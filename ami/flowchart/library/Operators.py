from pyqtgraph import QtGui
from typing import Dict
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
                      func=lambda a: np.sum(a, dtype=np.float64))
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
                      func=lambda a: np.sum(a, axis=axis))
        return node


class BinByVar(Node):

    """
    BinByVar creates a histogram using a variable number of bins.

    Returns a dict with keys Bins and values mean of bins.
    """

    nodeName = "BinByVar"

    def __init__(self, name):
        super(BinByVar, self).__init__(name, terminals={
            'Values': {'io': 'in', 'ttype': float},
            'Bins': {'io': 'in', 'ttype': float},
            'Out': {'io': 'out', 'ttype': Dict[float, float]}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        ordered_inputs = [inputs['Bins'], inputs['Values']]
        node = gn.Binning(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=ordered_inputs, outputs=outputs)
        return node


class Binning(CtrlNode):

    """
    Binning creates a histogram with a fixed number of bins.
    """

    nodeName = "Binning"
    uiTemplate = [('bins', 'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('range min', 'intSpin', {'value': 1, 'min': 1, 'max': MAX}),
                  ('range max', 'intSpin', {'value': 100, 'min': 2, 'max': MAX})]

    def __init__(self, name):
        super(Binning, self).__init__(name, terminals={
            'In': {'io': 'in', 'ttype': float},
            'Out': {'io': 'out', 'ttype': Dict[float, float]}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [self.name()+"_hist"]
        nbins = self.bins
        rmin = self.range_min
        rmax = self.range_max

        def bin(arr):
            counts, bins = np.histogram(arr, bins=nbins, range=(rmin, rmax))
            return dict(zip(bins, counts))

        node = [gn.Map(name=self.name()+"_map",
                       conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=map_outputs,
                       func=bin),
                gn.ReduceByKey(name=self.name()+"_reduce", inputs=map_outputs, outputs=outputs)]
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
                      func=func)
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
                      func=func)
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
