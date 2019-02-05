from ami.flowchart.Node import Node
import ami.graph_nodes


class Filter(Node):

    def __init__(self, name, addr):
        super(Filter, self).__init__(name, addr=addr, terminals={
            'Condition': {'io': 'in'},
            'Out': {'io': 'out'}
        })


class FilterOff(Filter):

    nodeName = "FilterOff"

    def to_operation(self):
        In = self.terminals['Condition'].inputTerminals()[0]

        if In.node().name() == "Input":
            inputs = [In.name()]
        else:
            inputs = [In.node().name()]

        outputs = [self.name()]

        node = ami.graph_nodes.FilterOff(name=self.name(), condition_needs=inputs, outputs=outputs)
        return node


class FilterOn(Filter):

    nodeName = "FilterOn"

    def to_operation(self):
        In = self.terminals['Condition'].inputTerminals()[0]

        if In.node().name() == "Input":
            inputs = [In.name()]
        else:
            inputs = [In.node().name()]

        outputs = [self.name()]

        node = ami.graph_nodes.FilterOn(name=self.name(), condition_needs=inputs, outputs=outputs)
        return node
