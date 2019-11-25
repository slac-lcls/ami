from pyqtgraph import QtGui
from typing import Any
from amitypes import Array1d, Array2d
from ami.flowchart.Node import Node, NodeGraphicsItem
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


# class Constant(CtrlNode, MathNode):

#     """
#     Add/Subtract/Multiply/Divide waveform and images by constant.
#     """

#     nodeName = "Constant"
#     uiTemplate = [('operation', 'combo', {'values': ['Add', 'Subtract', 'Multiply', 'Divide']})]

#     def __init__(self, name):
#         CtrlNode.__init__(name,
#                           terminals={'Image': {'io': 'in', 'ttype': Array2d, 'removable': True},
#                                      'Out': {'io': 'out', 'ttype': Array2d}},
#                           allowAddInput=True)
#         self.sigTerminalAdded.connect(self.setOutput)
#         self.sigTerminalRemoved.connect(self.setOutput)

#     def to_operation(self, inputs, conditions={}):
#         pass


class Export(Node):

    """
    Send data back to worker.
    """

    nodeName = "Export"

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any},
                                          "Out": {'io': 'out', 'ttype': Any}},
                         exportable=True)
