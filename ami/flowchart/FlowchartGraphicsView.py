from pyqtgraph import GraphicsWidget, GridItem
from pyqtgraph.graphicsItems.ViewBox import ViewBox
from pyqtgraph.widgets.GraphicsView import GraphicsView
from qtpy import QtCore, QtGui, QtWidgets

from ami.flowchart.library.common import SourceNode
from ami.flowchart.library.Editors import STYLE
from ami.flowchart.Node import NodeGraphicsItem, find_nearest
from ami.flowchart.SubgraphNode import SubgraphNode


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
        self.headerLayout = QtWidgets.QGraphicsLinearLayout(QtCore.Qt.Horizontal)
        self.commentName = CommentName(parent=self)
        self.headerLayout.addItem(self.commentName)
        self.__mouseDownPos = mouseDownPos
        self.setPos(self.__mouseDownPos)
        self.resize(0, 0)
        self.childNodes = set()
        self._resizing = False
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)
        self.buildMenu()
        if view:
            self.view = view
            self.view.addItem(self)

    def collidesWithItem(self, item):
        # Use center-point containment: node moves with box if its center is inside
        return self.sceneBoundingRect().contains(item.sceneBoundingRect().center())

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
        self.resize(max(bottomRight.x() - topLeft.x(), 100), max(bottomRight.y() - topLeft.y(), 100))

    def paint(self, painter, option, widget):
        rect = self.windowFrameRect()
        painter.setBrush(self.__backgroundColor)
        painter.setPen(self.__pen)
        painter.drawRect(rect)

        # Draw a small triangle grip in the bottom-right corner as a resize handle
        handle_size = 12
        x = rect.right()
        y = rect.bottom()
        path = QtGui.QPainterPath()
        path.moveTo(x, y - handle_size)
        path.lineTo(x, y)
        path.lineTo(x - handle_size, y)
        path.closeSubpath()
        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 160)))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPath(path)

    def destroy(self):
        # Disconnect the sigNodeCreated signal to prevent a leak
        try:
            self.view.chart.sigNodeCreated.disconnect(self.nodeCreated)
        except (TypeError, RuntimeError):
            pass
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
            ev.accept()

            if ev.isStart():
                # Refresh childNodes at drag start to prevent stale tracking
                children = [item for item in self.view.allChildren() if isinstance(item, NodeGraphicsItem)]
                self.updateChildren(children)

                # Determine resize vs move based on hit zone
                br = self.boundingRect()
                handle_rect = QtCore.QRectF(br.width() - 50, br.height() - 50, 50, 50)
                self._resizing = handle_rect.contains(ev.pos())
                if self._resizing:
                    # Fix anchor to current top-left so resize works after moves
                    self.__mouseDownPos = self.pos()

            if self._resizing:
                drag_pt = clamp(self.mapToParent(ev.pos()))
                self.setDragPoint(drag_pt)
            else:
                pos = self.pos() + self.mapToParent(ev.pos()) - self.mapToParent(ev.lastPos())
                old_pos = self.pos()
                if ev.isFinish():
                    pos = clamp(pos)
                self.setPos(pos)
                diff = pos - old_pos
                for child in self.childNodes:
                    child.moveBy(*diff)

    def hoverMoveEvent(self, ev):
        br = self.boundingRect()
        if QtCore.QRectF(br.width() - 50, br.height() - 50, 50, 50).contains(ev.pos()):
            self.setCursor(QtCore.Qt.SizeFDiagCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
        ev.accept()

    def hoverLeaveEvent(self, ev):
        self.setCursor(QtCore.Qt.ArrowCursor)
        ev.accept()

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            ev.accept()
            self.setFocus()
        elif ev.button() == QtCore.Qt.RightButton:
            ev.accept()
            self.raiseContextMenu(ev)

    def keyPressEvent(self, ev):
        if ev.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            ev.accept()
            self.destroy()
        else:
            ev.ignore()

    def buildMenu(self):
        self.menu = QtWidgets.QMenu()
        self.menu.setTitle("Comment")
        self.menu.addAction("Remove Comment\tDel", self.destroy)

    def raiseContextMenu(self, ev):
        menu = self.scene().addParentContextMenus(self, self.menu, ev)
        pos = ev.screenPos()
        menu.popup(QtCore.QPoint(pos.x(), pos.y()))

    def saveState(self):
        rect = self.sceneBoundingRect()
        topLeft = clamp(self.view.mapToView(rect.topLeft()))
        bottomRight = clamp(self.view.mapToView(rect.bottomRight()))
        return {
            "id": self.id,
            "text": self.commentName.text(),
            "topLeft": (topLeft.x(), topLeft.y()),
            "bottomRight": (bottomRight.x(), bottomRight.y()),
        }

    def restoreState(self, state):
        self.id = state["id"]
        self.commentName.setText(state["text"])
        self.__mouseDownPos = QtCore.QPointF(*state["topLeft"])
        self.setDragPoint(QtCore.QPointF(*state["bottomRight"]))


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
        self.resize(bottomRight.x() - topLeft.x(), bottomRight.y() - topLeft.y())

    def paint(self, painter, option, widget):
        rect = self.windowFrameRect()
        painter.setBrush(self.__backgroundColor)
        painter.setPen(self.__pen)
        painter.drawRect(rect)

    def destroy(self):
        self.view.removeItem(self)


class ViewManager(QtWidgets.QWidget):

    sigViewAdded = QtCore.Signal(object)
    sigMakeSubgraphFromSelection = QtCore.Signal(object)

    def __init__(self, widget, parent=None):
        super().__init__(parent)
        self.widget = widget  # FlowchartWidget
        self.chart = widget.chart  # Flowchart
        self.ctrl = widget.ctrl  # FlowchartCtrlWidget

        self.layout = QtWidgets.QGridLayout()
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
        self.previousView = None
        self._currentSubgraphName = None
        self.layout.addWidget(self.currentView, 1, 0, -1, -1)

        # Shared clipboard for copy/cut/paste across all views
        # Format: {"nodes": [{"class": str, "name": str, "state": dict}, ...],
        #          "connects": [(from_name, from_term, to_name, to_term), ...]}
        self.clipboard = {}

    def addView(self, name):
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

        self.sigViewAdded.emit(view)

        return view

    def displayView(self, checked=False, name=None, autoRange=False):
        if name is None:
            sender = self.sender()
            if sender is None:
                return

            name = sender.subgraph
        else:
            # Set the appropriate action as checked
            if name == "root":
                self.actionRoot.setChecked(True)
            elif name in self.actions:
                self.actions[name].setChecked(True)

        self.previousView = self.currentView
        self.currentView.hide()
        self.currentView = self.views[name]
        self._currentSubgraphName = name if name != "root" else None
        self.currentView.show()

        self.ctrl.ui.actionPan.trigger()

        if autoRange:
            children = self.currentView.viewBox().allChildren()
            self.currentView.viewBox().autoRange(items=children)

    def removeView(self, name):
        # Get the view widget
        view = self.views[name]

        # Remove from layout
        self.layout.removeWidget(view)

        # Delete the widget
        view.deleteLater()

        # Remove from tracking
        del self.views[name]

        # Remove action from toolbar and group
        action = self.actions[name]
        self.graphGroup.removeAction(action)
        self.toolBar.removeAction(action)
        del self.actions[name]

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
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def viewBox(self):
        return self._vb

    def dragEnterEvent(self, ev):
        ev.accept()

    def mousePressEvent(self, ev):
        self.setFocus()
        super().mousePressEvent(ev)

    def keyPressEvent(self, ev):
        key = ev.key()
        mods = ev.modifiers()

        if key == QtCore.Qt.Key_C and mods & QtCore.Qt.ControlModifier:
            self._vb.copySelectedNodes()
            ev.accept()
        elif key == QtCore.Qt.Key_X and mods & QtCore.Qt.ControlModifier:
            self._vb.cutSelectedNodes()
            ev.accept()
        elif key == QtCore.Qt.Key_V and mods & QtCore.Qt.ControlModifier:
            if self._vb.manager.clipboard:
                self._vb.pasteSelectedNodes()
            ev.accept()
        elif key == QtCore.Qt.Key_A and mods & QtCore.Qt.ControlModifier:
            for item in self._vb.allChildren():
                if isinstance(item, NodeGraphicsItem):
                    if item.node not in self._vb.selected_nodes:
                        self._vb.selected_nodes.append(item.node)
                        item.node.recolor("selected")
                        item.setSelected(True)
            ev.accept()
        elif key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace) and self._vb.selected_nodes:
            self._vb.deleteSelectedNodes()
            ev.accept()
        else:
            super().keyPressEvent(ev)

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

        if "Background" in STYLE:
            self.setBackgroundColor(STYLE["Background"])

        self.setLimits(minXRange=200, minYRange=200, xMin=-1000, yMin=-1000, xMax=5.2e3, yMax=5.2e3)
        self.addItem(GridItem())
        self.setAcceptDrops(True)
        self.setRange(xRange=(0, 800), yRange=(0, 800))
        self.mouseMode = "Pan"

        self.selectionRect = None
        self.selected_nodes = []

        self.mouse_pos = None

        self.commentRect = None
        self.commentId = 0
        self.commentRects = {}

    def setMouseMode(self, mode):
        assert mode in ["Select", "Pan", "Comment"]
        self.mouseMode = mode

    def getMenu(self, ev):
        # called by ViewBox to create a new context menu
        self._fc_menu = QtWidgets.QMenu()
        self._subMenus = self.getContextMenus(ev)
        for menu in self._subMenus:
            self._fc_menu.addMenu(menu)

        if self.selected_nodes:
            self.selected_node_menu = QtWidgets.QMenu("Selection")
            if self.isRoot:
                self.selected_node_menu.addAction("Make Subgraph", self.makeSubgraphFromSelection)
            self.selected_node_menu.addAction("Copy\tCtrl+C", self.copySelectedNodes)
            self.selected_node_menu.addAction("Cut\tCtrl+X", self.cutSelectedNodes)
            paste_pos = ev.pos()
            paste_action = self.selected_node_menu.addAction(
                "Paste\tCtrl+V", lambda: self.pasteSelectedNodes(pos=paste_pos)
            )
            paste_action.setEnabled(bool(self.manager.clipboard))
            self.selected_node_menu.addSeparator()
            self.selected_node_menu.addAction("Delete\tDel", self.deleteSelectedNodes)
            self._fc_menu.addMenu(self.selected_node_menu)
        elif self.manager.clipboard:
            # Show Paste on empty canvas when clipboard has content
            paste_pos = ev.pos()
            self._fc_menu.addAction("Paste\tCtrl+V", lambda: self.pasteSelectedNodes(pos=paste_pos))

        self.mouse_pos = self.mapToView(ev.pos())
        return self._fc_menu

    def _buildClipboard(self, nodes_to_copy):
        """Populate the shared clipboard from a list of Node objects."""
        selected_names = {n.name() for n in nodes_to_copy}
        nodes_data = [{"class": type(n).__name__, "name": n.name(), "state": n.saveState()} for n in nodes_to_copy]
        connects = []
        for from_name, to_name, data in self.chart._graph.edges(data=True):
            if from_name in selected_names and to_name in selected_names:
                connects.append((from_name, data["from_term"], to_name, data["to_term"]))
        self.manager.clipboard = {"nodes": nodes_data, "connects": connects}

    def copySelectedNodes(self):
        nodes_to_copy = list(self.selected_nodes)
        if not nodes_to_copy:
            # Fall back to Qt scene selection (handles single-click selections)
            nodes_to_copy = [
                item.node for item in (self.scene().selectedItems() or []) if isinstance(item, NodeGraphicsItem)
            ]
        if nodes_to_copy:
            self._buildClipboard(nodes_to_copy)

    def cutSelectedNodes(self):
        self.copySelectedNodes()
        self.deleteSelectedNodes()

    def copyNode(self, node):
        """Copy a single node (used from the per-node right-click menu)."""
        self._buildClipboard([node])

    def cutNode(self, node):
        """Cut a single node (used from the per-node right-click menu)."""
        self.copyNode(node)
        node.close()

    def pasteSelectedNodes(self, pos=None):
        """Paste nodes from the clipboard, restoring state and connections."""
        from pyqtgraph.debug import printExc

        if not self.manager.clipboard:
            return

        nodes_data = self.manager.clipboard.get("nodes", [])
        connects = self.manager.clipboard.get("connects", [])

        if not nodes_data:
            return

        # Compute paste origin
        if pos is not None:
            paste_origin = self.mapToView(pos)
        else:
            xr, yr = self.viewRange()
            paste_origin = QtCore.QPointF((xr[0] + xr[1]) / 2, (yr[0] + yr[1]) / 2)

        # Compute bounding-box top-left of original positions
        orig_positions = [n["state"].get("pos", (0, 0)) for n in nodes_data]
        min_x = min(p[0] for p in orig_positions)
        min_y = min(p[1] for p in orig_positions)

        # Create nodes and build name mapping
        name_mapping = {}
        for node_info in nodes_data:
            orig_name = node_info["name"]
            class_name = node_info["class"]
            state = dict(node_info["state"])

            # Compute new position relative to paste origin, preserving relative layout
            orig_pos = state.get("pos", (0, 0))

            new_x = find_nearest(paste_origin.x() + (orig_pos[0] - min_x))
            new_y = find_nearest(paste_origin.y() + (orig_pos[1] - min_y))
            new_x = max(min(new_x, 5000), 0)
            new_y = max(min(new_y, 5000), -900)

            try:
                new_node = self.widget.chart.createNode(class_name, pos=QtCore.QPointF(new_x, new_y), prompt=False)
                state["pos"] = (new_x, new_y)
                new_node.restoreState(state)
                name_mapping[orig_name] = new_node.name()
            except Exception:
                printExc(f"Error pasting node {orig_name} of type {class_name}")
                continue

        # Restore intra-selection connections
        for from_name, from_term, to_name, to_term in connects:
            if from_name not in name_mapping or to_name not in name_mapping:
                continue
            try:
                new_from = name_mapping[from_name]
                new_to = name_mapping[to_name]
                from_node_obj = self.widget.chart._graph.nodes[new_from]["node"]
                to_node_obj = self.widget.chart._graph.nodes[new_to]["node"]

                if from_term not in from_node_obj.terminals or to_term not in to_node_obj.terminals:
                    continue

                term1 = from_node_obj.terminals[from_term]
                term2 = to_node_obj.terminals[to_term]
                term1.connectTo(term2, signal=True)

                self.widget.chart._graph.add_edge(
                    new_from,
                    new_to,
                    key=f"{new_from}.{from_term}->{new_to}.{to_term}",
                    from_term=from_term,
                    to_term=to_term,
                )
            except Exception:
                printExc(f"Error restoring connection {from_name}.{from_term} -> {to_name}.{to_term}")
                continue

    def deleteSelectedNodes(self):
        nodes = list(self.selected_nodes)
        self.selected_nodes = []
        for node in nodes:
            node.close()

    def makeSubgraphFromSelection(self):
        nodes = self.selected_nodes

        # Prevent empty subgraphs
        if not nodes:
            msg = QtWidgets.QMessageBox()
            msg.setText("Cannot create empty subgraph. Select at least one node.")
            msg.exec()
            return

        # Prevent nested subgraphs
        for node in nodes:
            if isinstance(node, SubgraphNode):
                msg = QtWidgets.QMessageBox()
                msg.setText("Cannot create nested subgraphs. SubgraphNode cannot be inside another subgraph.")
                msg.exec()
                return
            # Also check the class name for safety
            if node.__class__.__name__ == "SubgraphNode":
                msg = QtWidgets.QMessageBox()
                msg.setText("Cannot create nested subgraphs.")
                msg.exec()
                return

        self.manager.sigMakeSubgraphFromSelection.emit(nodes)

    def getContextMenus(self, ev):
        # called by scene to add menus on to someone else's context menu
        sourceMenu = self.widget.buildSourceMenu(ev.scenePos())
        sourceMenu.setTitle("Add Source")
        operationMenu = self.widget.buildOperationMenu(ev.scenePos())
        operationMenu.setTitle("Add Operation")
        return [sourceMenu, operationMenu, ViewBox.getMenu(self, ev)]

    def decode_data(self, arr):
        data = QtCore.QMimeData()
        data.setData("application/x-qabstractitemmodeldatalist", arr)
        source_item = QtGui.QStandardItemModel()
        source_item.dropMimeData(data, QtCore.Qt.CopyAction, 0, 0, QtCore.QModelIndex())
        return source_item.item(0, 0).text()
        # data = []
        # item = {}

        # ds = QtCore.QDataStream(arr)
        # while not ds.atEnd():
        #     ds.readInt32()
        #     ds.readInt32()

        #     map_items = ds.readInt32()
        #     for i in range(map_items):

        #         key = ds.readInt32()

        #         value = QtCore.QVariant()
        #         ds >> value
        #         item[QtCore.Qt.ItemDataRole(key)] = value

        #         data.append(item)

        # return data

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
                node.recolor(None)
                node.graphicsItem().setSelected(False)
            self.selected_nodes = []

        children = list(filter(lambda item: isinstance(item, NodeGraphicsItem), self.allChildren()))
        for id, comment in self.commentRects.items():
            comment.updateChildren(children)

    def dropEvent(self, ev):
        if ev.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            # arr = ev.mimeData().data('application/x-qabstractitemmodeldatalist')
            # node = self.decode_data(arr)[0][0].value()
            arr = ev.mimeData().data("application/x-qabstractitemmodeldatalist")
            node = self.decode_data(arr)

            try:
                self.widget.chart.createNode(node, pos=self.mapToView(ev.pos()), prompt=True)
                ev.accept()
                return
            except KeyError:
                pass

            try:
                node_type = self.widget.chart.source_library.getSourceType(node)
                if node not in self.widget.chart._graph:
                    node = SourceNode(
                        name=node, terminals={"Out": {"io": "out", "ttype": node_type}}, flowchart=self.widget.chart
                    )
                    self.widget.chart.addNode(node=node, pos=self.mapToView(ev.pos()))
                    ev.accept()
                    return
            except KeyError:
                pass

            # Try subgraph library
            try:
                if self.widget.chart.subgraph_library.hasSubgraph(node):
                    result = self.widget.chart.instantiateSubgraphFromLibrary(node, pos=self.mapToView(ev.pos()))
                    if result:
                        ev.accept()
                        return
            except Exception as e:
                print(f"Error instantiating subgraph from library: {e}")
                import traceback

                traceback.print_exc()
                pass

        else:
            ev.ignore()

    def saveState(self):
        state = {"comments": []}

        for id, comment in self.commentRects.items():
            state["comments"].append(comment.saveState())

        return state

    def restoreState(self, state):
        self.commentId = 0
        for commentState in state["comments"]:
            comment = CommentRect(view=self)
            comment.restoreState(commentState)
            self.addItem(comment)
            self.commentRects[commentState["id"]] = comment
            self.commentId = max(commentState["id"] + 1, self.commentId)
