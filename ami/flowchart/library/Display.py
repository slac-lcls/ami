from ami.flowchart.library.DisplayWidgets import ScalarWidget, ScatterWidget, WaveformWidget, AreaDetWidget
from ami.flowchart.library.DisplayWidgets import HistogramWidget
from ami.flowchart.library.common import CtrlNode
import numpy as np
import ami.graph_nodes as gn


class ScalarViewer(CtrlNode):

    nodeName = "ScalarViewer"
    uiTemplate = []
    desc = "ScalarViewer"

    def __init__(self, name):
        super(ScalarViewer, self).__init__(name,
                                           terminals={"In": {"io": "in", "type": (float, int, bool, np.float64)}},
                                           viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(ScalarViewer, self).display(topics, addr, win, ScalarWidget, **kwargs)



class WaveformViewer(CtrlNode):

    nodeName = "WaveformViewer"
    uiTemplate = []
    desc = "WaveformViewer"

    def __init__(self, name):
        super(WaveformViewer, self).__init__(name, terminals={"In": {"io": "in", "type": np.ndarray}}, viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(WaveformViewer, self).display(topics, addr, win, WaveformWidget, **kwargs)


class ImageViewer(CtrlNode):

    nodeName = "ImageViewer"
    uiTemplate = []
    desc = "ImageViewer"

    def __init__(self, name):
        super(ImageViewer, self).__init__(name, terminals={"In": {"io": "in", "type": np.ndarray}}, viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(ImageViewer, self).display(topics, addr, win, AreaDetWidget, **kwargs)


class Histogram(CtrlNode):

    nodeName = "Histogram"
    uiTemplate = []
    desc = "Histogram"

    def __init__(self, name):
        super(Histogram, self).__init__(name,
                                        terminals={"In": {"io": "in", "type": dict}},
                                        allowAddInput=True,
                                        viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(Histogram, self).display(topics, addr, win, HistogramWidget, **kwargs)


class ScatterPlot(CtrlNode):

    nodeName = "ScatterPlot"
    uiTemplate = [("Num Points", 'intSpin', {'value': 100, 'min': 1, 'max': 2147483647})]
    desc = "Scatter Plot"

    def __init__(self, name):
        super(ScatterPlot, self).__init__(name, terminals={"X": {"io": "in", "type": (int, np.float64)},
                                                           "Y": {"io": "in", "type": (int, np.float64)}},
                                          allowAddInput=True,
                                          buffered=True)

    def display(self, topics, addr, win, **kwargs):
        return super(ScatterPlot, self).display(topics, addr, win, ScatterWidget, **kwargs)

    def addInput(self, **args):
        self.addTerminal(name="X", io='in', **args)
        self.addTerminal(name="Y", io='in', **args)

    def to_operation(self, inputs, conditions=[]):
        outputs = [gn.Var(name=self.name(), type=list)]
        node = gn.RollingBuffer(name=self.name()+"_operation", N=self.Num_Points,
                                conditions_needs=list(conditions.values()), inputs=list(inputs.values()),
                                outputs=outputs)
        return node


class LinePlot(CtrlNode):

    nodeName = "LinePlot"
    uiTemplate = [("Num Points", 'intSpin', {'value': 100, 'min': 1, 'max': 2147483647})]
    desc = "Waveform Plot"

    def __init__(self, name):
        super(LinePlot, self).__init__(name, terminals={"Y": {"io": "in", "type": (int, np.float64)}},
                                       allowAddInput=True,
                                       buffered=True)

    def addInput(self, **args):
        self.addTerminal(name="Y", io='in', **args)

    def display(self, topics, addr, win, **kwargs):
        return super(LinePlot, self).display(topics, addr, win, WaveformWidget, **kwargs)

    def to_operation(self, inputs, conditions=[]):
        outputs = [gn.Var(name=self.name(), type=list)]
        node = gn.RollingBuffer(name=self.name()+"_operation", N=self.Num_Points,
                                conditions_needs=list(conditions.values()), inputs=list(inputs.values()),
                                outputs=outputs)
        return node
