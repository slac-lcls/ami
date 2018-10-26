import operator
import networkx as nx
import itertools as it


class Graph():

    def __init__(self, name):
        self.name = name
        self.graph = nx.DiGraph()
        self.global_operations = set()
        self.filters = set()

    def add(self, op):
        for i in op.inputs:
            self.graph.add_edge(i, op)

        for o in op.outputs:
            self.graph.add_edge(op, o)

        for i in op.condition_needs:
            self.graph.add_edge(i, op)

    def color_nodes(self):
        g = self.graph
        inputs = [n for n, d in g.in_degree() if d == 0]
        outputs = [n for n, d in g.out_degree() if d == 0]

        self.global_operations = set()
        self.filters = set()

        sources_targets = list(it.product(inputs, outputs))
        for s, t in sources_targets:
            paths = list(nx.algorithms.all_simple_paths(g, s, t))
            for nodes in paths:
                reductions = filter(lambda node: isinstance(node, ReduceByKey), nodes)

                for reduction in reductions:
                    before = filter(lambda node: isinstance(node, ReduceByKey),
                                    nx.algorithms.dag.ancestors(g, reduction))
                    if list(before) == []:
                        self.global_operations.add(reduction)

                color = 'worker'
                for node in nodes:
                    if type(node) is str:
                        continue

                    if node not in self.global_operations:
                        node.color.add(color)
                    elif node in self.global_operations:
                        node.color.add(color)
                        color = 'localCollector'
                        node.color.add(color)
                        color = 'globalCollector'
                        node.color.add(color)

                filter_node = filter(lambda node: isinstance(node, Filter), nodes)
                self.filters = self.filters.union(set(filter_node))

    def expand_global_operations(self):
        g = self.graph
        for node in self.global_operation:
            inputs = node.inputs
            outputs = node.outputs
            condition_needs = node.condition_needs

            g.remove_node(node)

            color_order = ['worker', 'localCollector', 'globalCollector']
            worker_outputs = None
            local_collector_outputs = None

            for color in color_order:

                if color == 'worker':
                    worker_outputs = list(map(lambda o: o+'_worker', node.outputs))
                    worker_node = ReduceByKey(name=node.name+'_worker', inputs=inputs, outputs=worker_outputs,
                                              condition_needs=condition_needs)
                    worker_node.color.add(color)
                    for i in inputs:
                        g.add_edge(i, worker_node)
                    for o in worker_outputs:
                        g.add_edge(worker_node, o)
                    for n in condition_needs:
                        g.add_edge(n, worker_node)

                elif color == 'localCollector':
                    local_collector_outputs = list(map(lambda o: o+'_localCollector', node.outputs))
                    local_collector_node = ReduceByKey(name=node.name+'_localCollector', inputs=worker_outputs,
                                                       outputs=local_collector_outputs)
                    local_collector_node.color.add(color)
                    for i in worker_outputs:
                        g.add_edge(i, local_collector_node)
                    for o in local_collector_outputs:
                        g.add_edge(local_collector_node, o)

                elif color == 'globalCollector':
                    global_collector_node = ReduceByKey(name=node.name+'_globalCollector',
                                                        inputs=local_collector_outputs,
                                                        outputs=outputs)
                    global_collector_node.color.add(color)
                    for i in local_collector_outputs:
                        g.add_edge(i, global_collector_node)
                    for o in outputs:
                        g.add_edge(global_collector_node, o)

        def compile(self):

            self.color_nodes()
            self.expand_global_operations()


class Transformation():

    def __init__(self, name, inputs, outputs, func, condition_needs=[]):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.func = func
        self.condition_needs = condition_needs
        self.color = set()

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return bool(self.name is not None and
                    self.name == getattr(other, 'name', None))

    def __repr__(self):
        return u"%s(name='%s')" % (self.__class__.__name__, self.name)


class Map(Transformation):

    def __init__(self, **kwargs):
        super(Map, self).__init__(**kwargs)


class Filter():

    def __init__(self, name, condition_needs, outputs, condition=None):
        self.name = name
        self.condition_needs = condition_needs
        self.condition = condition
        self.inputs = []
        self.outputs = outputs
        self.color = set()


class FilterOn(Filter):

    def __init__(self, name, condition_needs, outputs, condition=lambda cond: cond is True):
        super(FilterOn, self).__init__(name, condition_needs, outputs, condition)


class FilterOff(Filter):

    def __init__(self, name, condition_needs, outputs):
        super(FilterOff, self).__init__(name, condition_needs, outputs)


class StatefulTransformation(Transformation):

    def __init__(self, name, inputs, outputs, condition_needs=[], reduction=None):
        super(StatefulTransformation, self).__init__(name=name, inputs=inputs,
                                                     outputs=outputs, func=None,
                                                     condition_needs=condition_needs)
        if reduction:
            assert hasattr(reduction, '__call__'), 'reduction is not callable'
        self.reduction = reduction

    def reset(self):
        raise NotImplementedError


class ReduceByKey(StatefulTransformation):

    def __init__(self, name, inputs, outputs, condition_needs=[], reduction=operator.add):
        super(ReduceByKey, self).__init__(name=name, inputs=inputs, outputs=outputs,
                                          condition_needs=condition_needs, reduction=reduction)
        self.res = {}

    def __call__(self, args):
        for r in args:
            for k, v in r.items():
                if k in self.res:
                    self.res[k] = self.reduction(self.res[k], v)
                else:
                    self.res[k] = v
        r = list(self.res.values())
        if len(r) == 1:
            return r[0]
        return r

    def reset(self):
        self.res = {}


class Accumulator(StatefulTransformation):

    def __init__(self, name, inputs, outputs, condition_needs, reduction=None):
        super(Accumulator, self).__init__(name, inputs, outputs, condition_needs, reduction)
        self.res = []

    def __call__(self, *args, **kwargs):
        self.res.extend(args)

        if self.reduction:
            return self.reduction(self.res)
        return self.res

    def reset(self):
        self.res = []
