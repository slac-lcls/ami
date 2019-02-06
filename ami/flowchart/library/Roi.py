from ami.flowchart.library.common import CtrlNode
from ami.comm import GraphCommHandler
from ami.graph_nodes import Map
from PyQt5.QtCore import pyqtSlot, QTimer
import pyqtgraph as pg


class AreaDetWidget(pg.ImageView):
    def __init__(self, name, topic, addr, parent=None):
        super(AreaDetWidget, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.comm_handler = GraphCommHandler(addr)
        self.timer = QTimer()
        self.timer.timeout.connect(self.get_image)
        self.timer.start(1000)
        self.roi.sigRegionChangeFinished.connect(self.roi_updated)

    @pyqtSlot()
    def get_image(self):
        reply = self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.image_updated(reply)
        else:
            print("failed to fetch %s from manager!" % self.topic)

    def image_updated(self, data):
        self.setImage(data)

    def roi_updated(self, roi):
        shape, vector, origin = roi.getAffineSliceParams(self.image, self.getImageItem())

        def roi_func(image):
            return pg.affineSlice(image, shape, origin, vector, (0, 1))

        self.func = roi_func


class Roi(CtrlNode):

    nodeName = "Roi"
    uiTemplate = []

    def __init__(self, name, addr):
        self.widget = None
        super(Roi, self).__init__(name, addr=addr)

    def display(self, name, topic):
        if self.win is None:
            self.win = pg.QtGui.QMainWindow()
            self.widget = AreaDetWidget(name, topic, self.addr, self.win)
            self.win.setWindowTitle(self.name())
            self.win.setCentralWidget(self.widget)
            self.win.show()
            self.show = True
        else:
            if self.show:
                self.win.hide()
            else:
                self.win.show()

            self.show = not self.show

    def to_operation(self):
        # this should be cleaned up at some point
        In = self.terminals['In'].inputTerminals()[0]

        if In.node().name() == "Input":
            inputs = [In.name()]
        else:
            inputs = [In.node().name()]

        outputs = [self.name()]

        if self.widget:
            func = self.widget.func
        else:
            def func(img):
                return img

        node = Map(name=self.name(), inputs=inputs, outputs=outputs, func=func)
        return node
