from pyqtgraph.Qt import QtGui, QtCore, QtWidgets
from pyqtgraph.widgets.GraphicsView import GraphicsView
from pyqtgraph.graphicsItems.ViewBox import ViewBox
from pyqtgraph import GridItem, GraphicsWidget
from ami.flowchart.Node import SubgraphNode, NodeGraphicsItem, find_nearest
from ami.flowchart.library.common import SourceNode


def clamp(pos):
    pos = [find_nearest(pos.x()), find_nearest(pos.y())]
    pos[0] = max(min(pos[0], 5e3), 0)
    pos[1] = max(min(pos[1], 5e3), -900)
    return QtCore.QPointF(*pos)


class CommentName(GraphicsWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QtWidgets.QGraphicsTextItem("Enter comment here", parent=self)
        self.label.setTextInteractionFlags(QtCore.Qt.TextEditorInteraction)
        self.setGraphicsItem(self.label)

    def text(self):
        return self.label.toPlainText()

    def setText(self, text):
        self.label.setPlainText(text)


class CommentRect(GraphicsWidget):
    # Copyright 2015-2019 Ilgar Lunin, Pedro Cabrera
    # taken from pyflow
    __backgroundColor = QtGui.QColor(100, 100, 255, 50)
    __pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.0, QtCore.Qt.DashLine)

    def __init__(self, view=None, mouseDownPos=QtCore.QPointF(0, 0), id=0):
        super().__init__()
        self.setZValue(2)
        self.id = id
        self.headerLayout = QtGui.QGraphicsLinearLayout(QtCore.Qt.Horizontal)
        self.commentName = CommentName(parent=self)
        self.headerLayout.addItem(self.commentName)
        self.__mouseDownPos = mouseDownPos
        self.setPos(self.__mouseDownPos)
        self.resize(0, 0)
        self.selectFullyIntersectedItems = True
        self.childNodes = set()
        self.buildMenu()
        if view:
            self.view = view
            self.view.addItem(self)

    def collidesWithItem(self, item):
        if self.selectFullyIntersectedItems:
            return self.sceneBoundingRect().contains(item.sceneBoundingRect())
        return super().collidesWithItem(item)

    def setDragPoint(self, dragPoint):
        topLeft = QtCore.QPointF(self.__mouseDownPos)
        bottomRight = QtCore.QPointF(dragPoint)
        if dragPoint.x() < self.__mouseDownPos.x():
            topLeft.setX(dragPoint.x())
            bottomRight.setX(self.__mouseDownPos.x())
        if dragPoint.y() < self.__mouseDownPos.y():
            topLeft.setY(dragPoint.y())
            bottomRight.setY(self.__mouseDownPos.y())
        self.setPos(topLeft)
        self.resize(max(bottomRight.x() - topLeft.x(), 100),
                    max(bottomRight.y() - topLeft.y(), 100))

    def paint(self, painter, option, widget):
        rect = self.windowFrameRect()
        painter.setBrush(self.__backgroundColor)
        painter.setPen(self.__pen)
        painter.drawRect(rect)

    def destroy(self):
        self.view.removeItem(self)
        del self.view.commentRects[self.id]

    def nodeCreated(self, node):
        item = node.graphicsItem()
        if self.collidesWithItem(item):
            self.childNodes.add(item)

    def updateChildren(self, children):
        collided = set()
        for child in children:
            if self.collidesWithItem(child):
                collided.add(child)
        self.childNodes = collided

    def mouseDragEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            boundingRect = self.boundingRect()
            width = boundingRect.width()
            height = boundingRect.height()
            rect = QtCore.QRectF(width - 50, height - 50, 50, 50)

            if rect.contains(ev.pos()):
                ev.ignore()
                self.view.commentRect = self
            else:
                ev.accept()
                pos = self.pos()+self.mapToParent(ev.pos())-self.mapToParent(ev.lastPos())
                old_pos = self.pos()

                if ev.isFinish():
                    pos = clamp(pos)
                self.setPos(pos)

                diff = pos - old_pos
                for child in self.childNodes:
                    child.moveBy(*diff)

    def mouseClickEvent(self, ev):
        if int(ev.button()) == int(QtCore.Qt.RightButton):
            ev.accept()
            self.raiseContextMenu(ev)

    def buildMenu(self):
        self.menu = QtGui.QMenu()
        self.menu.setTitle("Comment")
        self.menu.addAction("Remove Comment", self.destroy)

    def raiseContextMenu(self, ev):
        menu = self.scene().addParentContextMenus(self, self.menu, ev)
        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))

    def saveState(self):
        rect = self.sceneBoundingRect()
        topLeft = clamp(self.view.mapToView(rect.topLeft()))
        bottomRight = clamp(self.view.mapToView(rect.bottomRight()))
        return {'id': self.id,
                'text': self.commentName.text(),
                'topLeft': (topLeft.x(), topLeft.y()),
                'bottomRight': (bottomRight.x(), bottomRight.y())}

    def restoreState(self, state):
        self.id = state['id']
        self.commentName.setText(state['text'])
        self.__mouseDownPos = QtCore.QPointF(*state['topLeft'])
        self.setDragPoint(QtCore.QPointF(*state['bottomRight']))


class SelectionRect(GraphicsWidget):
    # Copyright 2015-2019 Ilgar Lunin, Pedro Cabrera
    # taken from pyflow
    __backgroundColor = QtGui.QColor(100, 100, 100, 50)
    __pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.0, QtCore.Qt.DashLine)

    def __init__(self, view, mouseDownPos):
        super().__init__()
        self.setZValue(2)

        self.view = view
        self.view.addItem(self)
        self.__mouseDownPos = mouseDownPos
        self.setPos(self.__mouseDownPos)
        self.resize(0, 0)
        self.selectFullyIntersectedItems = True

    def collidesWithItem(self, item):
        if self.selectFullyIntersectedItems:
            return self.sceneBoundingRect().contains(item.sceneBoundingRect())
        return super().collidesWithItem(item)

    def setDragPoint(self, dragPoint):
        topLeft = QtCore.QPointF(self.__mouseDownPos)
        bottomRight = QtCore.QPointF(dragPoint)
        if dragPoint.x() < self.__mouseDownPos.x():
            topLeft.setX(dragPoint.x())
            bottomRight.setX(self.__mouseDownPos.x())
        if dragPoint.y() < self.__mouseDownPos.y():
            topLeft.setY(dragPoint.y())
            bottomRight.setY(self.__mouseDownPos.y())
        self.setPos(topLeft)
        self.resize(bottomRight.x() - topLeft.x(),
                    bottomRight.y() - topLeft.y())

    def paint(self, painter, option, widget):
        rect = self.windowFrameRect()
        painter.setBrush(self.__backgroundColor)
        painter.setPen(self.__pen)
        painter.drawRect(rect)

    def destroy(self):
        self.view.removeItem(self)


class ViewManager(QtWidgets.QWidget):

    def __init__(self, widget, parent=None):
        super().__init__(parent)
        self.widget = widget  # FlowchartWidget
        self.chart = widget.chart  # Flowchart
        self.ctrl = widget.ctrl  # FlowchartCtrlWidget

        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)

        self.toolBar = QtWidgets.QToolBar(parent)
        self.graphGroup = QtWidgets.QActionGroup(parent)
        self.graphGroup.setExclusive(True)

        self.actions = {}
        self.actionRoot = QtWidgets.QAction("root", parent)
        self.actionRoot.subgraph = "root"
        self.actionRoot.triggered.connect(self.displayView)
        self.actionRoot.setCheckable(True)
        self.actionRoot.setChecked(True)
        self.toolBar.addAction(self.actionRoot)
        self.graphGroup.addAction(self.actionRoot)

        self.layout.addWidget(self.toolBar, 0, 0, 1, -1)

        self.views = {"root": FlowchartGraphicsView(widget, self, isRoot=True)}
        self.currentView = self.views["root"]
        self.layout.addWidget(self.currentView, 1, 0, -1, -1)

    def addView(self, nodes, name=None):
        graph = self.chart._graph

        if name is None:
            n = 0
            while True:
                name = f"combined.{n}"
                if name not in graph.nodes():
                    break
                n += 1

        view = FlowchartGraphicsView(self.widget, self)
        self.views[name] = view
        self.layout.addWidget(view, 1, 0, -1, -1)

        actionSubgraph = QtWidgets.QAction(name, self.parentWidget())
        actionSubgraph.subgraph = name
        actionSubgraph.setCheckable(True)
        actionSubgraph.triggered.connect(self.displayView)
        self.toolBar.addAction(actionSubgraph)
        self.graphGroup.addAction(actionSubgraph)
        self.actions[name] = actionSubgraph

        subgraphNode = SubgraphNode(name, allowAddInput=True, allowAddCondition=True)
        names = list(map(lambda node: node.name(), nodes))

        inputs = set()
        for fnode, tnode, data in graph.in_edges(names, data=True):
            if fnode in names and tnode in names:
                continue

            input_name = '.'.join([fnode, data['from_term']])
            if input_name not in inputs:
                fnode = graph.nodes[fnode]['node']
                subgraphNode.addInput(name=input_name, ttype=fnode.terminals[data['from_term']].type())
                inputs.add(input_name)

        outputs = set()
        for fnode, tnode, data in graph.out_edges(names, data=True):
            if fnode in names and tnode in names:
                continue

            output_name = '.'.join([fnode, data['from_term']])
            if output_name not in outputs:
                fnode = graph.nodes[fnode]['node']
                subgraphNode.addOutput(name=output_name, ttype=fnode.terminals[data['from_term']].type())
                outputs.add(output_name)

        if inputs:
            view.viewBox().addItem(subgraphNode.subgraphInputs().graphicsItem())
        if outputs:
            view.viewBox().addItem(subgraphNode.subgraphOutputs().graphicsItem())

        item = subgraphNode.graphicsItem()
        self.currentView.viewBox().addItem(item)
        item.moveBy(*nodes[0].graphicsItem().pos())

        for node in nodes:
            view.viewBox().addItem(node.graphicsItem())
            for name, term in node.terminals.items():
                for _, connection in term.connections().items():
                    view.viewBox().addItem(connection)
            node.recolor()

        actionSubgraph.trigger()

        self.ctrl.ui.actionPan.trigger()

    def displayView(self):
        sender = self.sender()
        if sender is None:
            return

        subgraph = sender.subgraph
        self.currentView.hide()
        self.currentView = self.views[subgraph]
        self.currentView.show()

    def removeView(self, name):
        pass

    def scene(self):
        return self.currentView.scene()

    def viewBox(self):
        return self.currentView.viewBox()


class FlowchartGraphicsView(GraphicsView):

    sigHoverOver = QtCore.Signal(object)
    sigClicked = QtCore.Signal(object)

    def __init__(self, widget, manager, isRoot=False, *args, **kwargs):
        super().__init__(*args, useOpenGL=False, background=0.75)
        self.widget = widget
        self.isRoot = isRoot
        self.setAcceptDrops(True)
        self._vb = FlowchartViewBox(widget, manager, isRoot=isRoot, lockAspect=True, invertY=True, **kwargs)
        self.setCentralItem(self._vb)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)

    def viewBox(self):
        return self._vb

    def dragEnterEvent(self, ev):
        ev.accept()

    def saveState(self):
        return self._vb.saveState()

    def restoreState(self, state):
        self._vb.restoreState(state)


class FlowchartViewBox(ViewBox):

    def __init__(self, widget, manager, isRoot=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget = widget
        self.chart = widget.chart
        self.manager = manager
        self.isRoot = isRoot

        self.setLimits(minXRange=200, minYRange=200,
                       xMin=-1000, yMin=-1000, xMax=5.2e3, yMax=5.2e3)
        self.addItem(GridItem())
        self.setAcceptDrops(True)
        self.setRange(xRange=(0, 800), yRange=(0, 800))
        self.mouseMode = "Pan"

        self.selectionRect = None
        self.selected_nodes = []

        self.copy = False
        self.paste_pos = None

        self.commentRect = None
        self.commentId = 0
        self.commentRects = {}

    def setMouseMode(self, mode):
        assert mode in ["Select", "Pan", "Comment"]
        self.mouseMode = mode

    def getMenu(self, ev):
        # called by ViewBox to create a new context menu
        self._fc_menu = QtGui.QMenu()
        self._subMenus = self.getContextMenus(ev)
        for menu in self._subMenus:
            self._fc_menu.addMenu(menu)

        if self.selected_nodes:
            self.selected_node_menu = QtGui.QMenu("Selection")
            if self.isRoot:
                self.selected_node_menu.addAction("Make Subgraph", self.makeSubgraph)
            if not self.copy:
                self.selected_node_menu.addAction("Copy", self.copySelectedNodes)
            else:
                self.selected_node_menu.addAction("Paste", self.pasteSelectedNodes)
                self.paste_pos = ev.pos()
            self.selected_node_menu.addAction("Delete", self.deleteSelectedNodes)
            self._fc_menu.addMenu(self.selected_node_menu)

        return self._fc_menu

    def copySelectedNodes(self):
        self.copy = True

    def pasteSelectedNodes(self):
        # TODO figure out right positions and preserve topology?
        pos = self.mapToView(self.paste_pos)

        for node in self.selected_nodes:
            self.widget.chart.createNode(type(node).__name__, pos=pos)
            pos += QtCore.QPointF(200, 0)

    def deleteSelectedNodes(self):
        for node in self.selected_nodes:
            node.close()

    def makeSubgraph(self):
        self.manager.addView(self.selected_nodes)

    def getContextMenus(self, ev):
        # called by scene to add menus on to someone else's context menu
        sourceMenu = self.widget.buildSourceMenu(ev.scenePos())
        sourceMenu.setTitle("Add Source")
        operationMenu = self.widget.buildOperationMenu(ev.scenePos())
        operationMenu.setTitle("Add Operation")
        return [sourceMenu, operationMenu, ViewBox.getMenu(self, ev)]

    def decode_data(self, arr):
        data = []
        item = {}

        ds = QtCore.QDataStream(arr)
        while not ds.atEnd():
            ds.readInt32()
            ds.readInt32()

            map_items = ds.readInt32()
            for i in range(map_items):

                key = ds.readInt32()

                value = QtCore.QVariant()
                ds >> value
                item[QtCore.Qt.ItemDataRole(key)] = value

                data.append(item)

        return data

    def mouseDragEvent(self, ev):
        ev.accept()

        if self.mouseMode == "Pan":
            super().mouseDragEvent(ev)

        elif self.mouseMode == "Select":
            if ev.isStart():
                self.selectionRect = SelectionRect(self, self.mapToView(ev.buttonDownPos()))

            if self.selectionRect:
                self.selectionRect.setDragPoint(self.mapToView(ev.pos()))

            if ev.isFinish():
                self.selected_nodes = []
                for item in self.allChildren():
                    if not isinstance(item, NodeGraphicsItem):
                        continue
                    if self.selectionRect.collidesWithItem(item):
                        item.node.recolor("selected")
                        self.selected_nodes.append(item.node)

                self.copy = False
                self.selectionRect.destroy()
                self.selectionRect = None

        elif self.mouseMode == "Comment":
            if ev.isStart() and self.commentRect is None:
                pos = clamp(self.mapToView(ev.buttonDownPos()))
                self.commentRect = CommentRect(self, pos, self.commentId)
                self.chart.sigNodeCreated.connect(self.commentRect.nodeCreated)
                self.commentId += 1

            if self.commentRect:
                pos = clamp(self.mapToView(ev.pos()))
                self.commentRect.setDragPoint(pos)

            if ev.isFinish():
                self.commentRects[self.commentRect.id] = self.commentRect

                for item in self.allChildren():
                    if isinstance(item, NodeGraphicsItem) and self.commentRect.collidesWithItem(item):
                        self.commentRect.childNodes.add(item)

                self.commentRect = None

    def mousePressEvent(self, ev):
        ev.accept()
        super().mousePressEvent(ev)

        if ev.button() == QtCore.Qt.LeftButton:
            for node in self.selected_nodes:
                node.recolor()

        children = filter(lambda item: isinstance(item, NodeGraphicsItem), self.allChildren())
        for id, comment in self.commentRects.items():
            comment.updateChildren(children)

    def dropEvent(self, ev):
        if ev.mimeData().hasFormat('application/x-qabstractitemmodeldatalist'):
            arr = ev.mimeData().data('application/x-qabstractitemmodeldatalist')
            node = self.decode_data(arr)[0][0].value()

            try:
                self.widget.chart.createNode(node, pos=self.mapToView(ev.pos()))
                ev.accept()
                return
            except KeyError:
                pass

            try:
                node_type = self.widget.chart.source_library.getSourceType(node)
                if node not in self.widget.chart._graph:
                    node = SourceNode(name=node, terminals={'Out': {'io': 'out', 'ttype': node_type}})
                    self.widget.chart.addNode(node=node, pos=self.mapToView(ev.pos()))
                    ev.accept()
                    return
            except KeyError:
                pass

        else:
            ev.ignore()

    def saveState(self):
        state = {'comments': []}

        for id, comment in self.commentRects.items():
            state['comments'].append(comment.saveState())

        return state

    def restoreState(self, state):
        self.commentId = 0
        for commentState in state['comments']:
            comment = CommentRect()
            comment.restoreState(commentState)
            self.addItem(comment)
            self.commentRects[commentState['id']] = comment
            self.commentId = max(commentState['id']+1, self.commentId)
