from graphkit import compose, operation, If, Else
import collections


class Graph():

    def __init__(self, name):
        self.name = name
        self.steps = []
        # { (condition_needs): {'filter_on': []}, 'filter_off': []}
        self.conditionals = collections.defaultdict(dict)
        self.graph = None

    def __call__(self, *args, **kwargs):
        if self.graph is None:
            self.graph = self.compile()
        return self.graph(*args, **kwargs)

    def add(self, op):
        if isinstance(op, Filter):
            branch = self.conditionals[tuple(op.condition_needs)]
            if 'filter_on' not in branch:
                branch['filter_on'] = []

            if 'filter_off' not in branch:
                branch['filter_off'] = []

        self.steps.append(op)

        return self

    def remove(self, op):
        pass

    def reset(self):
        for node in self.steps:
            if hasattr(node, 'reset'):
                node.reset()

    def compile(self):
        graph = []
        ops = graph
        color = 'worker'

        for op in self.steps:
            if isinstance(op, Map):
                if op.condition_needs is None:
                    ops = graph
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs, color=color)(op.func))
            elif isinstance(op, ReduceByKey):
                color = 'localCollector'
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs, color=color)(op.func))
            elif isinstance(op, Accumulator):
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs, color=color)(op))
            elif isinstance(op, FilterOn):
                branch = self.conditionals[tuple(op.condition_needs)]
                branch['if'] = {'name': op.name, 'condition_needs': op.condition_needs,
                                'condition': op.condition}
                ops = branch['filter_on']
            elif isinstance(op, FilterOff):
                branch = self.conditionals[tuple(op.condition_needs)]
                branch['else'] = {'name': op.name}
                ops = branch['filter_off']

        for key, branches in self.conditionals.items():
            if_args = branches['if']
            subgraph = compose(name=if_args['name'])(*branches['filter_on'])
            if_args['needs'] = subgraph.needs
            if_args['provides'] = subgraph.provides

            graph.append(If(**if_args)(*branches['filter_on']))

            else_args = branches['else']
            subgraph = compose(name=else_args['name'])(*branches['filter_off'])
            else_args['needs'] = subgraph.needs
            else_args['provides'] = subgraph.provides

            graph.append(Else(**else_args)(*branches['filter_off']))

        return compose(name=self.name)(*graph)


class Transformation():

    def __init__(self, name, inputs, outputs, func, condition_needs=None):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.func = func
        self.condition_needs = condition_needs


class Map(Transformation):

    def __init__(self, **kwargs):
        super(Map, self).__init__(**kwargs)


class ReduceByKey(Transformation):

    def __init__(self, **kwargs):
        super(ReduceByKey, self).__init__(**kwargs)


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


class Accumulator(Transformation):

    def __init__(self, name, inputs, outputs, func, reduction=None):
        super(Accumulator, self).__init__(name, inputs, outputs, func)
        if reduction:
            assert hasattr(reduction, '__call__'), 'reduction is not callable'
        self.reduction = reduction
        self.res = []

    def __call__(self, *args, **kwargs):
        self.res.append(self.func(*args, **kwargs))
        if self.reduction:
            return self.reduction(self.res)
        return self.res

    def reset(self):
        self.res = []


if __name__ == '__main__':
    from operator import mul
    graph = Graph(name='graph')
    graph.add(Map(name='mul1', inputs=['a', 'b'], outputs=['ab'], func=mul))

    graph.add(FilterOn(name='FilterOn', condition_needs=['i']))
    graph.add(Map(name='add', inputs=['ab'], outputs=['c'], condition_needs=['i'], func=lambda ab: ab + 2))
    graph.add(Map(name='sub2', inputs=['c'], outputs=['d'], condition_needs=['i'], func=lambda c: c - 2))

    graph.add(FilterOff(name='FilterOff', condition_needs=['i']))
    graph.add(Map(name='sub', inputs=['ab'], outputs=['c'], condition_needs=['i'], func=lambda ab: ab - 1))
    graph.add(Map(name='add2', inputs=['c'], outputs=['d'], condition_needs=['i'], func=lambda c: c + 1))

    graph.add(Map(name='div', inputs=['d'], outputs=['e'], func=lambda d: d/2))
    graph.add(Accumulator(name='acc', inputs=['e'], outputs=['f'], func=lambda a: a, reduction=sum))

    print(graph({'a': 1, 'b': 1, 'i': True}, color='worker'))
    print(graph({'a': 1, 'b': 1, 'i': True}, color='worker'))
    graph.reset()
    print(graph({'a': 1, 'b': 1, 'i': True}, color='worker'))
