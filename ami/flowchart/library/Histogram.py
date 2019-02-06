from ami.flowchart.library.common import CtrlNode
from ami.comm import GraphCommHandler
from PyQt5.QtCore import pyqtSlot, QTimer
import pyqtgraph as pg


class WaveformWidget(pg.GraphicsLayoutWidget):
    def __init__(self, name, topic, addr, parent=None):
        super(__class__, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.timer = QTimer()
        self.comm_handler = GraphCommHandler(addr)
        self.plot_view = self.addPlot()
        self.plot = None
        self.timer.timeout.connect(self.get_waveform)
        self.timer.start(1000)

    @pyqtSlot()
    def get_waveform(self):
        reply = self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.waveform_updated(reply)
        else:
            print("failed to fetch %s from manager!", self.topic)

    def waveform_updated(self, data):
        if self.plot is None:
            x, y = (list(data.keys()), list(data.values()))
            self.plot = self.plot_view.plot(x, y)
        else:
            self.plot.setData(y=list(data.values()))


class Histogram(CtrlNode):

    nodeName = "Histogram"
    uiTemplate = []

    def __init__(self, name, addr):
        super(Histogram, self).__init__(name, addr=addr, terminals={"In": {"io": "in"}})

    def display(self, name, topic):
        if self.win is None:
            self.win = pg.QtGui.QMainWindow()
            self.widget = WaveformWidget(name, topic, self.addr, self.win)
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
