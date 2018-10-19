from graphkit import compose, operation, If, Else
import collections
import operator


class Graph():

    def __init__(self, name):
        self.name = name
        self.steps = []
        self.graph = None

        # { (condition_needs): {'filter_on': {'ops': [], 'outputs': set()},
        #                       'filter_off': {'ops': [], 'outputs': set()}}},
        self.branches = collections.defaultdict(dict)

        # by default there are no condition needs until we do a filter,
        # we store this as default and remove one level of dictionaries
        # ie self.branches['default'] = {'ops': [], 'outputs': set()}
        branch = self.branches['default']
        branch['ops'] = []
        branch['outputs'] = set()

    def __call__(self, *args, **kwargs):
        if self.graph is None:
            self.graph = self.compile()
        return self.graph(*args, **kwargs)

    def add(self, op):
        if isinstance(op, Filter):
            branch = self.branches[tuple(op.condition_needs)]
            if 'filter_on' not in branch:
                branch['filter_on'] = {'ops': [], 'outputs': set(), 'if': {}}

            if 'filter_off' not in branch:
                branch['filter_off'] = {'ops': [], 'outputs': set(), 'else': {}}

        self.steps.append(op)

        return self

    def remove(self, op):
        self.graph = None

    def reset(self):
        for node in self.steps:
            if isinstance(node, StatefulTransformation):
                node.reset()

    def compile(self):
        branch = self.branches['default']
        ops = branch['ops']
        color = 'worker'
        filter_on = None
        filter_off = None

        for op in self.steps:

            if hasattr(op, 'inputs'):
                op_inputs = set(op.inputs)

                for need, brnch in self.branches.items():
                    if need == 'default':
                        continue

                    if op_inputs.issubset(brnch['filter_on']['outputs']) and \
                       op_inputs.issubset(brnch['filter_off']['outputs']):
                        branch = self.branches['default']
                        ops = branch['ops']
                        filter_on = None
                        filter_off = None
                        break

            if isinstance(op, Map):
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs, color=color)(op.func))
            elif isinstance(op, ReduceByKey):
                color = 'localCollector'
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs, color=color)(op))
            elif isinstance(op, Accumulator):
                ops.append(operation(name=op.name, needs=op.inputs, provides=op.outputs, color=color)(op))
            elif isinstance(op, FilterOn):
                branch = self.branches[tuple(op.condition_needs)]
                filter_on = branch['filter_on']
                filter_on['if'] = {'name': op.name, 'condition_needs': op.condition_needs,
                                   'condition': op.condition}
                ops = filter_on['ops']
                filter_off = None
            elif isinstance(op, FilterOff):
                branch = self.branches[tuple(op.condition_needs)]
                filter_off = branch['filter_off']
                filter_off['else'] = {'name': op.name}
                ops = filter_off['ops']
                filter_on = None

            if hasattr(op, 'outputs'):
                op_outputs = set(op.outputs)
                if filter_on:
                    filter_on['outputs'].update(op_outputs)
                elif filter_off:
                    filter_off['outputs'].update(op_outputs)
                else:
                    branch['outputs'].update(op_outputs)

        default = self.branches.pop('default')
        graph = default['ops']
        for key, branches in self.branches.items():
            if_args = branches['filter_on']['if']
            if_args['needs'] = branches['filter_on']['ops'][0].needs
            if_args['provides'] = branches['filter_on']['ops'][-1].provides

            graph.append(If(**if_args)(*branches['filter_on']['ops']))

            if branches['filter_off']['else']:
                else_args = branches['filter_off']['else']
                else_args['needs'] = branches['filter_off']['ops'][0].needs
                else_args['provides'] = branches['filter_off']['ops'][-1].provides

                graph.append(Else(**else_args)(*branches['filter_off']['ops']))

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


class Filter():

    def __init__(self, name, condition_needs, condition=None):
        self.name = name
        self.condition_needs = condition_needs
        self.condition = condition


class FilterOn(Filter):

    def __init__(self, name, condition_needs, condition=lambda cond: cond is True):
        super(FilterOn, self).__init__(name, condition_needs, condition)


class FilterOff(Filter):

    def __init__(self, name, condition_needs):
        super(FilterOff, self).__init__(name, condition_needs)


class StatefulTransformation(Transformation):

    def __init__(self, name, inputs, outputs, func, condition_needs=None, reduction=None):
        super(StatefulTransformation, self).__init__(name, inputs, outputs, func, condition_needs)
        if reduction:
            assert hasattr(reduction, '__call__'), 'reduction is not callable'
        self.reduction = reduction

    def reset(self):
        raise NotImplementedError


class ReduceByKey(StatefulTransformation):

    def __init__(self, name, inputs, outputs, func=lambda *args: args, condition_needs=None, reduction=operator.add):
        super(ReduceByKey, self).__init__(name, inputs, outputs, func, condition_needs, reduction)
        self.res = {}

    def __call__(self, *args, **kwargs):
        f = map(self.func, args)

        for r in f:
            for k, v in r[0].items():
                if k in self.res:
                    self.res[k] = self.reduction(self.res[k], v)
                else:
                    self.res[k] = v
        return self.res.values()

    def reset(self):
        self.res = {}


class Accumulator(StatefulTransformation):

    def __init__(self, name, inputs, outputs, func=lambda a: a, condition_needs=None, reduction=None):
        super(Accumulator, self).__init__(name, inputs, outputs, func, condition_needs, reduction)
        self.res = []

    def __call__(self, *args, **kwargs):
        self.res.append(self.func(*args, **kwargs))

        if self.reduction:
            return self.reduction(self.res)
        return self.res

    def reset(self):
        self.res = []
