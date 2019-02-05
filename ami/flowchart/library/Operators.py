from ami.flowchart.Node import Node
import ami.graph_nodes as gn
import numpy as np


class Sum(Node):

    nodeName = "Sum"

    def __init__(self, name, addr):
        super(Sum, self).__init__(name, addr=addr, terminals={
            'In': {'io': 'in'},
            'Out': {'io': 'out'}
        })

    def to_operation(self):
        In = self.terminals['In'].inputTerminals()[0]

        if In.node().name() == "Input":
            inputs = [In.name()]
        else:
            inputs = [In.node().name()]

        outputs = [self.name()]

        node = gn.Map(name=self.name(), inputs=inputs, outputs=outputs, func=np.sum)
        return node


class Binning(Node):

    nodeName = "Binning"

    def __init__(self, name, addr):
        super(Binning, self).__init__(name, addr=addr, terminals={
            'Condition': {'io': 'in'},
            'Values': {'io': 'in'},
            'Bins': {'io': 'in'},
            'Out': {'io': 'out'}
        })

    def to_operation(self):
        inputs = []

        Condition = self.terminals['Condition'].inputTerminals()[0]

        if Condition.node().name() == "Input":
            condition = [Condition.name()]
        else:
            condition = [Condition.node().name()]

        Bins = self.terminals['Bins'].inputTerminals()[0]

        if Bins.node().name() == "Input":
            inputs.append(Bins.name())
        else:
            inputs.append(Bins.node().name())

        Values = self.terminals['Values'].inputTerminals()[0]

        if Values.node().name() == "Input":
            inputs.append(Values.name())
        else:
            inputs.append(Values.node().name())

        outputs = [self.name()]

        node = gn.Binning(name=self.name(), condition_needs=condition, inputs=inputs, outputs=outputs)
        return node
