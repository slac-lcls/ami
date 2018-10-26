import operator
import networkx as nx


class Graph():

    def __init__(self, name):
        self.name = name
        self.graph = nx.DiGraph()

    def add(self, op):
        for i in op.inputs:
            self.graph.add_edge(i, op)

        for o in op.outputs:
            self.graph.add_edge(op, o)

        for i in op.condition_needs:
            self.graph.add_edge(i, op)

    def compile(self):
        pass


class Transformation():

    def __init__(self, name, inputs, outputs, func, condition_needs=[]):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.func = func
        self.condition_needs = condition_needs

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return bool(self.name is not None and
                    self.name == getattr(other, 'name', None))


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
