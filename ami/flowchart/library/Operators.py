from ami.flowchart.Node import Node
import ami.graph_nodes as gn
import numpy as np


class Sum(Node):

    nodeName = "Sum"

    def __init__(self, name):
        super(Sum, self).__init__(name, terminals={
            'In': {'io': 'in'},
            'Out': {'io': 'out'}
        })

    def to_operation(self, inputs, conditions=[]):
        outputs = [self.name()]
        node = gn.Map(name=self.name()+"_operation", inputs=inputs, outputs=outputs, func=np.sum)
        return node


class Binning(Node):

    nodeName = "Binning"

    def __init__(self, name):
        super(Binning, self).__init__(name, terminals={
            'Condition': {'io': 'in'},
            'Values': {'io': 'in'},
            'Bins': {'io': 'in'},
            'Out': {'io': 'out'}
        })

    def connected(self, localTerm, remoteTerm):
        if localTerm.isInput() and remoteTerm.isOutput():
            if localTerm.name() == "Condition":
                self.condition_names.append(remoteTerm.node().name())
            elif localTerm.name() == "Bins":
                self.input_names.insert(0, remoteTerm.node().name())
            elif localTerm.name() == "Values":
                self.input_names.insert(1, remoteTerm.node().name())

            self.sigTerminalConnected.emit(self)

    def to_operation(self, inputs, conditions=[]):
        outputs = [self.name()]

        node = gn.Binning(name=self.name()+"_operation", condition_needs=conditions, inputs=inputs, outputs=outputs)
        return node
