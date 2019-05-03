from ami.flowchart.library.DisplayWidgets import ScalarWidget, ScatterWidget, WaveformWidget, AreaDetWidget
from ami.flowchart.library.DisplayWidgets import HistogramWidget
from ami.flowchart.library.common import CtrlNode
from ami.nptype import Array1d, Array2d
from numbers import Real
import ami.graph_nodes as gn


class ScalarViewer(CtrlNode):

    """
    ScalarViewer displays the value of a scalar.

    Accepts float, int, bool, and np.float64.
    """

    nodeName = "ScalarViewer"
    uiTemplate = []

    def __init__(self, name):
        super(ScalarViewer, self).__init__(name,
                                           terminals={"In": {"io": "in", "type": Real}},
                                           viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(ScalarViewer, self).display(topics, addr, win, ScalarWidget, **kwargs)


class WaveformViewer(CtrlNode):

    """
    WaveformViewer displays 1D arrays.

    Accepts list and np.ndarray.
    """

    nodeName = "WaveformViewer"
    uiTemplate = []

    def __init__(self, name):
        super(WaveformViewer, self).__init__(name, terminals={"In": {"io": "in", "type": Array1d}},
                                             viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(WaveformViewer, self).display(topics, addr, win, WaveformWidget, **kwargs)


class ImageViewer(CtrlNode):

    """
    ImageViewer displays 2D arrays.

    Accepts np.ndarray.
    """

    nodeName = "ImageViewer"
    uiTemplate = []

    def __init__(self, name):
        super(ImageViewer, self).__init__(name, terminals={"In": {"io": "in", "type": Array2d}}, viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(ImageViewer, self).display(topics, addr, win, AreaDetWidget, **kwargs)


class Histogram(CtrlNode):

    """
    Histogram plots a histogram created from either Binning or BinByVar.

    Accepts dict.
    """

    nodeName = "Histogram"
    uiTemplate = []

    def __init__(self, name):
        super(Histogram, self).__init__(name,
                                        terminals={"In": {"io": "in", "type": dict}},
                                        allowAddInput=True,
                                        viewable=True)

    def display(self, topics, addr, win, **kwargs):
        return super(Histogram, self).display(topics, addr, win, HistogramWidget, **kwargs)


class ScatterPlot(CtrlNode):

    """
    Scatter Plot collects two scalars and plots them against each other.

    Accepts int, np.float64.
    """

    nodeName = "ScatterPlot"
    uiTemplate = [("Num Points", 'intSpin', {'value': 100, 'min': 1, 'max': 2147483647})]

    def __init__(self, name):
        super(ScatterPlot, self).__init__(name, terminals={"X": {"io": "in", "type": Real},
                                                           "Y": {"io": "in", "type": Real}},
                                          allowAddInput=True,
                                          buffered=True)

    def display(self, topics, addr, win, **kwargs):
        return super(ScatterPlot, self).display(topics, addr, win, ScatterWidget, **kwargs)

    def addInput(self, **args):
        self.addTerminal(name="X", io='in', **args)
        self.addTerminal(name="Y", io='in', **args)

    def to_operation(self, inputs, conditions={}):
        outputs = [gn.Var(name=self.name(), type=list)]
        node = gn.RollingBuffer(name=self.name()+"_operation", N=self.Num_Points,
                                conditions_needs=list(conditions.values()), inputs=list(inputs.values()),
                                outputs=outputs)
        return node


class LinePlot(CtrlNode):

    """
    Line Plot collects scalars and plots them.

    Accepts int, np.float64.
    """

    nodeName = "LinePlot"
    uiTemplate = [("Num Points", 'intSpin', {'value': 100, 'min': 1, 'max': 2147483647})]

    def __init__(self, name):
        super(LinePlot, self).__init__(name, terminals={"Y": {"io": "in", "type": Real}},
                                       allowAddInput=True,
                                       buffered=True)

    def addInput(self, **args):
        self.addTerminal(name="Y", io='in', **args)

    def display(self, topics, addr, win, **kwargs):
        return super(LinePlot, self).display(topics, addr, win, WaveformWidget, **kwargs)

    def to_operation(self, inputs, conditions={}):
        outputs = [gn.Var(name=self.name(), type=list)]
        node = gn.RollingBuffer(name=self.name()+"_operation", N=self.Num_Points,
                                conditions_needs=list(conditions.values()), inputs=list(inputs.values()),
                                outputs=outputs)
        return node
