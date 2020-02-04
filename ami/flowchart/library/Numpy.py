from typing import Union, List
from amitypes import Array, Array1d, Array2d, Array3d
from ami.flowchart.library.common import CtrlNode, MAX
from ami.flowchart.Node import Node
import ami.graph_nodes as gn
import numpy as np


class Sum(Node):

    """
    Returns the sum of an array.
    """

    nodeName = "Sum"

    def __init__(self, name):
        super().__init__(name, terminals={
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
        super().__init__(name, terminals={
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
                  ('auto range', 'check', {'checked': False}),
                  ('range min', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX}),
                  ('range max', 'doubleSpin', {'value': 100, 'min': -MAX, 'max': MAX}),
                  ('weighted', 'check', {'checked': False}),
                  ('density', 'check', {'checked': False})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Union[float, Array1d]},
            'Bins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array1d}
        })
        self.weighted = None

    def changed(self, *args, **kwargs):
        super().changed(*args, **kwargs)

        if "weighted" == args[0] and args[1]:
            self.addTerminal("Weights", io='in', ttype=Union[float, Array1d])
        elif "weighted" in args[0] and not args[1]:
            self.removeTerminal("Weights")
        elif "auto range" == args[0]:
            self.ctrls['range min'].setEnabled(not args[1])
            self.ctrls['range max'].setEnabled(not args[1])

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [self.name()+"_bins", self.name()+"_counts"]
        nbins = self.bins
        density = self.density

        range = None
        if not self.auto_range:
            range = (self.range_min, self.range_max)

        def bin(arr, weights=None):
            counts, bins = np.histogram(arr, bins=nbins, range=range, density=density, weights=weights)
            return bins, counts

        def reduction(res, *rest):
            res[0] = rest[0]
            res[1] = res[1] + rest[1]
            return res

        node = [gn.Map(name=self.name()+"_map",
                       condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=map_outputs,
                       func=bin, parent=self.name()),
                gn.Accumulator(name=self.name()+"_accumulated", inputs=map_outputs, outputs=outputs,
                               res_factory=lambda: [None, 0], reduction=reduction, parent=self.name())]
        return node


class Binning2D(CtrlNode):

    """
    Binning2D creates a 2d histogram with a fixed number of bins using numpy.histogram2d.
    """

    nodeName = "Binning2D"
    uiTemplate = [('x bins', 'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('y bins', 'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('range x min', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX}),
                  ('range x max', 'doubleSpin', {'value': 100, 'min': -MAX, 'max': MAX}),
                  ('range y min', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX}),
                  ('range y max', 'doubleSpin', {'value': 100, 'min': -MAX, 'max': MAX}),
                  ('density', 'check', {'checked': False})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'X': {'io': 'in', 'ttype': Union[float, Array1d]},
            'Y': {'io': 'in', 'ttype': Union[float, Array1d]},
            'XBins': {'io': 'out', 'ttype': Array1d},
            'YBins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array2d}
        })
        self.x_type = None
        self.y_type = None
        self.sigTerminalConnected.connect(self.setType)

    def setType(self, localTerm, remoteTerm):
        if remoteTerm.isOutput() and localTerm.name() == 'X':
            self.x_type = remoteTerm.type()
        elif remoteTerm.isOutput() and localTerm.name() == 'Y':
            self.y_type = remoteTerm.type()

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [self.name()+"_xbins", self.name()+"_ybins", self.name()+"_counts"]
        nxbins = self.x_bins
        nybins = self.y_bins
        xmin = self.range_x_min
        xmax = self.range_x_max
        ymin = self.range_y_min
        ymax = self.range_y_max
        density = self.density

        if self.x_type == float and self.y_type == float:
            def bin(x, y):
                counts, xbins, ybins = np.histogram2d([x], [y], bins=[nxbins, nybins],
                                                      range=[[xmin, xmax], [ymin, ymax]], density=density)
                return xbins, ybins, counts
        else:
            def bin(x, y):
                counts, xbins, ybins = np.histogram2d(x, y, bins=[nxbins, nybins],
                                                      range=[[xmin, xmax], [ymin, ymax]], density=density)
                return xbins, ybins, counts

        def reduction(res, *rest):
            res[0] = rest[0]
            res[1] = rest[1]
            res[2] = res[2] + rest[2]
            return res

        node = [gn.Map(name=self.name()+"_map",
                       condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=map_outputs,
                       func=bin, parent=self.name()),
                gn.Accumulator(name=self.name()+"_accumulated", inputs=map_outputs, outputs=outputs,
                               res_factory=lambda: [None, None, 0], reduction=reduction, parent=self.name())]
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


class GroupedNode(CtrlNode):

    def __init__(self, name, *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.sigTerminalConnected.connect(self.setType)

    def addInput(self, **kwargs):
        group = self.nextGroupName()
        kwargs['group'] = group
        super().addInput(**kwargs)
        super().addOutput(**kwargs)

    def setType(self, localTerm, remoteTerm):
        pass

    def find_output_term(self, localTerm):
        group = localTerm.group()
        if group:
            group = self._groups[group]
            for name in group:
                term = self.terminals[name]
                if term.isOutput():
                    return term
        else:
            return self.terminals['Out']


class Take(GroupedNode):

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

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        axis = self.axis
        index = self.index
        mode = self.mode

        if len(inputs) == 1:
            def func(arr):
                return np.take(arr, index, axis=axis, mode=mode)
        else:
            def func(*arr):
                return list(map(lambda a: np.take(a, index, axis=axis, mode=mode), arr))

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=func, parent=self.name())
        return node

    def setType(self, localTerm, remoteTerm):
        if localTerm.isInput():
            term = self.find_output_term(localTerm)

            if remoteTerm.type() == Array3d:
                term._type = Array2d
            elif remoteTerm.type() == Array2d:
                term._type = Array1d
            elif remoteTerm.type() == Array1d or remoteTerm.type() == List[float]:
                term._type = float


class Polynomial(CtrlNode):

    """
    Evaluate a polynomial using np.polynomial.polynomial.polyval
    """

    nodeName = "Polynomial"
    uiTemplate = [('c0', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX}),
                  ('c1', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX}),
                  ('c2', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Array1d},
            'Out': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        c0 = self.c0
        c1 = self.c1
        c2 = self.c2

        def poly(x):
            coeffs = [c0, c1, c2]
            return np.polynomial.polynomial.polyval(x, coeffs)

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=poly, parent=self.name())
        return node