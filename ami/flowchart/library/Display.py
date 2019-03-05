from ami.flowchart.library.DisplayWidgets import ScalarWidget, ScatterWidget, AreaDetWidget, HistogramWidget
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

    def display(self, topics, addr, win):
        return super(ScalarViewer, self).display(topics, addr, win, ScalarWidget)


class ImageViewer(CtrlNode):

    nodeName = "ImageViewer"
    uiTemplate = []
    desc = "ImageViewer"

    def __init__(self, name):
        super(ImageViewer, self).__init__(name, terminals={"In": {"io": "in", "type": np.ndarray}}, viewable=True)

    def display(self, topics, addr, win):
        return super(ImageViewer, self).display(topics, addr, win, AreaDetWidget)


class Histogram(CtrlNode):

    nodeName = "Histogram"
    uiTemplate = []
    desc = "Histogram"

    def __init__(self, name):
        super(Histogram, self).__init__(name,
                                        terminals={"In": {"io": "in", "type": dict}},
                                        allowAddInput=True,
                                        viewable=True)

    def display(self, topics, addr, win):
        return super(Histogram, self).display(topics, addr, win, HistogramWidget)


class ScatterPlot(CtrlNode):

    nodeName = "ScatterPlot"
    uiTemplate = []
    desc = "Scatter Plot"

    def __init__(self, name):
        super(ScatterPlot, self).__init__(name, terminals={"X": {"io": "in", "type": (int, np.float64)},
                                                           "Y": {"io": "in", "type": (int, np.float64)}},
                                          viewable=True)

    def display(self, topics, addr, win):
        return super(ScatterPlot, self).display(topics, addr, win, ScatterWidget)
