# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
from pyqtgraph import functions as fn
from pyqtgraph.pgcollections import OrderedDict
from pyqtgraph.debug import printExc
from ami.flowchart.Terminal import Terminal


def strDict(d):
    return dict([(str(k), v) for k, v in d.items()])


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

    sigClosed = QtCore.Signal(object)
    sigRenamed = QtCore.Signal(object, object)
    sigTerminalRenamed = QtCore.Signal(object, object)  # term, oldName
    sigTerminalAdded = QtCore.Signal(object, object)  # self, term
    sigTerminalRemoved = QtCore.Signal(object, object)  # self, term
    sigTerminalConnected = QtCore.Signal(object)  # self
    sigTerminalDisconnected = QtCore.Signal(object)  # self

    def __init__(self, name, terminals=None, allowAddInput=False, allowAddOutput=False, allowRemove=True,
                 viewable=False):
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
        viewable        bool; whether a pick one should be inserted into the graph to
                        view node inputs
        ==============  ============================================================

        """
        QtCore.QObject.__init__(self)
        self._name = name
        self._graphicsItem = None
        self.terminals = OrderedDict()
        self._inputs = OrderedDict()
        self._outputs = OrderedDict()
        self._allowAddInput = allowAddInput   # flags to allow the user to add/remove terminals
        self._allowAddOutput = allowAddOutput
        self._allowRemove = allowRemove
        self._viewable = viewable

        self.exception = None
        if terminals is None:
            return
        for name, opts in terminals.items():
            self.addTerminal(name, **opts)

        self.input_names = []
        self.condition_names = []
        self.win = None

    def nextTerminalName(self, name):
        """Return an unused terminal name"""
        name2 = name
        i = 1
        while name2 in self.terminals:
            name2 = "%s.%d" % (name, i)
            i += 1
        return name2

    def addInput(self, name="Input", **args):
        """Add a new input terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        This is a convenience function that just calls addTerminal(io='in', ...)"""
        # print "Node.addInput called."
        return self.addTerminal(name, io='in', **args)

    def addOutput(self, name="Output", **args):
        """Add a new output terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        This is a convenience function that just calls addTerminal(io='out', ...)"""
        return self.addTerminal(name, io='out', **args)

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

    def terminalRenamed(self, term, oldName):
        """Called after a terminal has been renamed

        Causes sigTerminalRenamed to be emitted."""
        newName = term.name()
        for d in [self.terminals, self._inputs, self._outputs]:
            if oldName not in d:
                continue
            d[newName] = d[oldName]
            del d[oldName]

        self.graphicsItem().updateTerminals()
        self.sigTerminalRenamed.emit(term, oldName)

    def addTerminal(self, name, **opts):
        """Add a new terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        Causes sigTerminalAdded to be emitted."""
        name = self.nextTerminalName(name)
        term = Terminal(self, name, **opts)
        self.terminals[name] = term
        if term.isInput():
            self._inputs[name] = term
        elif term.isOutput():
            self._outputs[name] = term
        self.graphicsItem().updateTerminals()
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

    def graphicsItem(self):
        """Return the GraphicsItem for this node. Subclasses may re-implement
        this method to customize their appearance in the flowchart."""
        if self._graphicsItem is None:
            self._graphicsItem = NodeGraphicsItem(self)
        return self._graphicsItem

    # this is just bad planning. Causes too many bugs.
    def __getattr__(self, attr):
        """Return the terminal with the given name"""
        if attr not in self.terminals:
            raise AttributeError(attr)
        else:
            import traceback
            traceback.print_stack()
            print("Warning: use of node.terminalName is deprecated; use node['terminalName'] instead.")
            return self.terminals[attr]

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

    def rename(self, name):
        """Rename this node. This will cause sigRenamed to be emitted."""
        oldName = self._name
        self._name = name
        self.sigRenamed.emit(self, oldName)

    def dependentNodes(self):
        """Return the list of nodes which provide direct input to this node"""
        nodes = set()
        for t in self.inputs().values():
            nodes |= set([i.node() for i in t.inputTerminals()])
        return nodes

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
        if localTerm.isInput() and remoteTerm.isOutput():
            if localTerm.name() == "In":
                self.input_names.append(remoteTerm.node().name())
            elif localTerm.name() == "Condition":
                self.condition_names.append(remoteTerm.node().name())
            self.sigTerminalConnected.emit(self)

    def disconnected(self, localTerm, remoteTerm):
        """Called whenever one of this node's terminals is disconnected from another."""
        if localTerm.isInput() and remoteTerm.isOutput():
            if localTerm.name() == "In":
                self.input_names.remove(remoteTerm.node().name())
            elif localTerm.name() == "Condition":
                self.condition_names.remove(remoteTerm.node().name())
            self.sigTerminalDisconnected.emit(self)

    def setException(self, exc):
        self.exception = exc
        self.recolor()

    def clearException(self):
        self.setException(None)

    def recolor(self):
        if self.exception is None:
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(0, 0, 0)))
        else:
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(150, 0, 0), 3))

    def saveState(self):
        """Return a dictionary representing the current state of this node
        (excluding input / output values). This is used for saving/reloading
        flowcharts. The default implementation returns this Node's position,
        bypass state, and information about each of its terminals.

        Subclasses may want to extend this method, adding extra keys to the returned
        dict."""
        pos = self.graphicsItem().pos()
        state = {'pos': (pos.x(), pos.y())}
        state['terminals'] = self.saveTerminals()
        return state

    def restoreState(self, state):
        """Restore the state of this node from a structure previously generated
        by saveState(). """
        pos = state.get('pos', (0, 0))
        self.graphicsItem().setPos(*pos)
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
            if name in self.terminals:
                term = self[name]
                term.setOpts(**opts)
                continue
            try:
                opts = strDict(opts)
                self.addTerminal(name, **opts)
            except Exception:
                printExc("Error restoring terminal %s (%s):" % (str(name), str(opts)))

    def clearTerminals(self):
        for t in self.terminals.values():
            t.close()
        self.terminals = OrderedDict()
        self._inputs = OrderedDict()
        self._outputs = OrderedDict()

    def close(self):
        """Cleans up after the node--removes terminals, graphicsItem, widget"""
        self.disconnectAll()
        self.clearTerminals()
        item = self.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)
        self._graphicsItem = None
        w = self.ctrlWidget()
        if w is not None:
            w.setParent(None)
        self.sigClosed.emit(self)

    def disconnectAll(self):
        for t in self.terminals.values():
            t.disconnectAll()


class NodeGraphicsItem(GraphicsObject):
    def __init__(self, node):
        GraphicsObject.__init__(self)

        self.pen = fn.mkPen(0, 0, 0)
        self.selectPen = fn.mkPen(200, 200, 200, width=2)
        self.brush = fn.mkBrush(200, 200, 200, 150)
        self.hoverBrush = fn.mkBrush(200, 200, 200, 200)
        self.selectBrush = fn.mkBrush(200, 200, 255, 200)
        self.hovered = False

        self.node = node
        flags = self.ItemIsMovable | self.ItemIsSelectable | self.ItemIsFocusable | self.ItemSendsGeometryChanges

        self.setFlags(flags)
        self.bounds = QtCore.QRectF(0, 0, 100, 100)
        self.nameItem = QtGui.QGraphicsTextItem(self.node.name(), self)
        self.nameItem.setDefaultTextColor(QtGui.QColor(50, 50, 50))
        self.nameItem.moveBy(self.bounds.width()/2. - self.nameItem.boundingRect().width()/2., 0)
        self.nameItem.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        self.updateTerminals()

        self.nameItem.focusOutEvent = self.labelFocusOut
        self.nameItem.keyPressEvent = self.labelKeyPress

        self.menu = None
        self.buildMenu()

    def labelFocusOut(self, ev):
        QtGui.QGraphicsTextItem.focusOutEvent(self.nameItem, ev)
        self.labelChanged()

    def labelKeyPress(self, ev):
        if ev.key() == QtCore.Qt.Key_Enter or ev.key() == QtCore.Qt.Key_Return:
            self.labelChanged()
        else:
            QtGui.QGraphicsTextItem.keyPressEvent(self.nameItem, ev)

    def labelChanged(self):
        newName = str(self.nameItem.toPlainText())
        if newName != self.node.name():
            self.node.rename(newName)

        bounds = self.boundingRect()
        self.nameItem.setPos(bounds.width()/2. - self.nameItem.boundingRect().width()/2., 0)

    def setPen(self, *args, **kwargs):
        self.pen = fn.mkPen(*args, **kwargs)
        self.update()

    def setBrush(self, brush):
        self.brush = brush
        self.update()

    def updateTerminals(self):
        bounds = self.bounds
        self.terminals = {}
        inp = self.node.inputs()
        dy = bounds.height() / (len(inp)+1)
        y = dy
        for i, t in inp.items():
            item = t.graphicsItem()
            item.setParentItem(self)
            item.setAnchor(0, y)
            self.terminals[i] = (t, item)
            y += dy

        out = self.node.outputs()
        dy = bounds.height() / (len(out)+1)
        y = dy
        for i, t in out.items():
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
        # print "Node.mouseClickEvent called."
        if int(ev.button()) == int(QtCore.Qt.LeftButton):
            ev.accept()
            # print "    ev.button: left"
            sel = self.isSelected()
            # ret = QtGui.QGraphicsItem.mousePressEvent(self, ev)
            self.setSelected(True)
            if not sel and self.isSelected():
                # self.setBrush(QtGui.QBrush(QtGui.QColor(200, 200, 255)))
                # self.emit(QtCore.SIGNAL('selected'))
                # self.scene().selectionChanged.emit() # for some reason this doesn't seem to be happening automatically
                self.update()
            # return ret

        elif int(ev.button()) == int(QtCore.Qt.RightButton):
            # print "    ev.button: right"
            ev.accept()
            # pos = ev.screenPos()
            self.raiseContextMenu(ev)
            # self.menu.popup(QtCore.QPoint(pos.x(), pos.y()))

    def mouseDragEvent(self, ev):
        # print "Node.mouseDrag"
        if ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            self.setPos(self.pos()+self.mapToParent(ev.pos())-self.mapToParent(ev.lastPos()))

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
        else:
            ev.ignore()

    def itemChange(self, change, val):
        if change == self.ItemPositionHasChanged:
            for k, t in self.terminals.items():
                t[1].nodeMoved()
        return GraphicsObject.itemChange(self, change, val)

    def getMenu(self):
        return self.menu

    def raiseContextMenu(self, ev):
        menu = self.scene().addParentContextMenus(self, self.getMenu(), ev)
        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))

    def buildMenu(self):
        self.menu = QtGui.QMenu()
        self.menu.setTitle("Node")
        if self.node._allowAddInput:
            self.menu.addAction("Add input", self.addInputFromMenu)
        if self.node._allowAddOutput:
            self.menu.addAction("Add output", self.addOutputFromMenu)
        if "Condition" not in self.node.terminals:
            self.menu.addAction("Add condition", self.addConditionFromMenu)
        if self.node._allowRemove:
            self.menu.addAction("Remove node", self.node.close)

    def addInputFromMenu(self):
        # called when add input is clicked in context menu
        self.node.addInput(renamable=True, removable=True, multiable=True)

    def addOutputFromMenu(self):
        # called when add output is clicked in context menu
        self.node.addOutput(renamable=True, removable=True, multiable=False)

    def addConditionFromMenu(self):
        self.node.addInput(name="Condition", removable=True)