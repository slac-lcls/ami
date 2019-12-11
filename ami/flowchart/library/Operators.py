from pyqtgraph import QtGui
from typing import Any
from amitypes import Array1d, Array2d
from ami.flowchart.Node import Node, NodeGraphicsItem
from ami.flowchart.library.common import CtrlNode, MAX
import ami.graph_nodes as gn
import numpy as np
import functools


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


class MathGraphicsItem(NodeGraphicsItem):

    def buildMenu(self, reset=False):
        super().buildMenu(reset)
        actions = self.menu.actions()
        addInput = actions[2]

        addFloat = QtGui.QAction("Add float", self.menu)
        addFloat.triggered.connect(self.node.addFloat)
        self.menu.insertAction(addInput, addFloat)

        addWaveform = QtGui.QAction("Add waveform", self.menu)
        addWaveform.triggered.connect(self.node.addWaveform)
        self.menu.insertAction(addInput, addWaveform)

        addImage = QtGui.QAction("Add image", self.menu)
        addImage.triggered.connect(self.node.addImage)
        self.menu.insertAction(addWaveform, addImage)

        self.menu.removeAction(addInput)


class MathNode(Node):

    def __init__(self, name):
        super().__init__(name,
                         terminals={'Float': {'io': 'in', 'ttype': float, 'removable': True},
                                    'Waveform': {'io': 'in', 'ttype': Array1d, 'removable': True},
                                    'Image': {'io': 'in', 'ttype': Array2d, 'removable': True},
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

    def addFloat(self):
        self.addTerminal('Float', io='in', ttype=float, removable=True)

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
        elif Array1d in inputs:
            output_type = Array1d
        elif float in inputs:
            output_type = float
        else:
            raise Exception("Unable to set output type!")

        self._outputs['Out']()._type = output_type


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
