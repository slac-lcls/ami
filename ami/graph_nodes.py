import abc
import operator
import numpy as np
from networkfox import operation
from networkfox.modifiers import GraphWarning


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
        self.begin_run_func = kwargs.get('begin_run', None)
        self.end_run_func = kwargs.get('end_run', None)
        self.begin_step_func = kwargs.get('begin_step', None)
        self.end_step_func = kwargs.get('end_step', None)
        self.exportable = False
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
        return u"%s(name='%s', color='%s', inputs=%s, outputs=%s, parent=%s)" % \
            (self.__class__.__name__, self.name, self.color, self.inputs, self.outputs, self.parent)

    def to_operation(self):
        """
        Return NetworkFoX operation node.
        """
        return operation(name=self.name, needs=self.inputs, provides=self.outputs, color=self.color,
                         metadata={'parent': self.parent})(self.func)

    def begin_run(self, color=""):
        if color == self.color and callable(self.begin_run_func):
            return self.begin_run_func()

    def end_run(self, color=""):
        if color == self.color and callable(self.end_run_func):
            return self.end_run_func()

    def begin_step(self, step, color=""):
        if color == self.color and callable(self.begin_step_func):
            return self.begin_step_func(step)

    def end_step(self, step, color=""):
        if color == self.color and callable(self.end_step_func):
            return self.end_step_func(step)


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
        self.count = 0

    def __call__(self, *args, **kwargs):
        if self.is_expanded:
            count, values = args
            if not (isinstance(values, list) or isinstance(values, tuple)):
                values = (values,)
        else:
            count = 1
            values = args

        self.res = self.reduction(self.res, *values)
        self.count += count

        return self.count, self.res

    def reset(self):
        self.res = self.res_factory()
        self.count = 0

    def heartbeat_finished(self):
        if self.color != 'globalCollector':
            self.reset()

    def on_expand(self):
        return {'parent': self.parent, 'res_factory': self.res_factory}


class PickN(GlobalTransformation):

    def __init__(self, **kwargs):
        N = kwargs.pop('N', 1)
        exportable = kwargs.pop('exportable', False)
        super().__init__(**kwargs)
        self.N = N
        self.exportable = exportable
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


class SumN(GlobalTransformation):

    def __init__(self, **kwargs):
        N = kwargs.pop('N', 1)
        exportable = kwargs.pop('exportable', False)
        super().__init__(**kwargs)
        self.N = N
        self.exportable = exportable
        self.count = 0
        self.res = None
        self.clear = False

    def __call__(self, *args, **kwargs):
        if self.clear:
            self.count = 0
            self.res = None
            self.clear = False

        if self.is_expanded:
            count, value = args
        else:
            count = 1
            value = args[0]

        self.count += count

        if self.res is None:
            if isinstance(value, np.ndarray):
                value = value.astype(np.float32)
            self.res = value
        else:
            self.res = np.add(self.res, value)

        if self.count >= self.N:
            self.clear = True
            return self.count, self.res
        else:
            return None, None

    def reset(self):
        self.count = 0
        self.res = None


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
        if self.is_expanded:
            count = args[0]
            args = args[1]
        else:
            count = 1
            if len(args) == 1:
                args = args[0]
            # all inputs are optional
            elif len(args) == 0 and len(kwargs) > 0:
                args = list(kwargs.values())
            elif len(args) > 0 and len(kwargs) > 0:
                raise Exception("RollingBuffer currently does not support mixing required and optional arguments.")

        self.count += count

        if self.is_expanded: # this case is for collectors: args = buffer
            # Logic to prevent self.res have a memory footprint > N
            if len(args) + len(self.res) < self.N:
                self.res.extend(args)
            else:
                # remove exactly enough to have a list of size N after addition of the new data
                remove = len(self.res) + len(args) - self.N
                self.res[:remove] = []
                self.res.extend(args)
            self.idx = min(self.idx + len(args), self.N)
        else: # this case is for workers:  args = data
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

        # returning like this ensure that a copy of self.res is returned, not the same object
        return self.count, self.res[-self.idx:]

    def on_expand(self):
        return {'parent': self.parent, 'use_numpy': self.use_numpy, 'unique': self.unique}

    def reset(self):
        self.idx = 0
        self.count = 0

class AMIWarning(GraphWarning):
    pass
