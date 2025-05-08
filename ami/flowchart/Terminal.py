# -*- coding: utf-8 -*-
import os
from qtpy import QtCore, QtGui, QtWidgets
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
from pyqtgraph import functions as fn
from pyqtgraph.Point import Point
import subprocess
import inspect
import weakref
import tempfile
import typing


class Terminal(QtCore.QObject):

    sigTerminalOptional = QtCore.Signal(object)  # self

    def __init__(self, node, name, io, ttype, group=None, pos=None, removable=False, optional=False, unit=None):
        """
        Construct a new terminal.

        ==============  =================================================================================
        **Arguments:**
        node            the node to which this terminal belongs
        name            string, the name of the terminal
        io              'in', 'out'
        ttype           type terminal expects/returns
        group           Terminal group
        pos             [x, y], the position of the terminal within its node's boundaries
        removable       (bool) Whether the terminal can be removed by the user
        unit            Pint Unit
        ==============  =================================================================================
        """
        super().__init__()
        self._io = io
        self._node = weakref.ref(node)
        self._name = name
        self._removable = removable
        self._connections = {}
        self._group = group
        self._type = ttype
        self._allowOptional = optional or self._io == 'in'
        self._optional = optional
        self._unit = unit
        self._graphicsItem = TerminalGraphicsItem(self, parent=self._node().graphicsItem())

        self.recolor()

        if self._allowOptional:
            self.sigTerminalOptional.emit(self)

    def setOpts(self, **opts):
        self._removable = opts.get('removable', self._removable)
        self._type = opts.get('type', self._type)
        self._group = opts.get('group', None)
        self._optional = opts.get('optional', False)
        if self._allowOptional:
            self.sigTerminalOptional.emit(self)

    def connected(self, term):
        """
        Called whenever this terminal has been connected to another.
        (note--this function is called on both terminals)
        """
        self.node().connected(self, term)
        self.graphicsItem().buildMenu(reset=True)

    def disconnected(self, term):
        """
        Called whenever this terminal has been disconnected from another.
        (note--this function is called on both terminals)
        """
        self.node().disconnected(self, term)

    def type(self):
        return self._type

    def group(self):
        return self._group

    def setType(self, type):
        self._type = type

    def unit(self):
        return self._unit

    def setUnit(self, unit):
        assert self._unit is None  # TODO handle conversions
        self._unit = unit

    def optional(self):
        return self._optional

    def setOptional(self, optional, emit=True):
        if self._allowOptional:
            self._optional = optional
            if emit:
                self.sigTerminalOptional.emit(self)

    def connections(self):
        return self._connections

    def node(self):
        return self._node()

    def isInput(self):
        return self._io == 'in'

    def isOutput(self):
        return self._io == 'out'

    def isRemovable(self):
        return self._removable

    def name(self):
        return self._name

    def graphicsItem(self):
        return self._graphicsItem

    def isConnected(self):
        return len(self.connections()) > 0

    def connectedTo(self, term):
        return term in self.connections()

    def hasInput(self):
        for t in self.connections():
            if t.isOutput():
                return True
        return False

    def inputTerminals(self):
        """Return the terminal(s) that give input to this one."""
        return [t for t in self.connections() if t.isOutput()]

    def dependentTerms(self):
        """Return the list of terms which receive input from this terminal."""
        return set([t for t in self.connections() if t.isInput()])

    def connectTo(self, term, connectionItem=None, type_file=None):
        try:
            if self.connectedTo(term):
                raise Exception('Already connected')
            if term is self:
                raise Exception('Not connecting terminal to self')
            if term.node() is self.node():
                raise Exception("Can't connect to terminal on same node.")

            if self.isInput() and term.isInput():
                raise Exception("Can't connect input to input.")
            elif self.isOutput() and term.isOutput():
                raise Exception("Can't connect output to output.")

            types = {}
            for t in [self, term]:
                if t.isInput():
                    types["Input"] = t

                    if len(t.connections()) > 0:
                        raise Exception(
                            "Cannot connect %s <-> %s: Terminal %s is already connected to %s \
                            (and does not allow multiple connections)" % (self, term, t,
                                                                          list(t.connections().keys())))
                elif t.isOutput():
                    types["Output"] = t

            if not checkType(types, type_file):
                raise Exception(f"Invalid types. Expected: {term.type()} Got: {self.type()}")
        except Exception:
            if connectionItem is not None:
                connectionItem.close()
            raise

        if connectionItem is None:
            connectionItem = ConnectionItem(self.graphicsItem(), term.graphicsItem())
            self.graphicsItem().getViewBox().addItem(connectionItem)
        self._connections[term] = connectionItem
        term._connections[self] = connectionItem

        self.recolor()

        self.connected(term)
        term.connected(self)

        if self.isInput() and term.isOutput():
            self.setUnit(term.unit())
        elif self.isOutput() and term.isInput():
            term.setUnit(self.unit())

        return connectionItem

    def disconnectFrom(self, term):
        if not self.connectedTo(term):
            return
        item = self._connections[term]
        item.close()
        del self._connections[term]
        del term._connections[self]
        self.recolor()
        term.recolor()

        self.disconnected(term)
        term.disconnected(self)

    def disconnectAll(self):
        for t in list(self._connections.keys()):
            self.disconnectFrom(t)

    def recolor(self, color=None, recurse=True):
        if color is None:
            if not self.isConnected():
                # disconnected terminals are black
                color = QtGui.QColor(0, 0, 0)
            elif self.isInput() and not self.hasInput():
                # input terminal with no connected output terminals
                color = QtGui.QColor(200, 200, 0)
            else:
                # terminal has bad
                color = QtGui.QColor(255, 255, 255)
        self.graphicsItem().setBrush(QtGui.QBrush(color))

        if recurse:
            for t in self.connections():
                t.recolor(color, recurse=False)

    def __repr__(self):
        return "<Terminal %s.%s>" % (str(self.node().name()), str(self.name()))

    def __hash__(self):
        return id(self)

    def close(self):
        self.disconnectAll()
        item = self.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)

    def saveState(self):
        ttype = str(self._type)
        if not ttype.startswith('typing'):
            ttype = self._type

        return {
            'io': self._io,
            'removable': self._removable,
            'ttype': ttype,
            'optional': self._optional,
            'group': self._group
        }


class TerminalGraphicsItem(GraphicsObject):

    def __init__(self, term, parent=None):
        self.term = term
        GraphicsObject.__init__(self, parent)
        self.brush = fn.mkBrush(0, 0, 0)
        self.box = QtWidgets.QGraphicsRectItem(0, 0, 10, 10, self)
        self.label = QtWidgets.QGraphicsTextItem(self.term.name(), self)
        self.label.setTransform(self.label.transform().scale(0.7, 0.7))
        self.newConnection = None
        self.setFiltersChildEvents(True)  # to pick up mouse events on the rectitem
        self.setZValue(1)
        self.menu = None

    def setBrush(self, brush):
        self.brush = brush
        self.box.setBrush(brush)

    def disconnect(self, target):
        self.term.disconnectFrom(target.term)

    def boundingRect(self):
        br = self.box.mapRectToParent(self.box.boundingRect())
        lr = self.label.mapRectToParent(self.label.boundingRect())
        return br | lr

    def paint(self, p, *args):
        pass

    def setAnchor(self, x, y):
        pos = QtCore.QPointF(x, y)
        self.anchorPos = pos
        br = self.box.mapRectToParent(self.box.boundingRect())
        lr = self.label.mapRectToParent(self.label.boundingRect())

        if self.term.isInput():
            self.box.setPos(pos.x(), pos.y()-br.height()/2.)
            self.label.setPos(pos.x() + br.width(), pos.y() - lr.height()/2.)
        else:
            self.box.setPos(pos.x()-br.width(), pos.y()-br.height()/2.)
            self.label.setPos(pos.x()-br.width()-lr.width(), pos.y()-lr.height()/2.)
        self.updateConnections()

    def updateConnections(self):
        for t, c in self.term.connections().items():
            c.updateLine()

    def mousePressEvent(self, ev):
        # ev.accept()
        ev.ignore()  # necessary to allow click/drag events to process correctly

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            self.label.setFocus(QtCore.Qt.MouseFocusReason)
        elif ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.raiseContextMenu(ev)

    def raiseContextMenu(self, ev):
        # only raise menu if this terminal is removable
        menu = self.buildMenu()
        menu = self.scene().addParentContextMenus(self, menu, ev)
        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))

    def buildMenu(self, reset=False):
        if reset:
            # qt seg. faults if you don't delete old menu first
            self.menu = None

        if self.menu is None:
            self.menu = QtWidgets.QMenu()
            self.menu.setTitle("Terminal")

            if self.term.isConnected():
                def disconnect(term, connections):
                    for conn in connections:
                        term.disconnectFrom(conn)
                        conn.graphicsItem().buildMenu(reset=True)
                    term.graphicsItem().buildMenu(reset=True)

                disconAct = QtWidgets.QAction("Disconnect", self.menu)
                if self.term.inputTerminals():
                    disconAct.triggered.connect(lambda: disconnect(self.term, self.term.inputTerminals()))
                elif self.term.dependentTerms():
                    disconAct.triggered.connect(lambda: disconnect(self.term, self.term.dependentTerms()))
                self.menu.addAction(disconAct)
                self.menu.disconAct = disconAct
            else:
                pass

            if self.term.isRemovable():
                remAct = QtWidgets.QAction("Remove terminal", self.menu)
                remAct.triggered.connect(self.removeSelf)
                self.menu.addAction(remAct)
                self.menu.remAct = remAct

            if self.term._allowOptional:
                optionalAct = QtWidgets.QAction("Optional", self.menu, checkable=True, checked=self.term.optional())
                optionalAct.triggered.connect(self.optional)
                self.menu.addAction(optionalAct)
                self.menu.optionalAct = optionalAct

        return self.menu

    def removeSelf(self):
        self.term.node().removeTerminal(self.term)

    def optional(self, checked):
        self.term.setOptional(checked)

    def mouseDragEvent(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            ev.ignore()
            return

        ev.accept()

        if ev.isStart():
            if self.newConnection is None:
                self.newConnection = ConnectionItem(self)
                self.getViewBox().addItem(self.newConnection)

            self.newConnection.setTarget(self.mapToView(ev.pos()))
        elif ev.isFinish():
            if self.newConnection is not None:
                items = self.scene().items(ev.scenePos())
                gotTarget = False
                for i in items:
                    if isinstance(i, TerminalGraphicsItem):
                        self.newConnection.setTarget(i)
                        try:
                            self.term.connectTo(i.term, self.newConnection)
                            gotTarget = True
                        except Exception as e:
                            msg = QtWidgets.QMessageBox()
                            msg.setText(str(e))
                            msg.exec()
                        break

                if not gotTarget:
                    self.newConnection.close()
                self.newConnection = None
        else:
            if self.newConnection is not None:
                self.newConnection.setTarget(self.mapToView(ev.pos()))

    def hoverEvent(self, ev):
        if not ev.isExit() and ev.acceptDrags(QtCore.Qt.LeftButton):
            # we don't use the click, but we also don't want anyone else to use it.
            ev.acceptClicks(QtCore.Qt.LeftButton)
            ev.acceptClicks(QtCore.Qt.RightButton)
            self.box.setBrush(fn.mkBrush('w'))
        else:
            self.box.setBrush(self.brush)
        self.update()

    def connectPoint(self):
        # return the connect position of this terminal in view coords
        return self.mapToView(self.mapFromItem(self.box, self.box.boundingRect().center()))

    def nodeMoved(self):
        for t, item in self.term.connections().items():
            item.updateLine()


class ConnectionItem(GraphicsObject):

    def __init__(self, source, target=None):
        super().__init__(source)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable |
            QtWidgets.QGraphicsItem.ItemIsFocusable
        )
        self.source = source
        self.target = target
        self.hovered = False
        self.path = None
        self.shapePath = None
        self.style = {
            'shape': 'cubic',
            'color': (100, 100, 250),
            'width': 3.0,
            'hoverColor': (255, 0, 0),
            'hoverWidth': 10.0,
            'selectedColor': (200, 200, 0),
            'selectedWidth': 3.0,
            }
        self.source.getViewBox().addItem(self)
        self.updateLine()
        self.setZValue(0)

    def close(self):
        if self.scene() is not None:
            self.scene().removeItem(self)

    def setTarget(self, target):
        self.target = target
        self.updateLine()

    def setStyle(self, **kwds):
        self.style.update(kwds)
        if 'shape' in kwds:
            self.updateLine()
        else:
            self.update()

    def updateLine(self):
        start = Point(self.source.connectPoint())
        if isinstance(self.target, TerminalGraphicsItem):
            stop = Point(self.target.connectPoint())
        elif isinstance(self.target, QtCore.QPointF):
            stop = Point(self.target)
        else:
            return
        self.prepareGeometryChange()

        self.path = self.generatePath(start, stop)
        self.shapePath = None
        self.update()

    def generatePath(self, start, stop):
        path = QtGui.QPainterPath()
        path.moveTo(start)
        if self.style['shape'] == 'line':
            path.lineTo(stop)
        elif self.style['shape'] == 'cubic':
            path.cubicTo(Point(stop.x(), start.y()), Point(start.x(), stop.y()), Point(stop.x(), stop.y()))
        else:
            raise Exception('Invalid shape "%s"; options are "line" or "cubic"' % self.style['shape'])
        return path

    def keyPressEvent(self, ev):
        if not self.isSelected():
            ev.ignore()
            return

        if ev.key() == QtCore.Qt.Key_Delete or ev.key() == QtCore.Qt.Key_Backspace:
            self.source.disconnect(self.target)
            ev.accept()
        else:
            ev.ignore()

    def mousePressEvent(self, ev):
        ev.ignore()

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            sel = self.isSelected()
            self.setSelected(True)
            self.setFocus()
            if not sel and self.isSelected():
                self.update()

    def hoverEvent(self, ev):
        if (not ev.isExit()) and ev.acceptClicks(QtCore.Qt.LeftButton):
            self.hovered = True
        else:
            self.hovered = False
        self.update()

    def boundingRect(self):
        return self.shape().boundingRect()

    def viewRangeChanged(self):
        self.shapePath = None
        self.prepareGeometryChange()

    def shape(self):
        if self.shapePath is None:
            if self.path is None:
                return QtGui.QPainterPath()
            stroker = QtGui.QPainterPathStroker()
            px = self.pixelWidth()
            stroker.setWidth(px*8)
            self.shapePath = stroker.createStroke(self.path)
        return self.shapePath

    def paint(self, p, *args):
        if self.isSelected():
            p.setPen(fn.mkPen(self.style['selectedColor'], width=self.style['selectedWidth']))
        else:
            if self.hovered:
                p.setPen(fn.mkPen(self.style['hoverColor'], width=self.style['hoverWidth']))
            else:
                p.setPen(fn.mkPen(self.style['color'], width=self.style['width']))

        p.drawPath(self.path)


checked = []


def checkType(terminals, type_file=None):

    t_in = terminals["Input"]
    t_out = terminals["Output"]

    def f_in(t):
        pass

    f_in_name = t_in.node().name() + '_' + t_in.name()
    f_in_name = f_in_name.translate(checkType.replacements)
    f_in.__annotations__ = {'t': t_in.type()}
    f_in = str(inspect.signature(f_in))
    f_in = f_in.replace('~', '')
    f_in = f_in_name + f_in

    def f_out():
        pass

    f_out_name = t_out.node().name() + '_' + t_out.name()
    f_out_name = f_out_name.translate(checkType.replacements)
    f_out.__annotations__ = {'return': t_out.type()}
    f_out_sig = inspect.signature(f_out)
    f_out_annotation = f_out_sig.return_annotation
    if f_out_annotation is inspect.Signature.empty or f_out_annotation is typing.Any:
        f_out_return_string = 'pass'
    else:
        f_out_annotation_str = f_out_annotation.__module__ + '.' + f_out_annotation.__name__
        f_out_return_string = 'return '+f_out_annotation_str+'()'
    f_out = str(f_out_sig)
    f_out = f_out.replace('~', '')
    f_out = f_out_name + f_out

    if type_file:
        # this case is for reloading a saved file, we want to just run mypy on a single file
        # we return true always and then deal with disconnecting invalid connections later
        if f_in_name not in checked:
            type_file.write(f"def {f_in}:\n\tpass\n\n")
            checked.append(f_in_name)

        if f_out_name not in checked:
            type_file.write(f"def {f_out}:\n\t{f_out_return_string}\n")
            checked.append(f_out_name)

        type_file.write(f"\n{f_in_name}({f_out_name}())\n\n")
        return True
    else:
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write("from typing import *\n")
            f.write("from mypy_extensions import TypedDict\n")
            f.write("import numbers\n")
            f.write("import builtins\n")
            f.write("import amitypes\n")
            f.write("T = TypeVar('T')\n")
            f.write(f"def {f_in}:\n\tpass\n")
            f.write(f"def {f_out}:\n\t{f_out_return_string}")
            f.write(f"\n{f_in_name}({f_out_name}())")
            f.flush()
            dmypy_status = os.environ['DMYPY_STATUS_FILE']
            status = subprocess.call(["dmypy", "--status-file", dmypy_status, "check", f.name])
            if status == 2:
                subprocess.call(["dmypy", "--status-file", dmypy_status, "start"])
                status = subprocess.call(["dmypy", "--status-file", dmypy_status, "check", f.name])
            return status == 0


# only create the translation table once
checkType.replacements = str.maketrans(" .:|-", "_____")
