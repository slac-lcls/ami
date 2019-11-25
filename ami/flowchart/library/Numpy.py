from typing import Union, List
from amitypes import Array, Array1d, Array2d, Array3d
from ami.flowchart.library.common import CtrlNode, MAX
from ami.flowchart.Node import Node
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


class Binning(CtrlNode):

    """
    Binning creates a histogram with a fixed number of bins using numpy.histogram.
    """

    nodeName = "Binning"
    uiTemplate = [('bins', 'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('range min', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX}),
                  ('range max', 'doubleSpin', {'value': 100, 'min': -MAX, 'max': MAX}),
                  ('density', 'check', {'checked': False})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Union[float, Array1d]},
            'Bins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [self.name()+"_bins", self.name()+"_counts"]
        nbins = self.bins
        rmin = self.range_min
        rmax = self.range_max
        density = self.density

        def bin(arr):
            counts, bins = np.histogram(arr, bins=nbins, range=(rmin, rmax), density=density)
            return bins, counts

        def reduction(res, *rest):
            res[0] = rest[0]
            res[1] = res[1] + rest[1]
            return res

        node = [gn.Map(name=self.name()+"_map",
                       condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=map_outputs,
                       func=bin, parent=self.name()),
                gn.Accumulator(name=self.name()+"_accumulated", inputs=map_outputs, outputs=outputs,
                               res_factory=lambda: [None, 0],
                               reduction=reduction)]
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


class Take(CtrlNode):

    """
    Index into a list or array using np.take
    """

    nodeName = "Take"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 2}),
                  ('index', 'intSpin', {'value': 0, 'min': -MAX, 'max': MAX}),
                  ('mode', 'combo', {'values': ['raise', 'wrap', 'clip']})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Array},
                                          "Out": {'io': 'out', 'ttype': Union[float, Array1d, Array2d]}},
                         allowAddInput=True)
        self.sigTerminalConnected.connect(self.setType)

    def addInput(self, **kwargs):
        group = self.nextGroupName()
        kwargs['group'] = group
        super().addInput(**kwargs)
        super().addOutput(**kwargs)

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        axis = self.axis
        index = self.index
        mode = self.mode

        def func(*arr):
            return list(map(lambda a: np.take(a, index, axis=axis, mode=mode), arr))

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=func, parent=self.name())
        return node

    def setType(self, localTerm, remoteTerm):
        if localTerm.isInput():
            group = localTerm.group()
            if group:
                group = self._groups[group]
                for name in group:
                    term = self.terminals[name]
                    if term.isOutput():
                        break
            else:
                term = self.terminals['Out']

            if remoteTerm.type() == Array3d:
                term._type = Array2d
            elif remoteTerm.type() == Array2d:
                term._type = Array1d
            elif remoteTerm.type() == Array1d or remoteTerm.type() == List[float]:
                term._type = float
