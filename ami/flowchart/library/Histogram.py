from ami.flowchart.library.DisplayWidgets import WaveformWidget
from ami.flowchart.library.common import CtrlNode
import asyncio


class Histogram(CtrlNode):

    nodeName = "Histogram"
    uiTemplate = []

    def __init__(self, name):
        super(Histogram, self).__init__(name, terminals={"In": {"io": "in"}}, viewable=True)

    def display(self, inputs, addr, win):
        name, topic = inputs[0]
        if self.widget is None:
            self.widget = WaveformWidget(name, topic, addr, win)
            self.task = asyncio.ensure_future(self.widget.update())
        return self.widget
