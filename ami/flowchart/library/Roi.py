from ami.flowchart.library.common import CtrlNode
from ami.comm import GraphCommHandler
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

    # @pyqtSlot(pg.ROI)
    def roi_updated(self, roi):
        shape, vector, origin = roi.getAffineSliceParams(self.image, self.getImageItem())

        def roi_func(image):
            return pg.affineSlice(image, shape, origin, vector, (0, 1))

        self.comm_handler.map("map_%s_roi" % self.name,
                              inputs=[self.name],
                              outputs=["%s_roi" % self.name],
                              func=roi_func)


class Roi(CtrlNode):

    nodeName = "Roi"
    uiTemplate = [
        ('row', 'intSpin', {'min': 0, 'max': 1024}),
        ('col', 'intSpin', {'min': 0, 'max': 1024})
    ]

    def display(self, name, topic):
        self.win = pg.QtGui.QMainWindow()
        widget = AreaDetWidget(name, topic, self.addr, self.win)
        self.win.setWindowTitle(name)
        self.win.setCentralWidget(widget)
        self.win.show()
