# -*- coding: utf-8 -*-
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.pgcollections import OrderedDict
from pyqtgraph import FileDialog
from pyqtgraph.debug import printExc
from pyqtgraph import configfile as configfile
from pyqtgraph import dockarea as dockarea
from numpy import ndarray
from ami.flowchart.FlowchartGraphicsView import FlowchartGraphicsView
from ami.flowchart.Terminal import Terminal
from ami.flowchart.library import LIBRARY
from ami.flowchart.library.common import CtrlNode
from ami.flowchart.Node import Node
from ami.comm import AsyncGraphCommHandler
from ami.graphkit_wrapper import Graph
from ami.client import flowchart_messages as fcMsgs

import ami.flowchart.Editor as EditorTemplate
import asyncio
import asyncqt
import zmq.asyncio
import dill


class Flowchart(Node):
    sigFileLoaded = QtCore.Signal(object)
    sigFileSaved = QtCore.Signal(object)

    sigChartLoaded = QtCore.Signal()
    # called when output is expected to have changed
    sigStateChanged = QtCore.Signal()

    def __init__(self, name=None, filePath=None, library=None,
                 broker_addr="", graphmgr_addr="", node_addr="", checkpoint_addr=""):
        super(Flowchart, self).__init__(name)
        self.library = library or LIBRARY
        self.graphmgr_addr = graphmgr_addr

        self.ctx = zmq.asyncio.Context()
        self.broker = self.ctx.socket(zmq.PUB)
        self.broker.connect(broker_addr)

        self.node = self.ctx.socket(zmq.PULL)
        self.node.bind(node_addr)

        self.checkpoint = self.ctx.socket(zmq.SUB)
        self.checkpoint.setsockopt_string(zmq.SUBSCRIBE, '')
        self.checkpoint.connect(checkpoint_addr)

        if name is None:
            name = "Flowchart"

        self.filePath = filePath

        self._nodes = {}
        self.nextZVal = 10
        self._widget = None
        self._scene = None

        self.widget()

        # self.viewBox.autoRange(padding=0.04)
        self.viewBox.enableAutoRange()

        self.sigChartLoaded.connect(self.chartLoaded)

    def setLibrary(self, lib):
        self.library = lib
        self.widget().chartWidget.buildMenu()

    def nodes(self):
        return self._nodes

    def createNode(self, nodeType, name=None, pos=None):
        """Create a new Node and add it to this flowchart.
        """
        if name is None:
            n = 0
            while True:
                name = "%s.%d" % (nodeType, n)
                if name not in self._nodes:
                    break
                n += 1

        # create an instance of the node
        node = self.library.getNodeType(nodeType)(name)
        self.addNode(node, name, pos)

        msg = fcMsgs.CreateNode(name, nodeType)
        self.broker.send_string(name, zmq.SNDMORE)
        self.broker.send_pyobj(msg)

        return node

    def addNode(self, node, name, pos=None):
        """Add an existing Node to this flowchart.

        See also: createNode()
        """
        if pos is None:
            pos = [0, 0]
        if type(pos) in [QtCore.QPoint, QtCore.QPointF]:
            pos = [pos.x(), pos.y()]
        item = node.graphicsItem()
        item.setZValue(self.nextZVal*2)
        self.nextZVal += 1
        self.viewBox.addItem(item)
        item.moveBy(*pos)
        self._nodes[name] = node
        node.sigClosed.connect(self.nodeClosed)
        node.sigTerminalConnected.connect(self.nodeConnected)
        node.sigTerminalDisconnected.connect(self.nodeDisconnected)

    @asyncqt.asyncSlot(object)
    async def nodeConnected(self, node):
        msg = fcMsgs.UpdateNodeAttributes(node.name(), node.input_vars(), node.condition_vars())
        await self.broker.send_string(msg.name, zmq.SNDMORE),
        await self.broker.send_pyobj(msg)

    @asyncqt.asyncSlot(object)
    async def nodeDisconnected(self, node):
        msg = fcMsgs.UpdateNodeAttributes(node.name(), node.input_vars(), node.condition_vars())
        await self.broker.send_string(node.name(), zmq.SNDMORE),
        await self.broker.send_pyobj(msg)

    def nodeClosed(self, node):
        # Qt does not like if this function is async
        del self._nodes[node.name()]
        try:
            getattr(node, 'sigClosed').disconnect(self.nodeClosed)
        except (TypeError, RuntimeError):
            pass
        self.broker.send_string(node.name(), zmq.SNDMORE)
        self.broker.send_pyobj(fcMsgs.CloseNode())

    def connectTerminals(self, term1, term2):
        """Connect two terminals together within this flowchart."""
        term1.connectTo(term2)

    def chartGraphicsItem(self):
        """
        Return the graphicsItem that displays the internal nodes and
        connections of this flowchart.

        Note that the similar method `graphicsItem()` is inherited from Node
        and returns the *external* graphical representation of this flowchart."""
        return self.viewBox

    def widget(self):
        """
        Return the control widget for this flowchart.

        This widget provides GUI access to the parameters for each node and a
        graphical representation of the flowchart.
        """
        if self._widget is None:
            self._widget = FlowchartCtrlWidget(self, self.graphmgr_addr)
            self.scene = self._widget.scene()
            self.viewBox = self._widget.viewBox()
        return self._widget

    def listConnections(self):
        conn = set()
        for n in self._nodes.values():
            terms = n.outputs()
            for n, t in terms.items():
                for c in t.connections():
                    conn.add((t, c))
        return conn

    def saveState(self):
        """
        Return a serializable data structure representing the current state of this flowchart.
        """
        state = Node.saveState(self)
        state['nodes'] = []
        state['connects'] = []

        for name, node in self._nodes.items():
            cls = type(node)
            clsName = "Node"
            if hasattr(cls, 'nodeName'):
                clsName = cls.nodeName
            ns = {'class': clsName, 'name': name, 'state': node.saveState()}
            state['nodes'].append(ns)

        conn = self.listConnections()
        for a, b in conn:
            state['connects'].append((a.node().name(), a.name(), b.node().name(), b.name()))

        return state

    def restoreState(self, state, clear=False):
        """
        Restore the state of this flowchart from a previous call to `saveState()`.
        """
        self.blockSignals(True)
        try:
            if clear:
                self.clear()
            Node.restoreState(self, state)
            nodes = state['nodes']
            nodes.sort(key=lambda a: a['state']['pos'][0])
            for n in nodes:

                if n['name'] in self._nodes:
                    self._nodes[n['name']].restoreState(n['state'])
                    continue
                if n['class'] == "Node":
                    try:
                        node = Node(name=n['name'])
                        node.restoreState(n['state'])
                        self.addNode(node, n['name'])
                    except Exception:
                        printExc("Error creating node %s: (continuing anyway)" % n['name'])
                else:
                    try:
                        node = self.createNode(n['class'], name=n['name'])
                        node.restoreState(n['state'])
                    except Exception:
                        printExc("Error creating node %s: (continuing anyway)" % n['name'])

            # self.restoreTerminals(state['terminals'])
            for n1, t1, n2, t2 in state['connects']:
                try:
                    self.connectTerminals(self._nodes[n1][t1], self._nodes[n2][t2])
                except Exception:
                    print(self._nodes[n1].terminals)
                    print(self._nodes[n2].terminals)
                    printExc("Error connecting terminals %s.%s - %s.%s:" % (n1, t1, n2, t2))

        finally:
            self.blockSignals(False)

        self.sigChartLoaded.emit()
        self.sigStateChanged.emit()

    def loadFile(self, fileName=None, startDir=None):
        """
        Load a flowchart (*.fc) file.
        """
        if fileName is None:
            if startDir is None:
                startDir = self.filePath
            if startDir is None:
                startDir = '.'
            self.fileDialog = FileDialog(None, "Load Flowchart..", startDir, "Flowchart (*.fc)")
            self.fileDialog.show()
            self.fileDialog.fileSelected.connect(self.loadFile)
            return
            #  NOTE: was previously using a real widget for the file dialog's parent,
            #        but this caused weird mouse event bugs..
        state = configfile.readConfigFile(fileName)
        self.restoreState(state, clear=True)
        self.viewBox.autoRange()
        self.sigFileLoaded.emit(fileName)
        return fileName

    def saveFile(self, fileName=None, startDir=None, suggestedFileName='flowchart.fc'):
        """
        Save this flowchart to a .fc file
        """
        if fileName is None:
            if startDir is None:
                startDir = self.filePath
            if startDir is None:
                startDir = '.'
            self.fileDialog = FileDialog(None, "Save Flowchart..", startDir, "Flowchart (*.fc)")
            self.fileDialog.setAcceptMode(QtGui.QFileDialog.AcceptSave)
            self.fileDialog.show()
            self.fileDialog.fileSelected.connect(self.saveFile)
            return
        if not fileName.endswith('.fc'):
            fileName += ".fc"
        configfile.writeConfigFile(self.saveState(), fileName)
        self.sigFileSaved.emit(fileName)

    def clear(self):
        """
        Remove all nodes from this flowchart except the original input/output nodes.
        """
        for n in list(self._nodes.values()):
            n.close()  # calls self.nodeClosed(n) by signal
        # self.clearTerminals()

    async def updateState(self):
        while True:
            node_name = await self.checkpoint.recv_string()
            new_node_state = await self.checkpoint.recv_pyobj()
            current_node_state = self._nodes[node_name].saveState()
            new_node_state['pos'] = current_node_state['pos']
            self._nodes[node_name].restoreState(new_node_state)

    @asyncqt.asyncSlot()
    async def chartLoaded(self):
        for name, node in self.nodes().items():
            msg = fcMsgs.NodeCheckpoint(node.name(), inputs=node.input_vars(), conditions=node.condition_vars(),
                                        state=node.saveState())
            await self.broker.send_string(node.name(), zmq.SNDMORE)
            await self.broker.send_pyobj(msg)


class FlowchartCtrlWidget(QtGui.QWidget):
    """
    The widget that contains the list of all the nodes in a flowchart and their controls,
    as well as buttons for loading/saving flowcharts.
    """

    def __init__(self, chart, graphmgr_addr):
        super(FlowchartCtrlWidget, self).__init__()

        self.items = {}
        self.currentFileName = None
        self.chart = chart
        self.chartWidget = FlowchartWidget(chart, self)

        self.ui = EditorTemplate.Ui_Toolbar()
        self.ui.setupUi(parent=self, chart=self.chartWidget)
        self.ui.create_model(self.ui.node_tree, self.chart.library.getLabelTree())

        self.features_lock = asyncio.Lock()
        self.features = {}

        self.graphCommHandler = AsyncGraphCommHandler(graphmgr_addr)

        self.ui.actionOpen.triggered.connect(self.openClicked)
        self.ui.actionSave.triggered.connect(self.saveClicked)
        # self.ui.saveAsBtn.clicked.connect(self.saveAsClicked)
        self.ui.actionApply.triggered.connect(self.applyClicked)
        self.ui.actionHome.triggered.connect(self.homeClicked)
        # self.chart.sigFileLoaded.connect(self.setCurrentFile)
        # self.ui.reloadBtn.clicked.connect(self.reloadClicked)
        self.chart.sigFileSaved.connect(self.fileSaved)

    @asyncqt.asyncSlot()
    async def applyClicked(self):
        graph_nodes = []

        for name, node in self.chart.nodes().items():
            if not hasattr(node, 'to_operation'):
                continue

            await self.chart.broker.send_string(name, zmq.SNDMORE),
            await self.chart.broker.send_pyobj(fcMsgs.GetNodeOperation())

            node = await self.chart.node.recv()
            node = dill.loads(node)

            if type(node) is list:
                graph_nodes.extend(node)
            else:
                graph_nodes.append(node)

        graph = Graph(name=str(self.chart.name))
        graph.add(graph_nodes)

        # TODO do some graph validation here before sending
        await self.graphCommHandler.update(graph)

        if not self.features:
            return

        # reinsert pick ones if they are still in the graph
        features = {}

        async with self.features_lock:
            for name, node in self.chart.nodes().items():
                for in_var in node.input_vars():
                    if in_var.name in self.features:
                        features[in_var.name] = self.features[in_var.name]
                        await self.graphCommHandler.view(in_var.name)
            self.features = features

    def reloadClicked(self):
        try:
            self.chartWidget.reloadLibrary()
        except Exception as e:
            raise e

    def openClicked(self):
        newFile = self.chart.loadFile()
        self.setCurrentFile(newFile)

    def fileSaved(self, fileName):
        self.setCurrentFile(fileName)

    def saveClicked(self):
        if self.currentFileName is None:
            self.saveAsClicked()
        else:
            try:
                self.chart.saveFile(self.currentFileName)
            except Exception as e:
                raise e

    def saveAsClicked(self):
        try:
            if self.currentFileName is None:
                self.chart.saveFile()
            else:
                self.chart.saveFile(suggestedFileName=self.currentFileName)
        except Exception as e:
            raise e

        # self.setCurrentFile(newFile)

    def homeClicked(self):
        children = self.viewBox().allChildren()
        self.viewBox().autoRange(items=children)

    def setCurrentFile(self, fileName):
        self.currentFileName = fileName
        # if fileName is None:
        #     self.ui.fileNameLabel.setText("<b>[ new ]</b>")
        # else:
        #     self.ui.fileNameLabel.setText("<b>%s</b>" % os.path.split(self.currentFileName)[1])
        # self.resizeEvent(None)

    def scene(self):
        # returns the GraphicsScene object
        return self.chartWidget.scene()

    def viewBox(self):
        return self.chartWidget.viewBox()

    def chartWidget(self):
        return self.chartWidget

    def clear(self):
        self.chartWidget.clear()


class FlowchartWidget(dockarea.DockArea):
    """Includes the actual graphical flowchart and debugging interface"""
    def __init__(self, chart, ctrl):
        dockarea.DockArea.__init__(self)
        self.chart = chart
        self.ctrl = ctrl
        self.hoverItem = None

        #  build user interface (it was easier to do it here than via developer)
        self.view = FlowchartGraphicsView(self)
        self.viewDock = dockarea.Dock('view', size=(1000, 600))
        self.viewDock.addWidget(self.view)
        self.viewDock.hideTitleBar()
        self.addDock(self.viewDock)

        self.hoverText = QtGui.QTextEdit()
        self.hoverText.setReadOnly(True)
        self.hoverDock = dockarea.Dock('Hover Info', size=(1000, 20))
        self.hoverDock.addWidget(self.hoverText)
        self.addDock(self.hoverDock, 'bottom')

        self._scene = self.view.scene()
        self._viewBox = self.view.viewBox()

        self._scene.selectionChanged.connect(self.selectionChanged)
        self._scene.sigMouseHover.connect(self.hoverOver)

    def reloadLibrary(self):
        self.nodeMenu.triggered.disconnect(self.nodeMenuTriggered)
        self.nodeMenu = None
        self.subMenus = []
        self.chart.library.reload()
        self.buildMenu()

    def buildMenu(self, pos=None):
        def buildSubMenu(node, rootMenu, subMenus, pos=None):
            for section, node in node.items():
                menu = QtGui.QMenu(section)
                rootMenu.addMenu(menu)
                if isinstance(node, OrderedDict):
                    buildSubMenu(node, menu, subMenus, pos=pos)
                    subMenus.append(menu)
                else:
                    act = rootMenu.addAction(section)
                    act.nodeType = section
                    act.pos = pos
        self.nodeMenu = QtGui.QMenu()
        self.subMenus = []
        buildSubMenu(self.chart.library.getNodeTree(), self.nodeMenu, self.subMenus, pos=pos)
        self.nodeMenu.triggered.connect(self.nodeMenuTriggered)
        return self.nodeMenu

    def scene(self):
        return self._scene  # the GraphicsScene item

    def viewBox(self):
        return self._viewBox  # the viewBox that items should be added to

    def nodeMenuTriggered(self, action):
        nodeType = action.nodeType
        if action.pos is not None:
            pos = action.pos
        else:
            pos = self.menuPos
        pos = self.viewBox().mapSceneToView(pos)

        self.chart.createNode(nodeType, pos=pos)

    @asyncqt.asyncSlot()
    async def selectionChanged(self):
        # print "FlowchartWidget.selectionChanged called."
        items = self._scene.selectedItems()

        if len(items) != 1:
            return

        item = items[0]
        if hasattr(item, 'node') and isinstance(item.node, Node) and item.node.viewable():
            node = item.node
            inputs = []

            if len(node.inputs()) != len(node.input_vars()):
                return

            for in_var in node.input_vars():

                if in_var.name in self.ctrl.features:
                    topic = self.ctrl.features[in_var.name]
                else:
                    topic = self.ctrl.graphCommHandler.auto(in_var.name)

                request_view = False

                async with self.ctrl.features_lock:
                    if in_var.name not in self.ctrl.features:
                        self.ctrl.features[in_var.name] = topic
                        request_view = True

                if request_view:
                    await self.ctrl.graphCommHandler.view(in_var.name)

                inputs.append((in_var.name, topic))

            await self.chart.broker.send_string(node.name(), zmq.SNDMORE)
            await self.chart.broker.send_pyobj(fcMsgs.DisplayNode(node.name(), inputs))

        elif hasattr(item, 'node') and isinstance(item.node, CtrlNode):
            node = item.node
            await self.chart.broker.send_string(node.name(), zmq.SNDMORE)
            await self.chart.broker.send_pyobj(fcMsgs.DisplayNode(node.name(), []))

    def hoverOver(self, items):
        # print "FlowchartWidget.hoverOver called."
        term = None
        for item in items:
            if item is self.hoverItem:
                return
            self.hoverItem = item
            if hasattr(item, 'term') and isinstance(item.term, Terminal):
                term = item.term
                break
        if term is None:
            self.hoverText.setPlainText("")
        else:
            val = term.value()
            if isinstance(val, ndarray):
                val = "%s %s %s" % (type(val).__name__, str(val.shape), str(val.dtype))
            else:
                val = str(val)
                if len(val) > 400:
                    val = val[:400] + "..."
            self.hoverText.setPlainText("%s.%s = %s" % (term.node().name(), term.name(), val))
            # self.hoverLabel.setCursorPosition(0)

    def clear(self):
        # self.outputTree.setData(None)
        self.hoverText.setPlainText('')
