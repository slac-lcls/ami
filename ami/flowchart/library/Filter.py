from ami.flowchart.Node import Node
import ami.graph_nodes as gn


class Filter(Node):

    def __init__(self, name):
        super(Filter, self).__init__(name, terminals={
            'Condition': {'io': 'condition'},
            'Out': {'io': 'out', 'type': bool}
        })

    def output_vars(self):
        return [self.name()]


class FilterOff(Filter):

    """
    FilterOff
    """

    nodeName = "FilterOff"

    def __init__(self, name):
        super(FilterOff, self).__init__(name)

    def to_operation(self, inputs, conditions=[]):
        outputs = self.output_vars()
        node = gn.FilterOff(name=self.name()+'_operation', condition_needs=list(conditions.values()), outputs=outputs)
        return node


class FilterOn(Filter):

    """
    FilterOn
    """

    nodeName = "FilterOn"

    def __init__(self, name):
        super(FilterOn, self).__init__(name)

    def to_operation(self, inputs, conditions=[]):
        outputs = self.output_vars()
        node = gn.FilterOn(name=self.name()+'_operation', condition_needs=list(conditions.values()), outputs=outputs)
        return node
