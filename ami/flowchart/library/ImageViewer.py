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

    @pyqtSlot()
    def get_image(self):
        reply = self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.image_updated(reply)
        else:
            print("failed to fetch %s from manager!" % self.topic)

    def image_updated(self, data):
        self.setImage(data)


class ImageViewer(CtrlNode):

    nodeName = "ImageViewer"
    uiTemplate = []

    def __init__(self, name):
        super(ImageViewer, self).__init__(name, terminals={"In": {"io": "in"}}, viewable=True)

    def display(self, inputs, addr, win):
        name, topic = inputs[0]
        self.widget = AreaDetWidget(name, topic, addr, self.win)
        return self.widget
