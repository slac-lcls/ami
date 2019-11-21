from pyqtgraph import QtGui
from typing import Any, Union
from amitypes import Array, Array1d, Array2d
from ami.flowchart.library.common import CtrlNode, MAX
from ami.flowchart.Node import Node, NodeGraphicsItem
import ami.graph_nodes as gn
import numpy as np
import functools


class Sum(Node):

    """
    Returns the sum of an array.
    """

    nodeName = "Sum"

    def __init__(self, name):
        super(Sum, self).__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Array},
            'Out': {'io': 'out', 'ttype': float}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda a: np.sum(a, dtype=np.float64), parent=self.name())
        return node


class Projection(CtrlNode):

    """
    Projection projects a 2d array along the selected axis.
    """

    nodeName = "Projection"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 1})]

    def __init__(self, name):
        super(Projection, self).__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Array2d},
            'Out': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        axis = self.axis
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda a: np.sum(a, axis=axis), parent=self.name())
        return node


class MeanVsScan(Node):

    """
    MeanVsScan creates a histogram using a variable number of bins.

    Returns a dict with keys Bins and values mean of bins.
    """

    nodeName = "MeanVsScan"

    def __init__(self, name):
        super().__init__(name, terminals={
            'Bin': {'io': 'in', 'ttype': float},
            'Value': {'io': 'in', 'ttype': float},
            'Bins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        map_outputs = [self.name()+'_map_count']
        reduce_outputs = [self.name()+'_reduce_count']

        def mean(d):
            res = {}
            for k, v in d.items():
                res[k] = v[0]/v[1]
            keys, values = zip(*sorted(res.items()))
            return np.array(keys), np.array(values)

        nodes = [
            gn.Map(name=self.name()+'_map', inputs=[inputs['Value']], outputs=map_outputs,
                   condition_needs=list(conditions.values()), func=lambda a: (a, 1), parent=self.name()),
            gn.ReduceByKey(name=self.name()+'_reduce', inputs=[inputs['Bin']]+map_outputs, outputs=reduce_outputs,
                           reduction=lambda cv, v: (cv[0]+v[0], cv[1]+v[1]), parent=self.name()),
            gn.Map(name=self.name()+'_mean', inputs=reduce_outputs, outputs=outputs, func=mean,
                   parent=self.name())
        ]

        return nodes


class Binning(CtrlNode):

    """
    Binning creates a histogram with a fixed number of bins using numpy.histogram.
    """

    nodeName = "Binning"
    uiTemplate = [('bins', 'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('range min', 'intSpin', {'value': 1, 'min': 1, 'max': MAX}),
                  ('range max', 'intSpin', {'value': 100, 'min': 2, 'max': MAX}),
                  ('density', 'check', {'checked': False}),
                  ('num events', 'intSpin', {'value': 10, 'min': 1, 'max': MAX})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Union[float, Array1d]},
            'Bins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [self.name()+"_hist"]
        accumulated_outputs = [self.name()+"_sum"]
        nbins = self.bins
        rmin = self.range_min
        rmax = self.range_max
        density = self.density

        def bin(arr):
            counts, bins = np.histogram(arr, bins=nbins, range=(rmin, rmax), density=density)
            return bins, counts

        node = [gn.Map(name=self.name()+"_map",
                       condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=map_outputs,
                       func=bin, parent=self.name()),
                gn.PickN(name=self.name()+"_accumulated", inputs=map_outputs, outputs=accumulated_outputs,
                         N=self.num_events, parent=self.name()),
                gn.Map(name=self.name()+"_operation", inputs=accumulated_outputs, outputs=outputs,
                       func=lambda h: functools.reduce(lambda x, y: (y[0], x[1]+y[1]), h), parent=self.name())]
        return node


class Binning2D(CtrlNode):

    """
    Binning2D creates a 2d histogram with a fixed number of bins using numpy.histogram2d.
    """

    nodeName = "Binning2D"
    uiTemplate = [('bins', 'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('range x min', 'intSpin', {'value': 1, 'min': 1, 'max': MAX}),
                  ('range x max', 'intSpin', {'value': 100, 'min': 2, 'max': MAX}),
                  ('range y min', 'intSpin', {'value': 1, 'min': 1, 'max': MAX}),
                  ('range y max', 'intSpin', {'value': 100, 'min': 2, 'max': MAX}),
                  ('density', 'check', {'checked': False}),
                  ('num events', 'intSpin', {'value': 10, 'min': 1, 'max': MAX})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'X': {'io': 'in', 'ttype': Union[float, Array1d]},
            'Y': {'io': 'in', 'ttype': Union[float, Array1d]},
            'XBins': {'io': 'out', 'ttype': Array1d},
            'YBins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array2d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [self.name()+"_hist"]
        accumulated_outputs = [self.name()+"_sum"]
        nbins = self.bins
        xmin = self.range_x_min
        xmax = self.range_x_max
        ymin = self.range_y_min
        ymax = self.range_y_max
        density = self.density

        def bin(x, y):
            counts, xbins, ybins = np.histogram2d(x, y, bins=nbins, range=[[xmin, xmax], [ymin, ymax]], density=density)
            return xbins, ybins, counts

        node = [gn.Map(name=self.name()+"_map",
                       condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=map_outputs,
                       func=bin, parent=self.name()),
                gn.PickN(name=self.name()+"_accumulated", inputs=map_outputs, outputs=accumulated_outputs,
                         N=self.num_events, parent=self.name()),
                gn.Map(name=self.name()+"_operation", inputs=accumulated_outputs, outputs=outputs,
                       func=lambda h: functools.reduce(lambda x, y: (y[0], y[1], x[2]+y[2]), h), parent=self.name())]
        return node


class MathGraphicsItem(NodeGraphicsItem):

    def buildMenu(self):
        super(MathGraphicsItem, self).buildMenu()
        actions = self.menu.actions()
        addInput = actions[1]

        addWaveform = QtGui.QAction("Add waveform", self.menu)
        addWaveform.triggered.connect(self.node.addWaveform)
        self.menu.insertAction(addInput, addWaveform)

        addImage = QtGui.QAction("Add image", self.menu)
        addImage.triggered.connect(self.node.addImage)
        self.menu.insertAction(addWaveform, addImage)

        self.menu.removeAction(addInput)


class MathNode(Node):

    def __init__(self, name):
        super(MathNode, self).__init__(name,
                                       terminals={'Image': {'io': 'in', 'ttype': Array2d, 'removable': True},
                                                  'Out': {'io': 'out', 'ttype': Array2d}},
                                       allowAddInput=True)
        self.sigTerminalAdded.connect(self.setOutput)
        self.sigTerminalRemoved.connect(self.setOutput)

    def graphicsItem(self, brush=None):
        if self._graphicsItem is None:
            self._graphicsItem = MathGraphicsItem(self, brush)
        return self._graphicsItem

    def isConnected(self):
        if len(self.terminals) < 3:
            return False

        return super(MathNode, self).isConnected()

    def addWaveform(self):
        self.addTerminal('Waveform', io='in', ttype=Array1d, removable=True)

    def addImage(self):
        self.addTerminal('Image', io='in', ttype=Array2d, removable=True)

    def setOutput(self):
        inputs = set()

        for name, term in self._inputs.items():
            inputs.add(term()._type)

        if Array2d in inputs:
            output_type = Array2d
        elif inputs == {Array1d}:
            output_type = Array1d
        else:
            return

        self._outputs['Out']()._type = output_type


class Add(MathNode):

    """
    Add waveforms and images.
    """

    nodeName = "Add"

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        def func(*args):
            return functools.reduce(lambda x, y: x+y, args)

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=func, parent=self.name())
        return node


class Subtract(MathNode):

    """
    Subtract waveforms and images.
    """

    nodeName = "Subtract"

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        def func(*args):
            return functools.reduce(lambda x, y: x-y, args)

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=func, parent=self.name())
        return node


class Constant(CtrlNode, MathNode):

    """
    Add/Subtract/Multiply/Divide waveform and images by constant.
    """

    nodeName = "Constant"
    uiTemplate = [('operation', 'combo', {'values': ['Add', 'Subtract', 'Multiply', 'Divide']})]

    def __init__(self, name):
        CtrlNode.__init__(name,
                          terminals={'Image': {'io': 'in', 'ttype': Array2d, 'removable': True},
                                     'Out': {'io': 'out', 'ttype': Array2d}},
                          allowAddInput=True)
        self.sigTerminalAdded.connect(self.setOutput)
        self.sigTerminalRemoved.connect(self.setOutput)

    def to_operation(self, inputs, conditions={}):
        pass


class Export(Node):

    """
    Send data back to worker.
    """

    nodeName = "Export"

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any},
                                          "Out": {'io': 'out', 'ttype': Any}},
                         exportable=True)


class Split(CtrlNode):

    """
    Split a 2d array into 1d arrays using np.split.
    """

    nodeName = "Split"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Array2d},
                                          "Out": {'io': 'out', 'ttype': Array1d}},
                         allowAddOutput=True)

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        axis = self.axis
        sections = len(outputs)

        def split(arr):
            splits = np.split(arr, sections, axis=axis)
            if axis == 0:
                splits = map(lambda a: a[0, :], splits)
            elif axis == 1:
                splits = map(lambda a: a[:, 0], splits)
            return list(splits)

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=split, parent=self.name())
        return node


class Stack(CtrlNode):

    """
    Stacks 1d arrays into 2d array using np.stack
    """

    nodeName = "Stack"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Array1d},
                                          "Out": {'io': 'out', 'ttype': Array2d}},
                         allowAddInput=True)

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        axis = self.axis

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda *arr: np.stack(arr, axis=axis), parent=self.name())
        return node
