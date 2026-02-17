from ami.flowchart.library.DisplayWidgets import ScalarWidget, ScatterWidget, WaveformWidget, \
    ImageWidget, ObjectWidget, LineWidget, TimeWidget, HistogramWidget, \
    Histogram2DWidget, MultiWaveformWidget
from ami.flowchart.library.common import CtrlNode
from amitypes import Array1d, Array2d, MultiChannelWaveform
from typing import Any
import ami.graph_nodes as gn


class ScalarViewer(CtrlNode):

    """
    ScalarViewer displays the value of a scalar.
    """

    nodeName = "ScalarViewer"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name,
                         terminals={"In": {"io": "in", "ttype": float}},
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, ScalarWidget, **kwargs)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'ScalarWidget', 'terms': terms, 'topics': topics}


class WaveformViewer(CtrlNode):

    """
    WaveformViewer displays 1D arrays.
    """

    nodeName = "WaveformViewer"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name, terminals={"In": {"io": "in", "ttype": Array1d}},
                         allowAddInput=True,
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, WaveformWidget, **kwargs)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'WaveformWidget', 'terms': terms, 'topics': topics}


class MultiWaveformViewer(CtrlNode):

    """
    MultiWaveformViewer displays 2D arrays as series of 1D arrays.
    """

    nodeName = "MultiWaveformViewer"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name, terminals={"In": {"io": "in", "ttype": MultiChannelWaveform}},
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, MultiWaveformWidget, **kwargs)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'MultiWaveformWidget', 'terms': terms, 'topics': topics}


class ImageViewer(CtrlNode):

    """
    ImageViewer displays 2D arrays.
    """

    nodeName = "ImageViewer"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name, terminals={"In": {"io": "in", "ttype": Array2d}}, viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, ImageWidget, **kwargs)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'ImageWidget', 'terms': terms, 'topics': topics}


class ObjectViewer(CtrlNode):

    """
    ObjectViewer displays string representation of a python object.
    """

    nodeName = "ObjectViewer"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name, terminals={"In": {"io": "in", "ttype": Any}}, viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, ObjectWidget, **kwargs)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'ObjectWidget', 'terms': terms, 'topics': topics}


class Histogram(CtrlNode):

    """
    Histogram plots a histogram created from Binning.
    """

    nodeName = "Histogram"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name,
                         terminals={"Bins": {"io": "in", "ttype": Array1d},
                                    "Counts": {"io": "in", "ttype": Array1d}},
                         allowAddInput=True,
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, HistogramWidget, **kwargs)

    def addInput(self, **args):
        self.addTerminal(name="Bins", io='in', ttype=Array1d, **args)
        self.addTerminal(name="Counts", io='in', ttype=Array1d, **args)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'HistogramWidget', 'terms': terms, 'topics': topics}


class Histogram2D(CtrlNode):

    """
    Histogram2D plots a 2d histogram created from Binning2D.
    """

    nodeName = "Histogram2D"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name,
                         terminals={"XBins": {"io": "in", "ttype": Array1d},
                                    "YBins": {"io": "in", "ttype": Array1d},
                                    "Counts": {"io": "in", "ttype": Array2d}},
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, Histogram2DWidget, **kwargs)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'Histogram2DWidget', 'terms': terms, 'topics': topics}


class ScatterPlot(CtrlNode):

    """
    Scatter Plot collects two scalars and plots them against each other.
    """

    nodeName = "ScatterPlot"
    uiTemplate = [("Num Points", 'intSpin', {'value': 100, 'min': 1}),
                  ('Unique', 'check')]

    def __init__(self, name):
        super().__init__(name, terminals={"X": {"io": "in", "ttype": float},
                                          "Y": {"io": "in", "ttype": float}},
                         allowAddInput=True,
                         buffered=True)

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, ScatterWidget, **kwargs)

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

    def addInput(self, **args):
        self.addTerminal(name="X", io='in', ttype=float, **args)
        self.addTerminal(name="Y", io='in', ttype=float, **args)

    def to_operation(self, inputs, outputs, **kwargs):
        outputs = [self.name()+'.'+i for i in inputs.keys()]
        buffer_output = [self.name()+"_count", self.name()+"_buffered"]
        nodes = [gn.RollingBuffer(name=self.name()+"_buffer",
                                  N=self.values['Num Points'], unique=self.values['Unique'],
                                  inputs=inputs, outputs=buffer_output, **kwargs),
                 gn.Map(name=self.name()+"_operation",
                        inputs=buffer_output, outputs=outputs,
                        func=lambda count, a: zip(*a), **kwargs)]
        return nodes

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'ScatterWidget', 'terms': terms, 'topics': topics}


class ScalarPlot(CtrlNode):

    """
    Scalar Plot collects scalars and plots them.
    """

    nodeName = "ScalarPlot"
    uiTemplate = [("Num Points", 'intSpin', {'value': 100, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"Y": {"io": "in", "ttype": float}},
                         allowAddInput=True,
                         buffered=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

    def addInput(self, **args):
        self.addTerminal(name="Y", io='in', ttype=float, **args)

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, WaveformWidget, **kwargs)

    def to_operation(self, inputs, outputs, **kwargs):
        outputs = [self.name()+'.'+i for i in inputs.keys()]
        buffer_output = [self.name()+"_count", self.name()+"_buffered"]

        if len(inputs.values()) > 1:
            def map_unzip(count, a):
                return zip(*a)
        else:
            def map_unzip(count, a):
                return a

        nodes = [gn.RollingBuffer(name=self.name()+"_buffer", N=self.values['Num Points'],
                                  inputs=inputs, outputs=buffer_output, **kwargs),
                 gn.Map(name=self.name()+"_operation", inputs=buffer_output, outputs=outputs,
                        func=map_unzip, **kwargs)]

        return nodes

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'WaveformWidget', 'terms': terms, 'topics': topics}


class LinePlot(CtrlNode):

    """
    Line Plot plots arrays.
    """

    nodeName = "LinePlot"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name, terminals={"X": {"io": "in", "ttype": Array1d},
                                          "Y": {"io": "in", "ttype": Array1d}},
                         allowAddInput=True,
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return False

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, LineWidget, **kwargs)

    def addInput(self, **args):
        group = self.nextGroupName()
        self.addTerminal(name="X", io='in', ttype=Array1d, group=group, **args)
        self.addTerminal(name="Y", io='in', ttype=Array1d, group=group, **args)

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'LineWidget', 'terms': terms, 'topics': topics}


class TimePlot(CtrlNode):

    """
    Plot a number against time of day.
    """

    nodeName = "TimePlot"
    uiTemplate = [("Num Points", 'intSpin', {'value': 1000, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"X": {"io": "in", "ttype": float},
                                          "Y": {"io": "in", "ttype": float}},
                         allowAddInput=True,
                         buffered=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, TimeWidget, **kwargs)

    def addInput(self, **args):
        self.addTerminal(name="X", io='in', ttype=float, **args)
        self.addTerminal(name="Y", io='in', ttype=float, **args)

    def to_operation(self, inputs, outputs, **kwargs):
        outputs = [self.name()+'.'+i for i in inputs.keys()]
        buffer_output = [self.name()+"_count", self.name()+"_buffered"]
        nodes = [gn.RollingBuffer(name=self.name()+"_buffer", N=self.values['Num Points'],
                                  inputs=inputs, outputs=buffer_output, **kwargs),
                 gn.Map(name=self.name()+"_operation", inputs=buffer_output, outputs=outputs,
                        func=lambda a: zip(*a), **kwargs)]
        return nodes

    def plotMetadata(self, topics, terms, **kwargs):
        return {'type': 'TimeWidget', 'terms': terms, 'topics': topics}
