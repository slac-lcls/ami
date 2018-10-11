from graphkit import compose, operation, If, Else


class Graph():

    def __init__(self, name):
        self.name = name
        self.steps = []

    def add(self, *args):
        self.steps.extend(args)
        return self

    def compile(self):
        ops = []

        for op in self.steps:

            # TODO Coloring
            if isinstance(op, Map):
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs)(op.func))
            elif isinstance(op, ReduceByKey):
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs)(op.func))
            elif isinstance(op, FilterOn):
                subgraph = op.compile()
                if_op = If(name=op.name, needs=subgraph.needs, provides=subgraph.provides,
                           condition_needs=op.condition_needs, condition=op.condition)(subgraph)
                ops.append(if_op)
            elif isinstance(op, FilterOff):
                subgraph = op.compile()
                else_op = Else(name=op.name, needs=subgraph.needs, provides=subgraph.provides)(subgraph)
                ops.append(else_op)

        return compose(name=self.name)(*ops)


class Transformation():

    def __init__(self, name, inputs, outputs, func):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.func = func


class Map(Transformation):

    def __init__(self, name, inputs, outputs, func):
        super(Map, self).__init__(name, inputs, outputs, func)


class Filter(Graph):

    def __init__(self, name, condition_needs, condition=None):
        super(Filter, self).__init__(name)
        self.condition_needs = condition_needs
        self.condition = condition


class FilterOn(Filter):

    def __init__(self, name, condition_needs, condition=lambda cond: cond is True):
        super(FilterOn, self).__init__(name, condition_needs, condition)


class FilterOff(Filter):

    def __init__(self, name, condition_needs):
        super(FilterOff, self).__init__(name, condition_needs)


class ReduceByKey(Transformation):

    def __init__(self, name, inputs, outputs, func):
        super(ReduceByKey, self).__init__(name, inputs, outputs, func)


if __name__ == '__main__':
    import numpy as np
    graph = Graph('complex')
    graph.add(Map('Roi', ['cspad'], ['roi'], lambda cspad: cspad[:100, :100]))
    graph.add(Map('Sum', ['roi'], ['sum'], np.sum))
    graph.add(FilterOn('FilterOn', ['laser']).add(
        ReduceByKey('Binning On', ['delta_t', 'sum'], ['signal'], lambda acc, n: acc+n)
    ))
    graph.add(FilterOff('FilterOff', ['laser']).add(
        ReduceByKey('Binning Off', ['delta_t', 'sum'], ['reference'], lambda acc, n: acc+n)
    ))

    graph = graph.compile()
    graph.plot(filename='complex.png')
