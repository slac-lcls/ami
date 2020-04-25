# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
from pyqtgraph import functions as fn
from pyqtgraph.pgcollections import OrderedDict
from pyqtgraph.debug import printExc
from ami.flowchart.Terminal import Terminal
import weakref


def strDict(d):
    return dict([(str(k), v) for k, v in d.items()])


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
    sigNodeEnabled = QtCore.Signal(object)  # self

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
        allowAddCondition bool; whether the user is allowed to add a condition
                        by the context menu.
        allowRemove     bool; whether the user is allowed to remove this node by the
                        context menu.
        viewable        bool; whether a pick one should be inserted into the graph to
                        view node inputs
        buffered        bool; whether a node has a to_operation which returns a rolling
                        buffer
        exportable      bool; whether export should be called
        filter          bool; whether a node is a filter
        ==============  ============================================================

        """
        super().__init__()
        self._name = name
        self._graphicsItem = None
        self.terminals = OrderedDict()
        self._inputs = OrderedDict()
        self._outputs = OrderedDict()
        self._conditions = OrderedDict()
        self._groups = OrderedDict()  # terminal group {"name": set(terminals)}
        self._allowAddInput = kwargs.get("allowAddInput", False)
        self._allowAddOutput = kwargs.get("allowAddOutput", False)
        self._allowAddCondition = kwargs.get("allowAddCondition", True)
        self._allowRemove = kwargs.get("allowRemove", True)
        self._viewable = kwargs.get("viewable", False)
        self._buffered = kwargs.get("buffered", False)
        self._exportable = kwargs.get("exportable", False)
        self._filter = kwargs.get("filter", False)
        self._editor = None
        self._enabled = True

        self.created = False
        self.changed = True
        self.viewed = False
        self.exception = None

        self._input_vars = {}  # term:var
        self._condition_vars = {}  # term:var

        terminals = kwargs.get("terminals", {})
        self.brush = self.determineColor(terminals)
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

    def determineColor(self, terminals):
        isInput = True
        isOutput = True
        for name, term in terminals.items():
            if term['io'] == 'in':
                isInput = False
            elif term['io'] == 'out':
                isOutput = False
            elif term['io'] == 'condition':
                isInput = False
                isOutput = False
                break

        brush = None
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

    def addInput(self, name="In", **kwargs):
        """Add a new input terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        This is a convenience function that just calls addTerminal(io='in', ...)"""
        # print "Node.addInput called."
        return self.addTerminal(name, io='in', ttype=self.terminals["In"].type(), **kwargs)

    def addOutput(self, name="Out", **kwargs):
        """Add a new output terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        This is a convenience function that just calls addTerminal(io='out', ...)"""
        return self.addTerminal(name, io='out', ttype=self.terminals["Out"].type(), **kwargs)

    def addCondition(self, name="Condition", **kwargs):
        """Add a new condition terminal to this Node with the given name. Extra
        keyword arguments are passed to Terminal.__init__.

        This is a convenience function that just calls addTerminal(io='condition', ...)"""
        return self.addTerminal(name, io='condition', ttype=bool, **kwargs)

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
        if name in self._conditions:
            del self._conditions[name]
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
        elif term.isOutput():
            self._outputs[name] = weakref.ref(self.terminals[name])
        elif term.isCondition():
            self._conditions[name] = weakref.ref(self.terminals[name])

        if group:
            if group not in self._groups:
                self._groups[group] = set()

            group = self._groups[group]
            group.add(name)

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

    def conditions(self):
        return self._conditions

    def viewable(self):
        return self._viewable

    def buffered(self):
        return self._buffered

    def buffered_topics(self):
        """
        Buffered nodes can override their topics/terms.
        """
        return {in_var: self.name()+'.'+term for term, in_var in self.input_vars().items()}

    def buffered_terms(self):
        """
        Buffered nodes can override their topics/terms.
        """
        return self.input_vars()

    def exportable(self):
        return self._exportable

    def filter(self):
        return self._filter

    def enabled(self):
        return self._enabled

    def input_vars(self):
        # we need to sort input_vars
        input_vars = {}
        for key in self.terminals.keys():
            if key in self._input_vars:
                input_vars[key] = self._input_vars[key]

        return input_vars

    def output_vars(self):
        output_vars = []

        for name, output in self._outputs.items():
            output_vars.append('.'.join([self.name(), name]))

        return output_vars

    def condition_vars(self):
        return self._condition_vars

    def graphicsItem(self, brush=None):
        """Return the GraphicsItem for this node. Subclasses may re-implement
        this method to customize their appearance in the flowchart."""
        if self._graphicsItem is None:
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

    def connected(self, localTerm, remoteTerm, pos=None):
        """Called whenever one of this node's terminals is connected elsewhere."""
        node = remoteTerm.node()

        if localTerm.isInput() and remoteTerm.isOutput():
            # if node.exportable():
            #     self._input_vars[localTerm.name()] = AutoExport.mangle('.'.join([node.name(), remoteTerm.name()]))
            if node.isSource():
                self._input_vars[localTerm.name()] = node.name()
            else:
                self._input_vars[localTerm.name()] = '.'.join([node.name(), remoteTerm.name()])
        elif localTerm.isCondition():
            self._condition_vars[localTerm.name()] = node.name()

        self.changed = True
        self.sigTerminalConnected.emit(localTerm, remoteTerm)

    def disconnected(self, localTerm, remoteTerm):
        """Called whenever one of this node's terminals is disconnected from another."""
        if localTerm.isInput() and remoteTerm.isOutput():
            del self._input_vars[localTerm.name()]
        elif localTerm.isCondition():
            del self._condition_vars[localTerm.name()]

        self.changed = True
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

        for name, term in self.conditions().items():
            if not term().isConnected():
                return False

        return True

    def setException(self, exc):
        self.exception = exc
        self.recolor(typ="exception")

    def clearException(self):
        self.setException(None)

    def recolor(self, typ=None):
        if typ == "exception":
            self.graphicsItem().setPen(QtGui.QPen(QtGui.QColor(255, 0, 0), 3))
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
        state = {'pos': (pos.x(), pos.y()), 'enabled': self._enabled}
        state['terminals'] = self.saveTerminals()
        return state

    def restoreState(self, state):
        """Restore the state of this node from a structure previously generated
        by saveState(). """
        pos = state.get('pos', (0, 0))
        self.graphicsItem().setPos(*pos)
        self._enabled = state.get('enabled')
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
                # opts = strDict(opts)
                self.addTerminal(name, **opts)
            except Exception:
                printExc("Error restoring terminal %s (%s):" % (str(name), str(opts)))

    def clearTerminals(self):
        for t in self.terminals.values():
            t.close()
        self.terminals = OrderedDict()
        self._inputs = OrderedDict()
        self._conditions = OrderedDict()
        self._outputs = OrderedDict()

    def close(self):
        """Cleans up after the node--removes terminals, graphicsItem, widget"""
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

    def disconnectAll(self):
        for t in self.terminals.values():
            t.disconnectAll()

    def isSource(self):
        return False


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
        flags = self.ItemIsMovable | self.ItemIsSelectable | self.ItemSendsGeometryChanges

        self.setFlags(flags)
        self.bounds = QtCore.QRectF(0, 0, 100, 100)
        self.nameItem = QtGui.QGraphicsTextItem(self.node.name(), self)
        self.nameItem.setDefaultTextColor(QtGui.QColor(50, 50, 50))
        self.nameItem.moveBy(self.bounds.width()/2. - self.nameItem.boundingRect().width()/2., 0)

        self.updateTerminals()

        self.menu = None
        self.add_condition = None
        self.enabled = QtGui.QAction("Enabled", self.menu, checkable=True, checked=True)
        self.buildMenu()

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
        conds = self.node.conditions()

        dy = bounds.height() / (len(inp)+len(conds)+1)
        y = dy
        for i, t in inp.items():
            t = t()
            item = t.graphicsItem()
            item.setParentItem(self)
            item.setAnchor(0, y)
            self.terminals[i] = (t, item)
            y += dy

        for i, t in conds.items():
            t = t()
            item = t.graphicsItem()
            item.setParentItem(self)
            item.setAnchor(0, y)
            self.terminals[i] = (t, item)
            y += dy

        out = self.node.outputs()
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
        if int(ev.button()) == int(QtCore.Qt.LeftButton):
            ev.accept()
            sel = self.isSelected()
            self.setSelected(True)
            if not sel and self.isSelected():
                self.update()

        elif int(ev.button()) == int(QtCore.Qt.RightButton):
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

    def buildMenu(self, reset=False):
        if reset:
            # qt seg. faults if you don't delete old menu first
            self.menu = None

        if self.menu is None:
            self.menu = QtGui.QMenu()
            self.menu.setTitle("Node")
            self.enabled.toggled.connect(self.enabledFromMenu)
            self.menu.addAction(self.enabled)
            if self.node._allowAddInput:
                self.menu.addAction("Add input", self.addInputFromMenu)
            if self.node._allowAddOutput:
                self.menu.addAction("Add output", self.addOutputFromMenu)
            if self.node._allowAddCondition:
                self.add_condition = self.menu.addAction("Add condition", self.addConditionFromMenu)
            if self.node._allowRemove:
                self.menu.addAction("Remove node", self.node.close)

        return self.menu

    def enabledFromMenu(self, checked):
        self.node.nodeEnabled(checked)
        self.node.sigNodeEnabled.emit(self.node)

    def addInputFromMenu(self):
        # called when add input is clicked in context menu
        self.node.addInput(removable=True)

    def addOutputFromMenu(self):
        # called when add output is clicked in context menu
        self.node.addOutput(removable=True)

    def addConditionFromMenu(self):
        self.node.addCondition(removable=True)
        self.menu.removeAction(self.add_condition)
        self.add_condition = None
