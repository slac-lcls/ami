from ami.flowchart.library.DisplayWidgets import AreaDetWidget
from ami.flowchart.library.common import CtrlNode
import asyncio


class ImageViewer(CtrlNode):

    nodeName = "ImageViewer"
    uiTemplate = []

    def __init__(self, name):
        super(ImageViewer, self).__init__(name, terminals={"In": {"io": "in"}}, viewable=True)

    def display(self, inputs, addr, win):
        name, topic = inputs[0]
        if self.widget is None:
            self.widget = AreaDetWidget(name, topic, addr, win)
            self.task = asyncio.ensure_future(self.widget.update())
        return self.widget
