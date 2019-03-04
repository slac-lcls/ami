from ami.flowchart.library.DisplayWidgets import ScalarWidget, WaveformWidget, AreaDetWidget
from ami.flowchart.library.common import CtrlNode
import numpy as np


class ScalarViewer(CtrlNode):

    nodeName = "ScalarViewer"
    uiTemplate = []
    desc = "ScalarViewer"

    def __init__(self, name):
        super(ScalarViewer, self).__init__(name,
                                           terminals={"In": {"io": "in", "type": (float, int, bool, np.float64)}},
                                           viewable=True)

    def display(self, inputs, addr, win):
        return super(ScalarViewer, self).display(inputs, addr, win, ScalarWidget)


class ImageViewer(CtrlNode):

    nodeName = "ImageViewer"
    uiTemplate = []
    desc = "ImageViewer"

    def __init__(self, name):
        super(ImageViewer, self).__init__(name, terminals={"In": {"io": "in", "type": np.ndarray}}, viewable=True)

    def display(self, inputs, addr, win):
        return super(ImageViewer, self).display(inputs, addr, win, AreaDetWidget)


class Histogram(CtrlNode):

    nodeName = "Histogram"
    uiTemplate = []
    desc = "Histogram"

    def __init__(self, name):
        super(Histogram, self).__init__(name, terminals={"In": {"io": "in", "type": dict}}, viewable=True)

    def display(self, inputs, addr, win):
        return super(Histogram, self).display(inputs, addr, win, WaveformWidget)
