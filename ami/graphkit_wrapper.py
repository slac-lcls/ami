import operator
import networkx as nx
import itertools as it
import collections
from graphkit import operation, If, Else, compose


class Graph():

    def __init__(self, name):
        self.name = name
        self.graph = nx.DiGraph()
        self.graphkit = None
        self.global_operations = set()
        self.outputs = collections.defaultdict(set)

    def add(self, op):
        for i in op.inputs:
            self.graph.add_edge(i, op)

        for o in op.outputs:
            self.graph.add_edge(op, o)

        for i in op.condition_needs:
            self.graph.add_edge(i, op)

    def remove(self, name):
        for n in self.graph.nodes:
            if type(n) is str:
                continue
            if n.name == name:
                desc = nx.dag.descendants(self.graph, n)
                self.graph.remove_nodes_from(desc)
                self.graph.remove_node(n)
                break

    def reset(self):
        nodes = filter(lambda node: isinstance(StatefulTransformation, node), self.graph.nodes)
        map(lambda node: node.reset(), nodes)

    def color_nodes(self):

        inputs = [n for n, d in self.graph.in_degree() if d == 0]
        outputs = [n for n, d in self.graph.out_degree() if d == 0]

        self.global_operations = set()

        sources_targets = list(it.product(inputs, outputs))
        for s, t in sources_targets:
            paths = list(nx.algorithms.all_simple_paths(self.graph, s, t))
            for nodes in paths:
                reductions = filter(lambda node: isinstance(node, ReduceByKey), nodes)

                for reduction in reductions:
                    before = filter(lambda node: isinstance(node, ReduceByKey),
                                    nx.algorithms.dag.ancestors(self.graph, reduction))
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

    def expand_global_operations(self):
        self.outputs = collections.defaultdict(set)

        for node in self.global_operations:
            inputs = node.inputs
            outputs = node.outputs
            condition_needs = node.condition_needs

            self.graph.remove_node(node)

            color_order = ['worker', 'localCollector', 'globalCollector']
            worker_outputs = None
            local_collector_outputs = None

            for color in color_order:

                if color == 'worker':
                    worker_outputs = list(map(lambda o: o+'_worker', node.outputs))
                    worker_node = ReduceByKey(name=node.name+'_worker', inputs=inputs, outputs=worker_outputs,
                                              condition_needs=condition_needs)
                    worker_node.color = color
                    self.outputs[color].update(worker_outputs)
                    for i in inputs:
                        self.graph.add_edge(i, worker_node)
                    for o in worker_outputs:
                        self.graph.add_edge(worker_node, o)
                    for n in condition_needs:
                        self.graph.add_edge(n, worker_node)

                elif color == 'localCollector':
                    local_collector_outputs = list(map(lambda o: o+'_localCollector', node.outputs))
                    local_collector_node = ReduceByKey(name=node.name+'_localCollector', inputs=worker_outputs,
                                                       outputs=local_collector_outputs)
                    local_collector_node.color = color
                    self.outputs[color].update(local_collector_outputs)
                    for i in worker_outputs:
                        self.graph.add_edge(i, local_collector_node)
                    for o in local_collector_outputs:
                        self.graph.add_edge(local_collector_node, o)

                elif color == 'globalCollector':
                    global_collector_node = ReduceByKey(name=node.name+'_globalCollector',
                                                        inputs=local_collector_outputs,
                                                        outputs=outputs)
                    global_collector_node.color = color
                    for i in local_collector_outputs:
                        self.graph.add_edge(i, global_collector_node)
                    for o in outputs:
                        self.graph.add_edge(global_collector_node, o)

    def generate_filter_node(self, seen, filter_node, nodes):
        seen.update(nodes)
        nodes.pop(0)
        nodes.pop(0)
        subgraph = self.graph.subgraph(nodes)
        inputs = [n for n, d in subgraph.in_degree() if d == 0]
        inputs = list(it.chain.from_iterable([i.inputs for i in inputs]))
        outputs = [n for n, d in subgraph.out_degree() if d == 0]
        nodes = list(filter(lambda node: type(node) is not str, nodes))
        nodes = list(map(lambda node: node.to_operation(), nodes))

        node = filter_node.to_operation()
        node = node(name=filter_node.name,
                    condition_needs=filter_node.condition_needs, condition=filter_node.condition,
                    needs=inputs, provides=outputs)(*nodes)
        return node

    def compile(self):

        self.color_nodes()
        self.expand_global_operations()

        seen = set()
        branch_merge_candidates = [n for n, d in self.graph.in_degree() if d >= 2 and type(n) is str]
        graph_filters = list(filter(lambda node: isinstance(node, Filter), self.graph.nodes))
        outputs = [n for n, d in self.graph.out_degree() if d == 0]
        body = []

        filters_targets = list(it.product(graph_filters, branch_merge_candidates))
        for f, t in filters_targets:
            paths = list(nx.algorithms.all_simple_paths(self.graph, f, t))

            for nodes in paths:
                filter_node = self.generate_filter_node(seen, f, nodes)
                body.append(filter_node)

        filters_targets = list(it.product(graph_filters, outputs))
        for f, t in filters_targets:
            paths = list(nx.algorithms.all_simple_paths(self.graph, f, t))

            for nodes in paths:
                if any(map(lambda node: node in branch_merge_candidates, nodes)):
                    continue
                if seen.issuperset(nodes):
                    continue

                filter_node = self.generate_filter_node(seen, f, nodes)
                body.append(filter_node)

        for node in self.graph.nodes:
            if node in seen:
                continue
            if type(node) is str:
                continue
            body.append(node.to_operation())

        self.outputs['globalCollector'].update(outputs)

        return compose(name=self.name)(*body)

    def __call__(self, *args, **kwargs):
        if self.graphkit is None:
            self.graphkit = self.compile()
        color = kwargs.get('color', None)
        assert color is not None
        result = self.graphkit(*args, **kwargs)
        outputs = self.outputs[color]
        return {k: result[k] for k in outputs if k in result}


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

    def to_operation(self):
        assert len(self.color) == 1, 'too many colors'
        color = list(self.color)[0]
        return operation(name=self.name, needs=self.inputs, provides=self.outputs, color=color)(self.func)


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

    def __init__(self, name, condition_needs, outputs, condition=lambda cond: cond):
        super(FilterOn, self).__init__(name, condition_needs, outputs, condition)

    def to_operation(self):
        return If


class FilterOff(Filter):

    def __init__(self, name, condition_needs, outputs):
        super(FilterOff, self).__init__(name, condition_needs, outputs)

    def to_operation(self):
        return Else


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

    def to_operation(self):
        return operation(name=self.name, needs=self.inputs, provides=self.outputs, color=self.color)(self)


class ReduceByKey(StatefulTransformation):

    def __init__(self, name, inputs, outputs, condition_needs=[], reduction=operator.add):
        super(ReduceByKey, self).__init__(name=name, inputs=inputs, outputs=outputs,
                                          condition_needs=condition_needs, reduction=reduction)
        self.res = {}

    def __call__(self, *args, **kwargs):
        if len(args) == 2:
            k, v = args
            if k in self.res:
                self.res[k] = self.reduction(self.res[k], v)
            else:
                self.res[k] = v
        else:
            for r in args:
                for k, v in r.items():
                    if k in self.res:
                        self.res[k] = self.reduction(self.res[k], v)
                    else:
                        self.res[k] = v
            r = list(self.res.values())
            if len(r) == 1:
                return r[0]
        return self.res

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
