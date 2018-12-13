import operator
import networkx as nx
import itertools as it
import collections
import sys
from graphkit import operation, If, Else, compose


class Graph():

    def __init__(self, name):
        self.name = name
        self.graph = nx.DiGraph()
        self.graphkit = None
        self.global_operations = set()
        self.expanded_global_operations = set()
        self.inputs = collections.defaultdict(set)
        self.outputs = collections.defaultdict(set)
        self.flattened_inputs = collections.defaultdict(set)

    def add(self, ops):
        if type(ops) is not list:
            ops = [ops]

        for op in ops:
            for i in op.inputs:
                self.graph.add_edge(i, op)

            for o in op.outputs:
                self.graph.add_edge(op, o)

            for i in op.condition_needs:
                self.graph.add_edge(i, op)

        self.graphkit = None

    def remove(self, name):
        for n in self.graph.nodes:
            if type(n) is str:
                continue
            if n.name == name:
                desc = nx.dag.descendants(self.graph, n)
                self.graph.remove_nodes_from(desc)
                self.graph.remove_node(n)
                break

        self.graphkit = None

    def reset(self):
        nodes = filter(lambda node: isinstance(StatefulTransformation, node), self.graph.nodes)
        map(lambda node: node.reset(), nodes)

    def color_nodes(self):
        """
        Generate all paths from inputs to outputs, for each path look for nodes which have the is_global_operation
        attribute set to True. If in a given path for which we've found a node global operation node there is no
        other node with is_global_operation true preceeds it then we mark that node for expansion.
        """
        inputs = [n for n, d in self.graph.in_degree() if d == 0]
        outputs = [n for n, d in self.graph.out_degree() if d == 0]

        self.global_operations = set()
        sources_targets = list(it.product(inputs, outputs))
        for s, t in sources_targets:
            paths = list(nx.algorithms.all_simple_paths(self.graph, s, t))
            for nodes in paths:
                reductions = list(filter(lambda node: getattr(node, 'is_global_operation', False), nodes))

                for reduction in reductions:
                    if reduction in self.expanded_global_operations:
                        continue
                    before = list(filter(lambda node: getattr(node, 'is_global_operation', False),
                                         nx.algorithms.dag.ancestors(self.graph, reduction)))
                    if before == []:
                        self.global_operations.add(reduction)

                color = 'worker'
                for node in nodes:
                    if type(node) is str:
                        continue

                    if node in self.global_operations or node in self.expanded_global_operations:
                        color = 'globalCollector'
                    if node.color == "":
                        node.color = color

    def expand_global_operations(self, num_workers, num_local_collectors):
        inputs = [n for n, d in self.graph.in_degree() if d == 0]
        self.flattened_inputs['worker'].update(inputs)

        for node in self.global_operations:
            inputs = node.inputs
            outputs = node.outputs
            condition_needs = node.condition_needs

            self.graph.remove_node(node)
            NewNode = getattr(sys.modules[__name__], node.__class__.__name__)

            color_order = ['worker', 'localCollector', 'globalCollector']
            worker_outputs = None
            local_collector_outputs = None
            for color in color_order:

                if color == 'worker':
                    worker_outputs = list(map(lambda o: o+'_worker', node.outputs))

                    worker_N = 1
                    if hasattr(node, 'N'):
                        worker_N = max(node.N // num_workers, 1)

                    worker_node = NewNode(name=node.name+'_worker', inputs=inputs, outputs=worker_outputs,
                                          condition_needs=condition_needs, reduction=node.reduction, N=worker_N)
                    worker_node.color = color
                    worker_node.is_global_operation = False
                    self.outputs[color].update(worker_outputs)
                    for i in inputs:
                        self.graph.add_edge(i, worker_node)
                    for o in worker_outputs:
                        self.graph.add_edge(worker_node, o)
                    for n in condition_needs:
                        self.graph.add_edge(n, worker_node)

                elif color == 'localCollector':
                    self.flattened_inputs[color].update(worker_outputs)
                    local_collector_outputs = list(map(lambda o: o+'_localCollector', node.outputs))

                    local_collector_N = 1
                    if hasattr(node, 'N'):
                        local_collector_N = max(node.N // num_local_collectors, 1)

                    local_collector_node = NewNode(name=node.name+'_localCollector', inputs=worker_outputs,
                                                   outputs=local_collector_outputs, reduction=node.reduction,
                                                   N=local_collector_N)
                    local_collector_node.color = color
                    local_collector_node.is_global_operation = False
                    self.outputs[color].update(local_collector_outputs)
                    for i in worker_outputs:
                        self.graph.add_edge(i, local_collector_node)
                    for o in local_collector_outputs:
                        self.graph.add_edge(local_collector_node, o)

                elif color == 'globalCollector':
                    self.flattened_inputs[color].update(local_collector_outputs)

                    N = getattr(node, 'N', 1)
                    N = max((N // num_workers)*num_workers, 1)

                    global_collector_node = NewNode(name=node.name+'_globalCollector',
                                                    inputs=local_collector_outputs,
                                                    outputs=outputs, reduction=node.reduction, N=N)
                    global_collector_node.color = color
                    self.expanded_global_operations.add(global_collector_node)
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

    def compile(self, num_workers=1, num_local_collectors=1):
        self.inputs = collections.defaultdict(set)
        self.color_nodes()
        self.expand_global_operations(num_workers, num_local_collectors)

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
        self.find_inputs()

        self.graphkit = compose(name=self.name)(*body)

    def find_inputs(self):
        graph_filters = list(filter(lambda node: isinstance(node, Filter), self.graph.nodes))
        # {"branch": {"worker": set(), "localCollector": set(), "globalCollector": set()}}
        inputs = collections.defaultdict(lambda: collections.defaultdict(set))
        seen = set()

        for color, color_inputs in self.flattened_inputs.items():
            sources_targets = list(it.product(graph_filters, color_inputs))

            for s, t in sources_targets:
                paths = list(nx.algorithms.all_simple_paths(self.graph, s, t))

                if paths:
                    inputs[s.name][color].add(t)
                    seen.add(t)

            for i in color_inputs:
                if i not in seen:
                    inputs[None][color].add(i)

        self.inputs = inputs

    def __call__(self, *args, **kwargs):
        assert self.graphkit is not None, "call compile first"

        color = kwargs.get('color', None)
        assert color is not None
        keys = args[0].keys()

        for branch, colors_inputs in self.inputs.items():
            if colors_inputs[color] and all(i in keys for i in colors_inputs[color]):
                result = self.graphkit(*args, **kwargs)
                outputs = self.outputs[color]
                return {k: result[k] for k in outputs if k in result}


class Transformation():

    def __init__(self, **kwargs):
        self.name = kwargs['name']
        self.inputs = kwargs['inputs']
        self.outputs = kwargs['outputs']
        self.func = kwargs['func']
        self.condition_needs = kwargs.get('condition_needs', [])
        self.color = ""
        self.is_global_operation = False

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return bool(self.name is not None and
                    self.name == getattr(other, 'name', None))

    def __repr__(self):
        return u"%s(name='%s')" % (self.__class__.__name__, self.name)

    def to_operation(self):
        return operation(name=self.name, needs=self.inputs, provides=self.outputs, color=self.color)(self.func)


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
        self.color = ""


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

    def __init__(self, **kwargs):
        reduction = kwargs.pop('reduction', None)

        kwargs.setdefault('func', None)
        super(StatefulTransformation, self).__init__(**kwargs)

        if reduction:
            assert hasattr(reduction, '__call__'), 'reduction is not callable'
        self.reduction = reduction

    def reset(self):
        raise NotImplementedError

    def to_operation(self):
        return operation(name=self.name, needs=self.inputs, provides=self.outputs, color=self.color)(self)


class ReduceByKey(StatefulTransformation):

    def __init__(self, **kwargs):
        kwargs.setdefault('reduction', operator.add)
        super(ReduceByKey, self).__init__(**kwargs)
        self.res = {}
        self.is_global_operation = True

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
        return self.res

    def reset(self):
        self.res = {}


class Accumulator(StatefulTransformation):

    def __init__(self, **kwargs):
        super(Accumulator, self).__init__(**kwargs)
        self.res = []

    def __call__(self, *args, **kwargs):
        self.res.extend(args)

        if self.reduction:
            return self.reduction(self.res)
        return self.res

    def reset(self):
        self.res = []


class PickN(StatefulTransformation):

    def __init__(self, **kwargs):
        N = kwargs.pop('N', 1)
        super(PickN, self).__init__(**kwargs)
        self.N = N
        self.idx = 0
        self.res = [None]*self.N
        self.reset = False
        self.is_global_operation = True

    def __call__(self, args):
        if self.reset:
            self.res = [None]*self.N
            self.reset = False

        if type(args) is not list:
            args = [args]

        for arg in args:
            self.res[self.idx] = arg
            self.idx = (self.idx + 1) % self.N

        if not any(x is None for x in self.res):
            self.reset = True
            if self.N > 1:
                return self.res
            elif self.N == 1:
                return self.res[0]

    def reset(self):
        pass


def Binning(name="", inputs=[], outputs=[], condition_needs=[]):
    assert len(inputs) == 2
    assert len(outputs) == 1

    k, v = inputs
    outputs = outputs[0]
    map_outputs = [outputs+'_count']
    reduce_outputs = [outputs+'_reduce']

    def mean(d):
        res = {}
        for k, v in d.items():
            res[k] = v[0]/v[1]
        return res

    nodes = [
        Map(name=name+'_map', inputs=[v], outputs=map_outputs, condition_needs=condition_needs, func=lambda a: (a, 1)),
        ReduceByKey(name=name+'_reduce', inputs=[k]+map_outputs, outputs=reduce_outputs,
                    reduction=lambda cv, v: (cv[0]+v[0], cv[1]+v[1])),
        Map(name=name+'_mean', inputs=reduce_outputs, outputs=[outputs], func=mean)
    ]

    return nodes
