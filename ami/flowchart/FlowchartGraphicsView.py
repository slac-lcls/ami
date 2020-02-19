from pyqtgraph.Qt import QtGui, QtCore, QtWidgets
from pyqtgraph.widgets.GraphicsView import GraphicsView
from pyqtgraph.graphicsItems.ViewBox import ViewBox
from pyqtgraph import GridItem
# from ami.flowchart.Node import NodeGraphicsItem
from ami.flowchart.library.common import SourceNode
import asyncqt


class SelectionRect(QtWidgets.QGraphicsWidget):
    # Copyright 2015-2019 Ilgar Lunin, Pedro Cabrera
    # taken from pyflow
    __backgroundColor = QtGui.QColor(100, 100, 100, 50)
    __pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 1.0, QtCore.Qt.DashLine)

    def __init__(self, view, mouseDownPos):
        super(SelectionRect, self).__init__()
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
        return super(SelectionRect, self).collidesWithItem(item)

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


class FlowchartGraphicsView(GraphicsView):

    sigHoverOver = QtCore.Signal(object)
    sigClicked = QtCore.Signal(object)
    sigDragEnter = QtCore.Signal()

    def __init__(self, widget, *args):
        super().__init__(*args, useOpenGL=False, background=0.75)
        self.widget = widget
        self.setAcceptDrops(True)
        self._vb = FlowchartViewBox(widget, lockAspect=True, invertY=True)
        self.setCentralItem(self._vb)
        self.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self.sigDragEnter.connect(self.dragEnter)

    def viewBox(self):
        return self._vb

    def dragEnterEvent(self, ev):
        ev.accept()
        self.sigDragEnter.emit()

    @asyncqt.asyncSlot()
    async def dragEnter(self):
        await self.widget.chart.source_lock.acquire()


class FlowchartViewBox(ViewBox):

    def __init__(self, widget, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget = widget
        self.setLimits(minXRange=200, minYRange=200,
                       xMin=-1000, yMin=-1000, xMax=5.2e3, yMax=5.2e3)
        self.addItem(GridItem())
        self.setAcceptDrops(True)
        self.setRange(xRange=(0, 800), yRange=(0, 800))
        self.mouseMode = "Pan"
        self.selectionRect = None

    def setMouseMode(self, mode):
        assert mode in ["Select", "Pan"]
        self.mouseMode = mode

    def getMenu(self, ev):
        # called by ViewBox to create a new context menu
        self._fc_menu = QtGui.QMenu()
        self._subMenus = self.getContextMenus(ev)
        for menu in self._subMenus:
            self._fc_menu.addMenu(menu)
        return self._fc_menu

    def getContextMenus(self, ev):
        # called by scene to add menus on to someone else's context menu
        menu = self.widget.buildMenu(ev.scenePos())
        menu.setTitle("Add Operation")
        return [menu, ViewBox.getMenu(self, ev)]

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
                # nodes = list(filter(lambda item: isinstance(item, NodeGraphicsItem), self.allChildren()))
                # selected_nodes = list(map(self.collidesWithItem, nodes))
                self.selectionRect.destroy()
                self.selectionRect = None

    def dropEvent(self, ev):
        if ev.mimeData().hasFormat('application/x-qabstractitemmodeldatalist'):
            arr = ev.mimeData().data('application/x-qabstractitemmodeldatalist')
            node = self.decode_data(arr)[0][0].value()
            try:
                self.widget.chart.createNode(node, pos=self.mapToView(ev.pos()))
                ev.accept()
                self.widget.chart.source_lock.release()
                return
            except KeyError:
                pass

            try:
                node_type = self.widget.chart.source_library.getSourceType(node)
                if node not in self.widget.chart._graph:
                    node = SourceNode(name=node, terminals={'Out': {'io': 'out', 'ttype': node_type}})
                    # self.widget.chart.addNode(node, name=nodeType, pos=self.mapToView(ev.pos()))
                    self.widget.chart.createNode(node_type, name=node.name(), node=node, pos=self.mapToView(ev.pos()))
                    ev.accept()
                    self.widget.chart.source_lock.release()
                    return
            except KeyError:
                pass

        else:
            ev.ignore()

        self.widget.chart.source_lock.release()
