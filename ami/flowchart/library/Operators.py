from typing import Any
from amitypes import Array1d
from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode, MAX, MathNode
import ami.graph_nodes as gn
import numpy as np
import functools
import itertools


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


class Add(MathNode):

    """
    Add floats, waveforms, and images.
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
    Subtract floats, waveforms, and images.
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


class Multiply(MathNode):

    """
    Multiply floats, waveforms, and images.
    """

    nodeName = "Multiply"

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        def func(*args):
            return functools.reduce(lambda x, y: x*y, args)

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=func, parent=self.name())
        return node


class Divide(MathNode):

    """
    Divide floats, waveforms, and images.
    """

    nodeName = "Divide"

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        def func(*args):
            return functools.reduce(lambda x, y: x/y, args)

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=func, parent=self.name())
        return node


class Combinations(CtrlNode):

    """
    Generate combinations using itertools.combinations.
    """

    nodeName = "Combinations"
    uiTemplate = [('length', 'intSpin', {'value': 1, 'min': 1, 'max': MAX})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})
        self.output_terms = []

    def changed(self, *args, **kwargs):
        super().changed(*args, **kwargs)

        while len(self.output_vars()) > self.length:
            self.removeTerminal(self.output_terms.pop())

        while len(self.output_vars()) < self.length:
            self.output_terms.append(self.addOutput())

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        length = self.length

        def func(*args):
            r = list(map(np.array, zip(*itertools.combinations(*args, length))))
            if r:
                return r
            else:
                return [np.array([])]*length

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=func, parent=self.name())
        return node


class ConstantFloat(CtrlNode):

    """
    Outputs a float constant.
    """

    nodeName = "ConstantFloat"
    uiTemplate = [('value', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX})]

    def __init__(self, name):
        super().__init__(name, terminals={'Out': {'io': 'out', 'ttype': float}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        value = self.value

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda: value, parent=self.name())
        return node


class ConstantArray1d(CtrlNode):

    """
    Outputs a constant 1d array.
    """

    nodeName = "ConstantArray1d"
    uiTemplate = [('shape', 'intSpin', {'value': 1, 'min': 1, 'max': MAX}),
                  ('value', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX})]

    def __init__(self, name):
        super().__init__(name, terminals={'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        shape = self.shape
        value = self.value

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda: np.ones(shape)*value, parent=self.name())
        return node


class Export(Node):

    """
    Send data back to worker.
    """

    nodeName = "Export"

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any},
                                          "Out": {'io': 'out', 'ttype': Any}},
                         exportable=True)
