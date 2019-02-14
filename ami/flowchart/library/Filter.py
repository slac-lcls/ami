from ami.flowchart.Node import Node
import ami.graph_nodes


class Filter(Node):

    def __init__(self, name):
        super(Filter, self).__init__(name, terminals={
            'Condition': {'io': 'in'},
            'Out': {'io': 'out'}
        })


class FilterOff(Filter):

    nodeName = "FilterOff"

    def __init__(self, name):
        super(FilterOff, self).__init__(name)

    def to_operation(self, inputs, conditions=[]):
        outputs = [self.name()]
        node = ami.graph_nodes.FilterOff(name=self.name(), condition_needs=conditions, outputs=outputs)
        return node


class FilterOn(Filter):

    nodeName = "FilterOn"

    def __init__(self, name):
        super(FilterOn, self).__init__(name)

    def to_operation(self, inputs, conditions=[]):
        outputs = [self.name()]
        node = ami.graph_nodes.FilterOn(name=self.name(), condition_needs=conditions, outputs=outputs)
        return node
