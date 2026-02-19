# -*- coding: utf-8 -*-
from qtpy import QtCore, QtGui, QtWidgets
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
from pyqtgraph import functions as fn
from pyqtgraph.debug import printExc
from collections import OrderedDict
from ami.flowchart.Terminal import Terminal
from networkfox import modifiers
from lark import Lark, Transformer
import inspect
import weakref
import amitypes  # noqa
import typing  # noqa
import logging

from ami.data import RequestedData

logger = logging.getLogger(__name__)

def find_nearest(x):
    gs = 100
    low = (x // gs) * gs
    hi = low + 100
    return hi if x - low > hi - x else low


class Node(QtCore.QObject):
    """
    Node represents the basic processing unit of a flowchart.
    A Node subclass implements at least:

    1) A list of input / ouptut terminals and their properties

    A flowchart thus consists of multiple instances of Node subclasses, each of which is connected
    to other by wires between their terminals. A flowchart is, itself, also a special subclass of Node.
    This allows Nodes within the flowchart to connect to the input/output nodes of the flowchart itself.

    Optionally, a node class can implement the ctrlWidget() method, which must return a QWidget
    (usually containing other widgets) that will be displayed in the flowchart control panel.
    Some nodes implement fairly complex control widgets, but most nodes follow a simple form-like pattern:
    a list of parameter names and a single value (represented as spin box, check box, etc..) for each parameter.
    To make this easier, the CtrlNode subclass allows you to instead define a simple data structure that CtrlNode
    will use to automatically generate the control widget.
    """

    sigClosed = QtCore.Signal(object, object)  # name, input_vars
    sigTerminalAdded = QtCore.Signal(object, object)  # self, term
    sigTerminalRemoved = QtCore.Signal(object, object)  # self, term
    sigTerminalConnected = QtCore.Signal(object, object)  # localTerm, remoteTerm
    sigTerminalDisconnected = QtCore.Signal(object, object)  # localTerm, remoteTerm
    sigTerminalEdited = QtCore.Signal(object, object)
    sigTerminalOptional = QtCore.Signal(object, object)  # self, term
    sigNodeEnabled = QtCore.Signal(object)  # self
    sigNodeLatched = QtCore.Signal(object)  # self
    sigLabelChanged = QtCore.Signal(object, object)  # self, label

    def __init__(self, name, **kwargs):
        """
        ==============  ============================================================
        **Arguments:**
        name            The name of this specific node instance. It can be any
                        string, but must be unique within a flowchart. Usually,
                        we simply let the flowchart decide on a name when calling
                        Flowchart.addNode(...)
        terminals       Dict-of-dicts specifying the terminals present on this Node.
                        Terminal specifications look like::

                            'inputTerminalName': {'io': 'in'}
                            'outputTerminalName': {'io': 'out'}

                        There are a number of optional parameters for terminals:
                        multi, pos, renamable, removable, multiable, bypass. See
                        the Terminal class for more information.
        allowAddInput   bool; whether the user is allowed to add inputs by the
                        context menu.
        allowAddOutput  bool; whether the user is allowed to add outputs by the
                        context menu.
        allowRemove     bool; whether the user is allowed to remove this node by the
                        context menu.
        allowOptional   bool; whether terminals are allowed to be optional
        viewable        bool; whether a pick one should be inserted into the graph to
                        view node inputs
        buffered        bool; whether a node has a to_operation which returns a rolling
                        buffer
        exportable      bool; whether export should be called
        ==============  ============================================================

        """
        super().__init__()
        self._name = name
        self._label = ""
        self._graphicsItem = None
        self.terminals = OrderedDict()
        self._inputs = OrderedDict()
        self._outputs = OrderedDict()
        self._groups = OrderedDict()  # terminal group {"name": set(terminals)}
        self._allowAddInput = kwargs.get("allowAddInput", False)
        self._allowAddOutput = kwargs.get("allowAddOutput", False)
        self._allowRemove = kwargs.get("allowRemove", True)
        self._allowOptional = kwargs.get("allowOptional", True)
        self._viewable = kwargs.get("viewable", False)
        self._buffered = kwargs.get("buffered", False)
        self._exportable = kwargs.get("exportable", False)
        self._editor = None
        self._enabled = True

        self.created = False
        self.changed = True
        self.viewed = False
        self.exception = None
        self.global_op = kwargs.get("global_op", False)
        self.latched = False

        self._input_vars = {}  # term:var

        terminals = kwargs.get("terminals", {})
        self.brush = self.determineColor(terminals, self.global_op)
        self.graphicsItem(self.brush)

        for name, opts in terminals.items():
            self.addTerminal(name, **opts)

    def nextGroupName(self):
        group = "group.%d"
        i = 1
        while (group % i) in self._groups:
            i += 1
        return (group % i)

    def nextTerminalName(self, name):
        """Return an unused terminal name"""
        name2 = name
        i = 1
        while name2 in self.terminals:
            name2 = "%s.%d" % (name, i)
            i += 1
        return name2

    def determineColor(self, terminals, global_op=False):
        isInput = True
        isOutput = True
        for name, term in terminals.items():
            if term['io'] == 'in':
                isInput = False
            elif term['io'] == 'out':
                isOutput = False

        brush = None
        if global_op:
            brush = fn.mkBrush(100, 150, 255, 255)
        if isInput and not isOutput:
            brush = fn.mkBrush(255, 0, 0, 255)
        elif isOutput and not isInput:
            brush = fn.mkBrush(0, 255, 0, 255)

        return brush

    def nodeEnabled(self, enabled):
        self._enabled = enabled

        # block signals so that flowchart.nodeEnabled doesn't get called recursively
        self.graphicsItem().enabled.blockSignals(True)
        self.graphicsItem().enabled.setChecked(enabled)
        self.graphicsItem().enabled.blockSignals(False)

        if enabled:
            if self.brush:
                self.graphicsItem().setBrush(self.brush)
            else:
                self.graphicsItem().setBrush(fn.mkBrush(255, 255, 255, 255))
        else:
            self.graphicsItem().setBrush(fn.mkBrush(255, 255, 0, 255))

    def nodeLatched(self, latched):
        self.latched = latched

        # block signals so that flowchart.nodeEnabled doesn't get called recursively
        self.graphicsItem().latch.blockSignals(True)
        self.graphicsItem().latch.setChecked(latched)
        self.graphicsItem().latch.blockSignals(False)

    def addInput(self, name="In", **kwargs):
        """Add a new input terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        This is a convenience function that just calls addTerminal(io='in', ...)"""
        ttype = typing.Any
        if 'ttype' in kwargs:
            ttype = kwargs.pop('ttype')
        elif 'In' in self.terminals:
            ttype = self.terminals['In'].type()
        return self.addTerminal(name, io='in', ttype=ttype, **kwargs)

    def addOutput(self, name="Out", **kwargs):
        """Add a new output terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        This is a convenience function that just calls addTerminal(io='out', ...)"""
        ttype = typing.Any
        if 'ttype' in kwargs:
            ttype = kwargs.pop('ttype')
        elif 'Out' in self.terminals:
            ttype = self.terminals['Out'].type()
        return self.addTerminal(name, io='out', ttype=ttype, **kwargs)

    def removeTerminal(self, term):
        """Remove the specified terminal from this Node. May specify either the
        terminal's name or the terminal itself.

        Causes sigTerminalRemoved to be emitted."""
        if isinstance(term, Terminal):
            name = term.name()
        else:
            name = term
            term = self.terminals[name]

        # print "remove", name
        # term.disconnectAll()
        term.close()
        del self.terminals[name]
        if name in self._inputs:
            del self._inputs[name]
        if name in self._outputs:
            del self._outputs[name]
        self.graphicsItem().updateTerminals()
        self.sigTerminalRemoved.emit(self, term)
        self.graphicsItem().buildMenu(reset=True)

        group_name = term._group
        if group_name in self._groups:
            group = self._groups[group_name]
            group.discard(name)

            terms = []
            for term in group:
                terms.append(term)

            for term in terms:
                self.removeTerminal(term)

            if group_name in self._groups:
                del self._groups[group_name]

    def addTerminal(self, name, group=None, **opts):
        """Add a new terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        Causes sigTerminalAdded to be emitted."""
        name = self.nextTerminalName(name)
        term = Terminal(self, name, group=group, **opts)
        self.terminals[name] = term
        if term.isInput():
            self._inputs[name] = weakref.ref(self.terminals[name])
            term.sigTerminalOptional.connect(self.optionalTerm)
        elif term.isOutput():
            self._outputs[name] = weakref.ref(self.terminals[name])

        if group:
            if group not in self._groups:
                self._groups[group] = set()

            group = self._groups[group]
            group.add(name)

        self.graphicsItem().updateTerminals()
        self.graphicsItem().buildMenu(reset=True)
        self.sigTerminalAdded.emit(self, term)
        return term

    def inputs(self):
        """Return dict of all input terminals.
        Warning: do not modify."""
        return self._inputs

    def outputs(self):
        """Return dict of all output terminals.
        Warning: do not modify."""
        return self._outputs

    def viewable(self):
        return self._viewable

    def buffered(self):
        return self._buffered

    def buffered_topics(self):
        """
        Buffered nodes can override their topics/terms.
        """
        topics = {}
        for term, in_var in self.input_vars().items():
            if isinstance(in_var, modifiers.optional):
                topics[in_var.name] = self.name()+'.'+term
            else:
                topics[in_var] = self.name()+'.'+term
        return topics

    def buffered_terms(self):
        """
        Buffered nodes can override their topics/terms.
        """
        terms = {}
        for term, in_var in self.input_vars().items():
            if isinstance(in_var, modifiers.optional):
                terms[term] = in_var.name
            else:
                terms[term] = in_var

        return terms

    def exportable(self):
        return self._exportable

    def enabled(self):
        return self._enabled

    def input_vars(self):
        # we need to sort input_vars
        input_vars = {}
        for name, term in self.terminals.items():
            if name in self._input_vars:
                if term.optional():
                    input_vars[name] = modifiers.optional(self._input_vars[name],
                                                          mapped_name=name.replace(".", "_"))
                else:
                    input_vars[name] = self._input_vars[name]
        return input_vars

    def input_units(self):
        units = {}

        for key, term in self.terminals.items():
            if key in self._input_vars:
                units[key] = term.unit()

        return units

    def output_vars(self):
        output_vars = []

        for name, output in self._outputs.items():
            output_vars.append('.'.join([self.name(), name]))

        return output_vars

    def graphicsItem(self, brush=None):
        """Return the GraphicsItem for this node. Subclasses may re-implement
        this method to customize their appearance in the flowchart."""
        if self._graphicsItem is None:
            if self.isSource():
                self._graphicsItem = SourceNodeGraphicsItem(self, brush)
            else:
                self._graphicsItem = NodeGraphicsItem(self, brush)
        return self._graphicsItem

    def __getitem__(self, item):
        # return getattr(self, item)
        """Return the terminal with the given name"""
        if item not in self.terminals:
            raise KeyError(item)
        else:
            return self.terminals[item]

    def name(self):
        """Return the name of this node."""
        return self._name

    def __repr__(self):
        return "<Node %s @%x>" % (self.name(), id(self))

    def ctrlWidget(self):
        """Return this Node's control widget.

        By default, Nodes have no control widget. Subclasses may reimplement this
        method to provide a custom widget. This method is called by Flowcharts
        when they are constructing their Node list."""
        return None

    def connected(self, localTerm, remoteTerm):
        """Called whenever one of this node's terminals is connected elsewhere."""
        node = remoteTerm.node()

        if localTerm.isInput() and remoteTerm.isOutput():
            if node.exportable() and node.values['alias']:
                self._input_vars[localTerm.name()] = node.values['alias']
            elif node.isSource():
                self._input_vars[localTerm.name()] = node.name()
            else:
                self._input_vars[localTerm.name()] = '.'.join([node.name(), remoteTerm.name()])

        if not self.changed:
            self.changed = localTerm.isInput()

        self.sigTerminalConnected.emit(localTerm, remoteTerm)

    def disconnected(self, localTerm, remoteTerm):
        """Called whenever one of this node's terminals is disconnected from another."""
        if localTerm.isInput() and remoteTerm.isOutput():
            del self._input_vars[localTerm.name()]

        self.changed = localTerm.isInput()
        self.sigTerminalDisconnected.emit(localTerm, remoteTerm)

    def isConnected(self):
        for name, term in self.terminals.items():
            if not term.isConnected():
                return False
        return True

    def hasInput(self):
        for name, term in self.inputs().items():
            if not term().isConnected():
                return False

        return True

    def setException(self, exc, typ="exception"):
        self.exception = exc
        self.recolor(typ=typ)

    def clearException(self):
        self.setException(None, None)

    def recolor(self, typ=None):
        if typ == "warning":
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(255, 255, 0), 5))
        elif typ == "exception":
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(255, 0, 0), 5))
        elif typ == "selected":
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(250, 150, 0), 3))
        else:
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(0, 0, 0)))

    def saveState(self):
        """Return a dictionary representing the current state of this node
        (excluding input / output values). This is used for saving/reloading
        flowcharts. The default implementation returns this Node's position,
        bypass state, and information about each of its terminals.

        Subclasses may want to extend this method, adding extra keys to the returned
        dict."""
        pos = self.graphicsItem().pos()
        state = {'pos': (pos.x(), pos.y()), 'enabled': self._enabled,
                 'viewed': self.viewed, 'latched': self.latched,
                 'label': self._label}
        state['terminals'] = self.saveTerminals()
        return state

    def restoreState(self, state):
        """Restore the state of this node from a structure previously generated
        by saveState(). """
        pos = state.get('pos', (0, 0))
        self.graphicsItem().setPos(*pos)
        self._label = state.get('label', "")
        self._enabled = state.get('enabled')
        self.viewed = state.get('viewed', False)
        self.nodeLatched(state.get('latched', False))
        if self._label:
            self.graphicsItem().setLabel(self._label)
        if 'terminals' in state:
            self.restoreTerminals(state['terminals'])

    def saveTerminals(self):
        terms = OrderedDict()
        for n, t in self.terminals.items():
            terms[n] = (t.saveState())

        return terms

    def restoreTerminals(self, state):
        for name in list(self.terminals.keys()):
            if name not in state:
                self.removeTerminal(name)
        for name, opts in state.items():
            if type(opts['ttype']) is str:
                opts['ttype'] = eval(opts['ttype'])

            if name in self.terminals:
                term = self[name]
                term.setOpts(**opts)
                continue
            try:
                self.addTerminal(name, **opts)
            except Exception:
                printExc("Error restoring terminal %s (%s):" % (str(name), str(opts)))

    def clearTerminals(self):
        for t in self.terminals.values():
            t.close()
        self.terminals = OrderedDict()
        self._inputs = OrderedDict()
        self._outputs = OrderedDict()

    def close(self, emit=True):
        """Cleans up after the node--removes terminals, graphicsItem, widget"""
        if emit:
            self.sigClosed.emit(self, self.input_vars())
        self.disconnectAll()
        self.clearTerminals()
        item = self.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)
        self._graphicsItem = None
        w = self.ctrlWidget()
        if w is not None:
            w.setParent(None)
            w.close()

    def disconnectAll(self):
        for t in self.terminals.values():
            t.disconnectAll()

    def isSource(self):
        return False

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def setGraph(self, graph):
        self._graph = graph

    def optionalTerm(self, term):
        if self._allowOptional:
            checked = all([term.isInput() and term.optional() for name, term in self.terminals.items()])
            self.graphicsItem().optional.setChecked(checked)
            self.sigTerminalOptional.emit(self, term)

    def plotMetadata(self, **kwargs):
        return {}

    def onCreate(self):
        pass

    def terminalConnected(self, nodeTermConnected):
        """
        Can be used to trigger updates in widget.
        """
        pass

    def terminalDisconnected(self, nodeTermDisconnected):
        """
        Can be used to trigger updates in widget.
        """
        pass


class NodeGraphicsItem(GraphicsObject):

    def __init__(self, node, brush=None):
        super().__init__()

        self.pen = fn.mkPen(0, 0, 0)
        self.selectPen = fn.mkPen(200, 200, 200, width=2)

        if brush:
            self.brush = brush
        else:
            self.brush = fn.mkBrush(255, 255, 255, 255)

        self.hoverBrush = fn.mkBrush(200, 200, 200, 200)
        self.selectBrush = fn.mkBrush(200, 200, 255, 200)
        self.hovered = False

        self.node = node
        flags = QtWidgets.QGraphicsItem.ItemIsMovable | \
            QtWidgets.QGraphicsItem.ItemIsSelectable | \
            QtWidgets.QGraphicsItem.ItemSendsGeometryChanges

        self.setFlags(flags)
        self.bounds = QtCore.QRectF(0, 0, 100, 100)
        self.labelItem = QtWidgets.QGraphicsTextItem(self.node.name(), self)
        self.labelItem.setDefaultTextColor(QtGui.QColor(50, 50, 50))
        self.labelItem.mousePressEvent = self.nameEditingStarted
        self.labelItem.focusOutEvent = self.nameEditingFinished
        self.labelItem.moveBy(self.bounds.width()/2. - self.labelItem.boundingRect().width()/2., 0)

        # Add class name item below the name
        self.nameItem = QtWidgets.QGraphicsTextItem(self.node.name(), self)
        self.nameItem.setDefaultTextColor(QtGui.QColor(120, 120, 120))
        self.nameItem.setVisible(False)
        font = self.nameItem.font()
        font.setPointSize(8)
        font.setItalic(True)
        self.nameItem.setFont(font)
        self.nameItem.setPos(
            self.bounds.width()/2. - self.nameItem.boundingRect().width()/2.,
            self.nameItem.boundingRect().height()
        )

        self.updateTerminals()

        self.menu = None
        self.connectedTo = None
        self.enabled = QtWidgets.QAction("Enabled", self.menu, checkable=True, checked=True)
        self.optional = QtWidgets.QAction("Optional Inputs", self.menu, checkable=True, checked=False)
        self.latch = QtWidgets.QAction("Latch Outputs", self.menu, checkable=True, checked=False)
        self.buildMenu()

    def setPen(self, *args, **kwargs):
        self.pen = fn.mkPen(*args, **kwargs)
        self.update()

    def setBrush(self, brush):
        self.brush = brush
        self.update()

    def setLabel(self, label):
        self.labelItem.setPlainText(label)
        self.labelItem.setPos(self.bounds.width()/2. - self.labelItem.boundingRect().width()/2., 0)
        self.nameItem.setVisible(True)
        nameBottom = self.nameItem.boundingRect().height()
        self.nameItem.setPos(
            self.bounds.width()/2. - self.nameItem.boundingRect().width()/2.,
            nameBottom
        )

    def nameEditingStarted(self, event):
        self.labelItem.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        super().mousePressEvent(event)

    def nameEditingFinished(self, event):
        """Called when user finishes editing the name"""
        # Call the original focusOutEvent
        super().focusOutEvent(event)
        self.labelItem.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        self.labelItem.setPos(self.bounds.width()/2. - self.labelItem.boundingRect().width()/2., 0)
        self.nameItem.setVisible(True)
        nameBottom = self.nameItem.boundingRect().height()
        self.nameItem.setPos(
            self.bounds.width()/2. - self.nameItem.boundingRect().width()/2.,
            nameBottom
        )
        self.node._label = self.labelItem.toPlainText()
        self.node.sigLabelChanged.emit(self.node, self.node._label)

    def updateTerminals(self):
        inp = self.node.inputs()
        out = self.node.outputs()

        t = max(len(inp), len(out))
        bounds = QtCore.QRectF(0, 0, 100, 100*((t // 4) + 1))

        if bounds != self.bounds:
            self.bounds = bounds
            self.update()

        self.terminals = {}

        dy = bounds.height() / (len(inp)+1)
        y = dy
        for i, t in inp.items():
            t = t()
            item = t.graphicsItem()
            item.setParentItem(self)
            item.setAnchor(0, y)
            self.terminals[i] = (t, item)
            y += dy

        dy = bounds.height() / (len(out)+1)
        y = dy
        for i, t in out.items():
            t = t()
            item = t.graphicsItem()
            item.setParentItem(self)
            item.setZValue(self.zValue())
            item.setAnchor(bounds.width(), y)
            self.terminals[i] = (t, item)
            y += dy

    def boundingRect(self):
        return self.bounds.adjusted(-5, -5, 5, 5)

    def paint(self, p, *args):

        p.setPen(self.pen)
        if self.isSelected():
            p.setPen(self.selectPen)
            p.setBrush(self.selectBrush)
        else:
            p.setPen(self.pen)
            if self.hovered:
                p.setBrush(self.hoverBrush)
            else:
                p.setBrush(self.brush)

        p.drawRect(self.bounds)

    def mousePressEvent(self, ev):
        ev.ignore()

    def mouseClickEvent(self, ev):
        # if int(ev.button()) == int(QtCore.Qt.LeftButton):
        if ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            sel = self.isSelected()
            self.setSelected(True)
            if not sel and self.isSelected():
                self.update()

        # elif int(ev.button()) == int(QtCore.Qt.RightButton):
        elif ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.raiseContextMenu(ev)

    def mouseDragEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            pos = self.pos()+self.mapToParent(ev.pos())-self.mapToParent(ev.lastPos())
            if ev.isFinish():
                pos = [find_nearest(pos.x()), find_nearest(pos.y())]

            pos[0] = max(min(pos[0], 5e3), 0)
            pos[1] = max(min(pos[1], 5e3), -900)
            self.setPos(*pos)

    def hoverEvent(self, ev):
        if not ev.isExit() and ev.acceptClicks(QtCore.Qt.LeftButton):
            ev.acceptDrags(QtCore.Qt.LeftButton)
            self.hovered = True
        else:
            self.hovered = False
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() == QtCore.Qt.Key_Delete or ev.key() == QtCore.Qt.Key_Backspace:
            ev.accept()
            if not self.node._allowRemove:
                return
            self.node.close()
        elif ev.key() == QtCore.Qt.Key_Up:
            ev.accept()
            pos = self.pos() + (0, -100)
            self.setPos(*pos)
        elif ev.key() == QtCore.Qt.Key_Down:
            ev.accept()
            pos = self.pos() + (0, 100)
            self.setPos(*pos)
        elif ev.key() == QtCore.Qt.Key_Left:
            ev.accept()
            pos = self.pos() + (-100, 0)
            self.setPos(*pos)
        elif ev.key() == QtCore.Qt.Key_Right:
            ev.accept()
            pos = self.pos() + (100, 0)
            self.setPos(*pos)
        else:
            ev.ignore()

    def itemChange(self, change, val):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            for k, t in self.terminals.items():
                t[1].nodeMoved()

        return GraphicsObject.itemChange(self, change, val)

    def getMenu(self):
        if not self.node._graph:
            return self.menu

        graph = self.node._graph
        self.connectTo = QtWidgets.QMenu("Connect To")
        self.connectToSubMenus = []

        def connect(action):
            try:
                action.from_term.connectTo(action.to_term)
            except Exception as e:
                msg = QtWidgets.QMessageBox()
                msg.setText(str(e))
                msg.exec()

        for name, from_term in self.node.terminals.items():
            if from_term.isInput() and not from_term.isConnected():
                term_menu = QtWidgets.QMenu(self.node.name() + '.' + name)
                add_term_menu = False

                for node_name, node in graph.nodes(data='node'):
                    if node == self.node:
                        continue

                    added = False
                    node_menu = QtWidgets.QMenu(node_name)

                    for term_name, to_term in node.terminals.items():
                        if to_term.isOutput():
                            added = True
                            add_term_menu = True
                            action = node_menu.addAction(term_name)
                            action.from_term = from_term
                            action.to_term = to_term

                    if added:
                        term_menu.addMenu(node_menu)
                        node_menu.triggered.connect(connect)
                        self.connectToSubMenus.append(node_menu)

                if add_term_menu:
                    self.connectTo.addMenu(term_menu)
                    self.connectToSubMenus.append(term_menu)

            if from_term.isOutput():
                term_menu = QtWidgets.QMenu(self.node.name() + '.' + name)
                add_term_menu = False

                for node_name, node in graph.nodes(data='node'):
                    if node == self.node:
                        continue

                    added = False
                    node_menu = QtWidgets.QMenu(node_name)

                    for term_name, to_term in node.terminals.items():
                        if to_term.isInput() and not to_term.isConnected():
                            added = True
                            add_term_menu = True
                            action = node_menu.addAction(term_name)
                            action.from_term = from_term
                            action.to_term = to_term

                    if added:
                        term_menu.addMenu(node_menu)
                        node_menu.triggered.connect(connect)
                        self.connectToSubMenus.append(node_menu)

                if add_term_menu:
                    self.connectTo.addMenu(term_menu)
                    self.connectToSubMenus.append(term_menu)

        self.menu.addMenu(self.connectTo)

        return self.menu

    def raiseContextMenu(self, ev):
        menu = self.scene().addParentContextMenus(self, self.getMenu(), ev)
        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))

        if self.connectedTo:
            action = self.connectedTo.menuAction()
            self.menu.removeAction(action)
            del self.connectTo

    def buildMenu(self, reset=False):
        if reset:
            # qt seg. faults if you don't delete old menu first
            self.menu = None

        if self.menu is None:
            self.menu = QtWidgets.QMenu()
            self.menu.setTitle("Node")
            self.enabled.toggled.connect(self.enabledFromMenu)
            self.menu.addAction(self.enabled)
            if self.node._allowOptional:
                self.optional.toggled.connect(self.optionalFromMenu)
                self.menu.addAction(self.optional)
            if self.node.global_op:
                self.latch.toggled.connect(self.latchedFromMenu)
                self.menu.addAction(self.latch)
            if self.node._allowAddInput:
                self.menu.addAction("Add input", self.addInputFromMenu)
            if self.node._allowAddOutput:
                self.menu.addAction("Add output", self.addOutputFromMenu)
            if self.node._allowRemove:
                self.menu.addAction("Remove node", self.node.close)
            self.menu.addAction("View Source Code", self.viewSource)
        return self.menu

    def enabledFromMenu(self, checked):
        self.node.nodeEnabled(checked)
        self.node.sigNodeEnabled.emit(self.node)

    def optionalFromMenu(self, checked):
        for name, term in self.terminals.items():
            term, graphicsItem = term
            if term._allowOptional and graphicsItem.menu:
                graphicsItem.menu.optionalAct.setChecked(checked)
            term.setOptional(checked, emit=False)
            self.node.sigTerminalOptional.emit(self.node, term)

    def latchedFromMenu(self, checked):
        self.node.nodeLatched(checked)
        self.node.sigNodeLatched.emit(self.node)

    def addInputFromMenu(self):
        # called when add input is clicked in context menu
        self.node.addInput(removable=True)

    def addOutputFromMenu(self):
        # called when add output is clicked in context menu
        self.node.addOutput(removable=True)

    def viewSource(self):
        self.sourceEditor = QtWidgets.QTextEdit()
        self.sourceEditor.setText(inspect.getsource(self.node.__class__))
        self.sourceEditor.setReadOnly(True)
        self.sourceEditor.setWindowTitle(self.node.__class__.__name__ + ' Source')
        self.sourceEditor.show()


class SourceNodeGraphicsItem(NodeGraphicsItem):
    """
    Extension of the NodeGraphicsItem to handle the source kwargs graphics.
    """
    sigSourceKwargs = QtCore.Signal(object) # signal emitted when new user kwargs are supplied

    def __init__(self, node, brush=None):
        super().__init__(node, brush=brush)
        self._source_kwargs = {}

        self.kwargs_parser = Lark(kwargs_grammar, start='value') #, transformer=MyTransformer_2(), parser='lalr')
        self.kwargs_transformer = KwargsTransformer()

    @property
    def source_kwargs(self):
        return self._source_kwargs

    @source_kwargs.setter
    def source_kwargs(self, kws):
        self._source_kwargs = kws
        self.emit_source_kwargs()

    def emit_source_kwargs(self):
        logger.debug(f'Emit kws: {self.node._name} {self.source_kwargs}')
        requested_data = RequestedData()
        requested_data.add(self.node._name, kwargs=self.source_kwargs)
        self.sigSourceKwargs.emit(requested_data)

    def buildMenu(self, reset=False):
        if reset:
            # qt seg. faults if you don't delete old menu first
            self.menu = None

        if self.menu is None:
            self.menu = QtWidgets.QMenu()
            self.menu.setTitle("Node")
            self.enabled.toggled.connect(self.enabledFromMenu)
            self.menu.addAction(self.enabled)
            if self.node._allowOptional:
                self.optional.toggled.connect(self.optionalFromMenu)
                self.menu.addAction(self.optional)
            if self.node._allowAddInput:
                self.menu.addAction("Add input", self.addInputFromMenu)
            if self.node._allowAddOutput:
                self.menu.addAction("Add output", self.addOutputFromMenu)
            if self.node._allowRemove:
                self.menu.addAction("Remove node", self.node.close)
            if self.node.isSource():
                self.menu.addAction("Source kwargs", self.editSourceKwargs)
            self.menu.addAction("View Source Code", self.viewSource)
        return self.menu

    def editSourceKwargs(self):
        self.kwargsEditorWindow = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()

        label1 = QtWidgets.QLabel()
        label1.setWordWrap(True)
        label1_font = QtGui.QFont()
        label1_font.setBold(True)
        label1_font.setPointSize(14)
        label1.setFont(label1_font)
        label1.setText("/!\ Expert only /!\\")

        label2 = QtWidgets.QLabel()
        label2.setWordWrap(True)
        label2.setText("Enter kwargs in a dict format: {\'k1\': v1, ...}")

        self.kwargs_edit = QtWidgets.QLineEdit()
        self.kwargs_edit.setText(str(self.source_kwargs))

        cmdLayout = QtWidgets.QHBoxLayout()
        cmd_save = QtWidgets.QPushButton("Save")
        cmd_save.clicked.connect(self.cmd_save)
        cmd_cancel = QtWidgets.QPushButton("Close")
        cmd_cancel.clicked.connect(self.kwargsEditorWindow.close)
        cmdLayout.addWidget(cmd_save)
        cmdLayout.addWidget(cmd_cancel)

        layout.addWidget(label1)
        layout.addWidget(label2)
        layout.addWidget(self.kwargs_edit)
        layout.addLayout(cmdLayout)
        self.kwargsEditorWindow.setLayout(layout)
        self.kwargsEditorWindow.show()
        self.kwargsEditorWindow.resize(450, self.kwargsEditorWindow.height())

    def cmd_save(self):
        #self.source_kwargs = eval(self.kwargs_edit.text())  # Code injection risk
        kwargs = self.kwargs_edit.text()
        if kwargs == '':
            kwargs = "{}"
        p = self.kwargs_parser.parse(kwargs)
        self.source_kwargs = dict(self.kwargs_transformer.transform(p))


kwargs_grammar = r"""
    ?value : list
           | dict
           | kv_pair
           | number
           | string

    kv_pair : (string | number) ":" value
    list : "[" [value ("," value)*] "]"
    dict : "{" [kv_pair ("," kv_pair)*] "}"

    STRING : /".*?(?<!\\)"/ | /'.*?(?<!\\)'/
    string : STRING
    number : SIGNED_NUMBER

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS // ignore white space
"""

class KwargsTransformer(Transformer):
    list = list
    dict = dict
    kv_pair = tuple

    def number(self, value):
        value = value[0]
        return float(value)

    def string(self, s):
        s = s[0]
        return str(s[1:-1])

