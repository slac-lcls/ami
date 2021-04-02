import abc
import operator
import numpy as np
from networkfox import operation


class Transformation(abc.ABC):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            inputs (list): List of inputs
            outputs (list): List of outputs
            func (function): Function node will call
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

        self.func = kwargs['func']
        self.parent = kwargs.get('parent', None)
        self.color = kwargs.get('color', "")
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
        return u"%s(name='%s', color='%s', inputs=%s, outputs=%s)" % \
            (self.__class__.__name__, self.name, self.color, self.inputs, self.outputs)

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
        """
        super().__init__(**kwargs)


class StatefulTransformation(Transformation):

    def __init__(self, **kwargs):
        """
        Keyword Arguments:
            name (str): Name of node
            inputs (list): List of inputs
            outputs (list): List of outputs
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

    def __call__(self, *args, **kwargs):
        if self.clear:
            self.res = [None]*self.N
            self.clear = False

        if not args and kwargs:
            args = list(kwargs.values())
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
        unique = kwargs.pop('unique', False)
        super().__init__(**kwargs)
        self.N = N
        self.use_numpy = use_numpy
        self.unique = unique
        self.idx = 0
        self.count = 0
        self.res = None if use_numpy else []

    def __call__(self, *args, **kwargs):
        if len(args) == 1:
            dims = 0
            args = args[0]
        elif args:
            dims = len(args)
        elif kwargs:
            args = [kwargs.get(arg, np.nan) for arg in self.inputs]
            dims = len(args)
            if len(args) == 1:
                dims = 0
                args = args[0]

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
                if not self.unique:
                    self.res.append(args)
                    self.idx = min(self.idx + 1, self.N)
                elif self.unique:
                    if len(self.res) == 0:
                        self.res.append(args)
                        self.idx = min(self.idx + 1, self.N)
                    elif self.res[self.idx-1] != args:
                        self.res.append(args)
                        self.idx = min(self.idx + 1, self.N)
            self.res = self.res[-self.idx:]

        return self.res[-self.idx:]

    def on_expand(self):
        return {'parent': self.parent, 'use_numpy': self.use_numpy, 'unique': self.unique}

    def reset(self):
        self.idx = 0
