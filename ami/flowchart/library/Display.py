from ami.flowchart.library.DisplayWidgets import ScalarWidget, WaveformWidget, AreaDetWidget
from ami.flowchart.library.common import CtrlNode


class ScalarViewer(CtrlNode):

    nodeName = "ScalarViewer"
    uiTemplate = []

    def __init__(self, name):
        super(ScalarViewer, self).__init__(name, terminals={"In": {"io": "in"}}, viewable=True)

    def display(self, inputs, addr, win):
        return super(ScalarViewer, self).display(inputs, addr, win, ScalarWidget)


class ImageViewer(CtrlNode):

    nodeName = "ImageViewer"
    uiTemplate = []

    def __init__(self, name):
        super(ImageViewer, self).__init__(name, terminals={"In": {"io": "in"}}, viewable=True)

    def display(self, inputs, addr, win):
        return super(ImageViewer, self).display(inputs, addr, win, AreaDetWidget)


class Histogram(CtrlNode):

    nodeName = "Histogram"
    uiTemplate = []

    def __init__(self, name):
        super(Histogram, self).__init__(name, terminals={"In": {"io": "in"}}, viewable=True)

    def display(self, inputs, addr, win):
        return super(Histogram, self).display(inputs, addr, win, WaveformWidget)
