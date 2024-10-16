from typing import Union
from amitypes import Array, Array1d, Array2d, Array3d
from ami.flowchart.library.common import CtrlNode, GroupedNode
from ami.flowchart.Node import Node
import ami.graph_nodes as gn
import numpy as np
import os


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

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=lambda a: np.sum(a, dtype=np.float64))


class Binning(CtrlNode):

    """
    Binning creates a histogram with a fixed number of bins using numpy.histogram.
    """

    nodeName = "Binning"
    uiTemplate = [('bins', 'intSpin', {'value': 10, 'min': 1}),
                  ('auto range', 'check', {'checked': False}),
                  ('range min', 'doubleSpin', {'value': 1}),
                  ('range max', 'doubleSpin', {'value': 100}),
                  ('weighted', 'check', {'checked': False}),
                  ('density', 'check', {'checked': False})]

    def __init__(self, name):
        super().__init__(name, global_op=True,
                         terminals={
                             'In': {'io': 'in', 'ttype': Union[float, Array1d, Array2d]},
                             'Bins': {'io': 'out', 'ttype': Array1d},
                             'Counts': {'io': 'out', 'ttype': Array1d}
                         })
        self.weighted = None

    def state_changed(self, *args, **kwargs):
        super().state_changed(*args, **kwargs)

        if "weighted" == args[0] and args[1]:
            self.addTerminal("Weights", io='in', ttype=Union[float, Array1d])
        elif "weighted" in args[0] and not args[1]:
            self.removeTerminal("Weights")
        elif "auto range" == args[0]:
            self.ctrls['range min'].setEnabled(not args[1])
            self.ctrls['range max'].setEnabled(not args[1])

    def to_operation(self, inputs, outputs, **kwargs):
        map_outputs = [self.name()+"_bins", self.name()+"_counts"]
        nbins = self.values['bins']
        density = self.values['density']

        range = None
        if not self.values['auto range']:
            range = (self.values['range min'], self.values['range max'])

        def bin(arr, weights=None):
            counts, bins = np.histogram(arr, bins=nbins, range=range, density=density, weights=weights)
            return bins, counts

        def reduction(res, *rest):
            res[0] = rest[0]
            res[1] = res[1] + rest[1]
            return res

        node = [gn.Map(name=self.name()+"_map",
                       inputs=inputs, outputs=map_outputs, func=bin, **kwargs),
                gn.Accumulator(name=self.name()+"_accumulated", inputs=map_outputs, outputs=outputs,
                               res_factory=lambda *args: ([None, 0], ()), reduction=reduction, **kwargs)]
        return node


class Binning2D(CtrlNode):

    """
    Binning2D creates a 2d histogram with a fixed number of bins using numpy.histogram2d.
    """

    nodeName = "Binning2D"
    uiTemplate = [('x bins', 'intSpin', {'value': 10, 'min': 1}),
                  ('y bins', 'intSpin', {'value': 10, 'min': 1}),
                  ('range x min', 'doubleSpin', {'value': 1}),
                  ('range x max', 'doubleSpin', {'value': 100}),
                  ('range y min', 'doubleSpin', {'value': 1}),
                  ('range y max', 'doubleSpin', {'value': 100}),
                  ('density', 'check', {'checked': False})]

    def __init__(self, name):
        super().__init__(name, global_op=True,
                         terminals={
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

    def to_operation(self, inputs, outputs, **kwargs):
        map_outputs = [self.name()+"_xbins", self.name()+"_ybins", self.name()+"_counts"]
        nxbins = self.values['x bins']
        nybins = self.values['y bins']
        xmin = self.values['range x min']
        xmax = self.values['range x max']
        ymin = self.values['range y min']
        ymax = self.values['range y max']
        density = self.values['density']

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
                       inputs=inputs, outputs=map_outputs, func=bin, **kwargs),
                gn.Accumulator(name=self.name()+"_accumulated", inputs=map_outputs, outputs=outputs,
                               res_factory=lambda *args: ([None, None, 0], ()), reduction=reduction, **kwargs)]
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

    def to_operation(self, **kwargs):
        axis = self.values['axis']
        sections = len(kwargs['outputs'])

        if axis == 0:
            def split(arr):
                splits = np.split(arr, sections, axis=axis)
                return list(map(lambda a: a[0, :], splits))
        elif axis == 1:
            def split(arr):
                splits = np.split(arr, sections, axis=axis)
                return list(map(lambda a: a[:, 0], splits))

        return gn.Map(name=self.name()+"_operation", **kwargs, func=split)


class Stack1d(CtrlNode):

    """
    Stacks scalars into 1d array using np.stack
    """

    nodeName = "Stack1d"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 0})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Union[float, list[float]]},
                                          "Out": {'io': 'out', 'ttype': Array1d}},
                         allowAddInput=True)

    def to_operation(self, **kwargs):
        axis = self.values['axis']

        if len(self.inputs()) > 1:
            node = gn.Map(name=self.name()+"_operation", **kwargs,
                          func=lambda *arr: np.stack(arr, axis=axis))
        else:
            node = gn.Map(name=self.name()+"_operation", **kwargs,
                          func=lambda arr: np.stack(arr, axis=axis))

        return node


class Stack2d(CtrlNode):

    """
    Stacks 1d arrays into 2d array using np.stack
    """

    nodeName = "Stack2d"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Union[Array1d, list[Array1d]]},
                                          "Out": {'io': 'out', 'ttype': Array2d}},
                         allowAddInput=True)

    def to_operation(self, **kwargs):
        axis = self.values['axis']

        if len(self.inputs()) > 1:
            node = gn.Map(name=self.name()+"_operation", **kwargs,
                          func=lambda *arr: np.stack(arr, axis=axis))
        else:
            node = gn.Map(name=self.name()+"_operation", **kwargs,
                          func=lambda arr: np.stack(arr, axis=axis))

        return node


class Projection(GroupedNode):

    """
    Projection projects a 2d array along the selected axis.
    """

    nodeName = "Projection"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array1d}},
                         allowAddInput=True)

    def to_operation(self, **kwargs):
        axis = self.values['axis']

        if len(kwargs['inputs']) == 1:
            def func(arr):
                return np.sum(arr, axis=axis)
        else:
            def func(*arr):
                return list(map(lambda a: np.sum(a, axis=axis), arr))

        node = gn.Map(name=self.name()+"_operation", **kwargs, func=func)
        return node


class Take(GroupedNode):

    """
    Index into a list or array using np.take
    """

    nodeName = "Take"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 2}),
                  ('index', 'intSpin', {'value': 0}),
                  ('mode', 'combo', {'values': ['raise', 'wrap', 'clip']})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Array},
                                          "Out": {'io': 'out', 'ttype': Union[float, Array1d, Array2d]}},
                         allowAddInput=True)

    def to_operation(self, **kwargs):
        axis = self.values['axis']
        index = self.values['index']
        mode = self.values['mode']

        if len(kwargs['inputs']) == 1:
            def func(arr):
                return np.take(arr, index, axis=axis, mode=mode)
        else:
            def func(*arr):
                return list(map(lambda a: np.take(a, index, axis=axis, mode=mode), arr))

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)

    def setType(self, localTerm, remoteTerm):
        if localTerm.isInput():
            term = self.find_output_term(localTerm)
            term.setUnit(remoteTerm.unit())

            if remoteTerm.type() == Array3d:
                term._type = Array2d
            elif remoteTerm.type() == Array2d:
                term._type = Array1d
            else:
                term._type = float


class Polynomial(CtrlNode):

    """
    Evaluate a polynomial using np.polynomial.polynomial.polyval
    """

    nodeName = "Polynomial"
    uiTemplate = [('c0', 'doubleSpin', {'value': 1}),
                  ('c1', 'doubleSpin', {'value': 1}),
                  ('c2', 'doubleSpin', {'value': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Array1d},
            'Out': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, **kwargs):
        c0 = self.values['c0']
        c1 = self.values['c1']
        c2 = self.values['c2']
        coeffs = [c0, c1, c2]

        def poly(x):
            return np.polynomial.polynomial.polyval(x, coeffs)

        return gn.Map(name=self.name()+"_operation", **kwargs, func=poly)


class Average(GroupedNode):

    """
    Compute average using np.average
    """

    nodeName = "Average"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Union[Array1d, Array2d]},
                                          'Out': {'io': 'out', 'ttype': float}},
                         allowAddInput=True)

    def to_operation(self, **kwargs):
        axis = self.values['axis']

        if len(kwargs['inputs']) == 1:
            def func(arr):
                return np.average(arr, axis=axis)
        else:
            def func(*arr):
                return list(map(lambda a: np.average(a, axis=axis), arr))

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)


class RMS(GroupedNode):

    """
    RMS
    """

    nodeName = "RMS"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Union[Array1d, Array2d]},
                                          'Out': {'io': 'out', 'ttype': float}},
                         allowAddInput=True)

    def to_operation(self, **kwargs):
        if len(kwargs['inputs']) == 1:
            def func(arr):
                return np.sqrt(np.mean(np.square(arr)))
        else:
            def func(*arr):
                return list(map(lambda a: np.sqrt(np.mean(np.square(a))), arr))

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)


class TimeMeanRMS0D(CtrlNode):

    """
    TimeMeanRMS0D
    """

    nodeName = "TimeMeanRMS0D"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': float},
                                          'Mean': {'io': 'out', 'ttype': float},
                                          'RMS': {'io': 'out', 'ttype': float}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        def func(arr):
            mean = np.mean(arr)
            rms = np.sqrt(np.mean(np.square(arr)))
            return mean, rms

        accumulated_outputs = [self.name()+'_accumulated_events']

        nodes = [gn.PickN(name=self.name()+'_picked', N=self.values['N'],
                          inputs=inputs, outputs=accumulated_outputs, **kwargs),
                 gn.Map(name=self.name()+'_operation', inputs=accumulated_outputs, outputs=outputs,
                        func=func, **kwargs)]

        return nodes


class TimeMeanRMS1D(CtrlNode):

    """
    TimeMeanRMS1D
    """

    nodeName = "TimeMeanRMS1D"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Mean': {'io': 'out', 'ttype': Array1d},
                                          'RMS': {'io': 'out', 'ttype': Array1d}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        def func(arr):
            mean = np.mean(arr, axis=0)
            sq = list(map(np.square, arr))
            rms = np.sqrt(np.mean(sq, axis=0))
            return mean, rms

        accumulated_outputs = [self.name()+'_accumulated_events']

        nodes = [gn.PickN(name=self.name()+'_picked', N=self.values['N'],
                          inputs=inputs, outputs=accumulated_outputs, **kwargs),
                 gn.Map(name=self.name()+'_operation', inputs=accumulated_outputs, outputs=outputs,
                        func=func, **kwargs)]

        return nodes


class TimeMeanRMS2D(CtrlNode):

    """
    TimeMeanRMS2D
    """

    nodeName = "TimeMeanRMS2D"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Mean': {'io': 'out', 'ttype': Array2d},
                                          'RMS': {'io': 'out', 'ttype': Array2d}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        def func(arr):
            mean = np.mean(arr, axis=0)
            sq = list(map(np.square, arr))
            rms = np.sqrt(np.mean(sq, axis=0))
            return mean, rms

        accumulated_outputs = [self.name()+'_accumulated_events']

        nodes = [gn.PickN(name=self.name()+'_picked', N=self.values['N'],
                          inputs=inputs, outputs=accumulated_outputs, **kwargs),
                 gn.Map(name=self.name()+'_operation', inputs=accumulated_outputs, outputs=outputs,
                        func=func, **kwargs)]

        return nodes


class HistMeanRMS(Node):

    """
    HistMeanRMS
    """

    nodeName = "HistMeanRMS"

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Mean': {'io': 'out', 'ttype': float},
                                          'Stdev': {'io': 'out', 'ttype': float}})

    def to_operation(self, **kwargs):
        def func(arr):
            centers = np.arange(len(arr))
            mean = np.average(centers, 0, arr)
            var = np.average((centers-mean)**2, 0, arr)
            std = np.sqrt(var)
            return mean, std

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)


class Average0D(CtrlNode):

    """
    Collect N scalars and average them.
    """

    nodeName = "Average0D"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2}),
                  ('infinite', 'check')]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': float},
                                          'Out': {'io': 'out', 'ttype': float}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        accumulated_outputs = [self.name()+'_accumulated_counts', self.name()+'_accumulated_sum']

        def avg(count, value):
            return value/count

        if self.values['infinite']:
            def reduction(res, *rest):
                if len(rest) > 1:
                    res[0] += rest[0]
                    res[1] += rest[1]
                else:
                    res[0] = res[0] + 1
                    res[1] = res[1] + rest[1]
                return res

            nodes = [gn.Accumulator(name=self.name()+"_accumulated",
                                    inputs=inputs, outputs=accumulated_outputs,
                                    res_factory=lambda *args: ([0, 0], ()), reduction=reduction, **kwargs),
                     gn.Map(name=self.name()+"_map",
                            inputs=accumulated_outputs, outputs=outputs,
                            func=avg, **kwargs)]
        else:
            nodes = [gn.SumN(name=self.name()+"_accumulated",
                             inputs=inputs, outputs=accumulated_outputs,
                             N=self.values['N'], **kwargs),
                     gn.Map(name=self.name()+"_map",
                            inputs=accumulated_outputs, outputs=outputs,
                            func=avg, **kwargs)]

        return nodes


class Average1D(CtrlNode):

    """
    Collect N 1d arrays and average them.
    """

    nodeName = "Average1D"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2}),
                  ('infinite', 'check')]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        accumulated_outputs = [self.name()+'_accumulated_counts', self.name()+'_accumulated_sum']

        def avg(count, value):
            return value/count

        if self.values['infinite']:
            def reduction(res, *rest):
                if len(rest) > 1:
                    res[0] += rest[0]
                    res[1] = np.add(res[1], rest[1])
                else:
                    res[0] = res[0] + 1
                    res[1] = np.add(res[1], rest[0])
                return res

            nodes = [gn.Accumulator(name=self.name()+"_accumulated",
                                    inputs=inputs, outputs=accumulated_outputs,
                                    res_factory=lambda *args: ([0, 0], ()), reduction=reduction, **kwargs),
                     gn.Map(name=self.name()+"_map",
                            inputs=accumulated_outputs, outputs=outputs,
                            func=avg, **kwargs)]

        else:
            nodes = [gn.SumN(name=self.name()+"_accumulated",
                             inputs=inputs, outputs=accumulated_outputs,
                             N=self.values['N'], **kwargs),
                     gn.Map(name=self.name()+"_map",
                            inputs=accumulated_outputs, outputs=outputs,
                            func=avg, **kwargs)]

        return nodes


class Average2D(CtrlNode):

    """
    Collect N 2d arrays and average them.
    """

    nodeName = "Average2D"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2}),
                  ('infinite', 'check')]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        accumulated_outputs = [self.name()+'_accumulated_counts', self.name()+'_accumulated_sum']

        def avg(count, value):
            return value/count

        if self.values['infinite']:
            def reduction(res, *rest):
                if len(rest) > 1:
                    res[0] += rest[0]
                    res[1] = np.add(res[1], rest[1])
                else:
                    res[0] = res[0] + 1
                    res[1] = np.add(res[1], rest[0])
                return res

            nodes = [gn.Accumulator(name=self.name()+"_accumulated",
                                    inputs=inputs, outputs=accumulated_outputs,
                                    res_factory=lambda *args: ([0, 0], ()), reduction=reduction, **kwargs),
                     gn.Map(name=self.name()+"_map",
                            inputs=accumulated_outputs, outputs=outputs,
                            func=avg, **kwargs)]
        else:
            nodes = [gn.SumN(name=self.name()+"_accumulated",
                             inputs=inputs, outputs=accumulated_outputs,
                             N=self.values['N'], **kwargs),
                     gn.Map(name=self.name()+"_map",
                            inputs=accumulated_outputs, outputs=outputs,
                            func=avg, **kwargs)]

        return nodes


class LoadReference1D(CtrlNode):

    """
    Load 1d reference array from csv.
    """

    nodeName = "LoadReference1D"
    uiTemplate = [('path', 'text')]

    def __init__(self, name):
        super().__init__(name, terminals={"X": {'io': 'out', 'ttype': Array1d},
                                          "Y": {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, **kwargs):
        path = self.values['path']
        assert (os.path.exists(self.values['path']))
        assert (path.endswith('.csv'))
        arr = np.genfromtxt(path, delimiter=',', usecols=(0, 1), skip_header=1)
        return gn.Map(name=self.name()+"_operation", **kwargs, func=lambda: (arr[:, 0], arr[:, 1]))
