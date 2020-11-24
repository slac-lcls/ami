import abc
import operator
import numpy as np
from networkfox import operation, If


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

        inputs = kwargs['inputs']
        if type(inputs) is dict:
            self.inputs = list(inputs.values())
        else:
            self.inputs = inputs

        outputs = kwargs['outputs']
        if type(outputs) is dict:
            self.outputs = list(outputs.values())
        else:
            self.outputs = outputs

        condition_needs = kwargs.get('condition_needs', [])
        if type(condition_needs) is dict:
            self.condition_needs = list(condition_needs.values())
        else:
            self.condition_needs = condition_needs

        self.func = kwargs['func']
        self.parent = kwargs.get('parent', None)
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
        return u"%s(name='%s', color='%s', inputs=%s, outputs=%s, condition_needs=%s)" % \
            (self.__class__.__name__, self.name, self.color, self.inputs, self.outputs, self.condition_needs)

    def to_operation(self):
        """
        Return NetworkFoX operation node.
        """
        return operation(name=self.name, needs=self.inputs, provides=self.outputs, color=self.color,
                         metadata={'parent': self.parent})(self.func)


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
        super().__init__(**kwargs)


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

        self.inputs = []

        outputs = kwargs['outputs']
        if type(outputs) is dict:
            self.outputs = list(outputs.values())
        else:
            self.outputs = outputs

        condition_needs = kwargs['condition_needs']
        if type(condition_needs) is dict:
            self.condition_needs = list(condition_needs.values())
        else:
            self.condition_needs = condition_needs

        self.parent = kwargs.get('parent', None)
        self.color = ""
        self.is_global_operation = False

    @abc.abstractmethod
    def to_operation(self):
        return

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
        super().__init__(**kwargs)

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
        self.condition = kwargs.get('condition', lambda cond: not cond)
        super().__init__(**kwargs)

    def to_operation(self):
        """
        Return NetworkFoX Else node.
        """
        return If


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
        super().__init__(**kwargs)

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

    def heartbeat_finished(self):
        """
        Execute at the end of a heartbeat.
        """
        return

    def to_operation(self):
        return operation(name=self.name, needs=self.inputs, provides=self.outputs,
                         color=self.color, metadata={'parent': self.parent})(self)


class GlobalTransformation(StatefulTransformation):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            inputs (list): List of inputs
            outputs (list): List of outputs
            condition_needs (list): List of condition needs
            reduction (function): Reduction function
            is_expanded (bool): Indicates this node's input comes another part
                of the expanded operation
            num_contributors (int): the number of contributors providing input
                to this part of the global operation
        """
        is_expanded = kwargs.pop('is_expanded', False)
        num_contributors = kwargs.pop('num_contributors', None)
        super().__init__(**kwargs)
        self.is_global_operation = True
        self.is_expanded = is_expanded
        self.num_contributors = num_contributors

    def on_expand(self):
        """
        Called when expanding a global operation to get an extra kwargs that
        should be passed to the expanded nodes when they are constructed.

        This is intended to be overrided by subclasses if they need this!

        Returns:
            Dictionary of keyword arguments to pass when constructing the
            globally expanded version of this operation
        """
        return {"parent": self.parent}


class ReduceByKey(GlobalTransformation):

    def __init__(self, **kwargs):
        kwargs.setdefault('reduction', operator.add)
        super().__init__(**kwargs)
        self.res = {}

    def __call__(self, *args, **kwargs):
        if len(args) == 2:
            # worker
            k, v = args
            if k in self.res:
                self.res[k] = self.reduction(self.res[k], v)
            else:
                self.res[k] = v
        else:
            # localCollector, globalCollector
            for r in args:
                for k, v in r.items():
                    if k in self.res:
                        self.res[k] = self.reduction(self.res[k], v)
                    else:
                        self.res[k] = v
        return self.res

    def reset(self):
        self.res = {}

    def heartbeat_finished(self):
        if self.color != 'globalCollector':
            self.reset()


class Accumulator(GlobalTransformation):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.res_factory = kwargs.pop('res_factory', lambda: 0)
        assert hasattr(self.res_factory, '__call__'), 'res_factory is not callable'
        self.res = self.res_factory()

    def __call__(self, *args, **kwargs):
        self.res = self.reduction(self.res, *args)
        return self.res

    def reset(self):
        self.res = self.res_factory()

    def heartbeat_finished(self):
        if self.color != 'globalCollector':
            self.reset()

    def on_expand(self):
        return {'parent': self.parent, 'res_factory': self.res_factory}


class PickN(GlobalTransformation):

    def __init__(self, **kwargs):
        N = kwargs.pop('N', 1)
        super().__init__(**kwargs)
        self.N = N
        self.idx = 0
        self.res = [None]*self.N
        self.clear = False

    def __call__(self, *args):
        if self.clear:
            self.res = [None]*self.N
            self.clear = False

        if len(args) > 1:
            args = [args]
        elif self.is_expanded and len(args) == 1 and type(args[0]) is list and self.N > 1:
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


class RollingBuffer(GlobalTransformation):

    def __init__(self, **kwargs):
        N = kwargs.pop('N', 1)
        use_numpy = kwargs.pop('use_numpy', False)
        super().__init__(**kwargs)
        self.N = N
        self.use_numpy = use_numpy
        self.idx = 0
        self.count = 0
        self.res = None if use_numpy else []

    def __call__(self, *args):

        if len(args) == 1:
            dims = 0
            args = args[0]
        else:
            dims = len(args)

        if self.is_expanded:
            if self.count == 0:
                self.idx = 0
            self.count = (self.count + 1) % self.num_contributors

        if self.use_numpy:
            if self.is_expanded:
                dtype = args.dtype
                if len(args) > self.N:
                    nelem = self.N
                    args = args[..., -self.N:]
                else:
                    nelem = len(args)
            else:
                dtype = type(args)
                nelem = 1
            if self.res is None:
                self.res = np.zeros(self.N, dtype=dtype)
            self.idx += nelem
            self.res = np.roll(self.res, -nelem)
            self.res[..., -nelem:] = [args] if dims else args
        else:
            if self.is_expanded:
                self.res.extend(args)
                self.idx = min(self.idx + len(args), self.N)
            else:
                self.res.append(args)
                self.idx = min(self.idx + 1, self.N)
            self.res = self.res[-self.idx:]

        return self.res[-self.idx:]

    def on_expand(self):
        return {'parent': self.parent, 'use_numpy': self.use_numpy}

    def reset(self):
        self.idx = 0
