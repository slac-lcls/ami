import abc
import operator
from networkfox import operation, If, Else, Var


class Transformation(abc.ABC):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            inputs (list): List of inputs
            outputs (list): List of outputs
            func (function): Function node will call
            condition_needs (list): List of condition needs
        """
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
        """
        Two nodes are considered equal if their name is equal.

        Args:
            other (Transformation): Node to compare against.
        """
        return bool(self.name is not None and
                    self.name == getattr(other, 'name', None))

    def __repr__(self):
        return u"%s(name='%s', color='%s')" % (self.__class__.__name__, self.name, self.color)

    def to_operation(self):
        """
        Return NetworkFoX operation node.
        """
        return operation(name=self.name, needs=self.inputs, provides=self.outputs, color=self.color)(self.func)


class Map(Transformation):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            inputs (list): List of inputs
            outputs (list): List of outputs
            func (function): Function node will call
            condition_needs (list): List of condition needs
        """
        super(Map, self).__init__(**kwargs)


class Filter(abc.ABC):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            condition_needs (list): List of condition needs
            outputs (list): List of outputs
            condition (function): Condition to evaluate
        """
        self.name = kwargs['name']
        self.condition_needs = kwargs['condition_needs']
        self.inputs = []
        self.outputs = kwargs['outputs']
        self.color = ""

    @abc.abstractmethod
    def to_operation(self):
        return

    def __repr__(self):
        return u"%s(name='%s', color='%s')" % (self.__class__.__name__, self.name, self.color)


class FilterOn(Filter):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            condition_needs (list): List of condition needs
            outputs (list): List of outputs
            condition (function): Condition to evaluate
        """
        self.condition = kwargs.get('condition', lambda cond: cond)
        super(FilterOn, self).__init__(**kwargs)

    def to_operation(self):
        """
        Return NetworkFoX If node.
        """
        return If


class FilterOff(Filter):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            condition_needs (list): List of condition needs
            outputs (list): List of outputs
        """
        super(FilterOff, self).__init__(**kwargs)

    def to_operation(self):
        """
        Return NetworkFoX Else node.
        """
        return Else


class StatefulTransformation(Transformation):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            inputs (list): List of inputs
            outputs (list): List of outputs
            condition_needs (list): List of condition needs
            reduction (function): Reduction function
        """

        reduction = kwargs.pop('reduction', None)

        kwargs.setdefault('func', None)
        super(StatefulTransformation, self).__init__(**kwargs)

        if reduction:
            assert hasattr(reduction, '__call__'), 'reduction is not callable'
        self.reduction = reduction

    @abc.abstractmethod
    def __call__(self, *args, **kwargs):
        return

    @abc.abstractmethod
    def reset(self):
        """
        Reset nodes state.
        """
        return

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
        self.clear = False
        self.is_global_operation = True

    def __call__(self, *args):
        if self.clear:
            self.res = [None]*self.N
            self.clear = False

        if len(args) > 1:
            args = [args]
        elif len(args) == 1 and type(args[0]) is list:
            args = args[0]

        for arg in args:
            self.res[self.idx] = arg
            self.idx = (self.idx + 1) % self.N

        if not any(x is None for x in self.res):
            self.clear = True
            if self.N > 1:
                return self.res
            elif self.N == 1:
                return self.res[0]

    def reset(self):
        self.res = [None]*self.N


def Binning(name="", inputs=[], outputs=[], condition_needs=[]):
    """

    """

    assert len(inputs) == 2
    assert len(outputs) == 1

    k, v = inputs
    outputs = outputs[0]
    map_outputs = [Var(name=outputs.name+'_count', type=tuple)]
    reduce_outputs = [Var(name=outputs.name+'_reduce', type=dict)]

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
