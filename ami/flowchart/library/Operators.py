from typing import Union, Any
from amitypes import Array1d, Array2d, Array3d
from ami.flowchart.library.common import CtrlNode, GroupedNode
from ami.flowchart.library.CalculatorWidget import CalculatorWidget, FilterWidget, gen_filter_func, sanitize_name
import ami.graph_nodes as gn
import numpy as np
import itertools
import collections


class Identity(GroupedNode):

    """
    Identity
    """

    nodeName = "Identity"

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any},
                                          "Out": {'io': 'out', 'ttype': Any}},
                         allowAddInput=True)

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name()+"_operation", **kwargs, func=lambda *args: args)


class MeanVsScan(CtrlNode):

    """
    MeanVsScan creates a histogram using a variable number of bins.

    Returns a dict with keys Bins and values mean of bins.
    """

    nodeName = "MeanVsScan"
    uiTemplate = [('binned', 'check', {'checked': False}),
                  ('bins', 'intSpin', {'value': 10, 'min': 1}),
                  ('min', 'intSpin', {'value': 0}),
                  ('max', 'intSpin', {'value': 10})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'Bin': {'io': 'in', 'ttype': float},
            'Value': {'io': 'in', 'ttype': float},
            'Bins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, outputs, **kwargs):
        outputs = self.output_vars()

        if self.values['binned']:
            bins = np.histogram_bin_edges(np.arange(self.values['min'], self.values['max']),
                                          bins=self.values['bins'],
                                          range=(self.values['min'], self.values['max']))
            map_outputs = [self.name()+'_bin', self.name()+'_map_count']
            reduce_outputs = [self.name()+'_reduce_count']

            def func(k, v):
                return np.digitize(k, bins), (v, 1)

            def mean(d):
                res = {bins[i]: 0 for i in range(0, bins.size)}
                for k, v in d.items():
                    try:
                        res[bins[k]] = v[0]/v[1]
                    except IndexError:
                        pass

                keys, values = zip(*sorted(res.items()))
                return np.array(keys), np.array(values)

            nodes = [
                gn.Map(name=self.name()+'_map', inputs=inputs, outputs=map_outputs,
                       func=func, **kwargs),
                gn.ReduceByKey(name=self.name()+'_reduce',
                               inputs=map_outputs, outputs=reduce_outputs,
                               reduction=lambda cv, v: (cv[0]+v[0], cv[1]+v[1]), **kwargs),
                gn.Map(name=self.name()+'_mean', inputs=reduce_outputs, outputs=outputs, func=mean,
                       **kwargs)
            ]
        else:
            map_outputs = [self.name()+'_map_count']
            reduce_outputs = [self.name()+'_reduce_count']

            def mean(d):
                res = {}
                for k, v in d.items():
                    res[k] = v[0]/v[1]
                keys, values = zip(*sorted(res.items()))
                return np.array(keys), np.array(values)

            nodes = [
                gn.Map(name=self.name()+'_map', inputs=[inputs['Value']], outputs=map_outputs,
                       func=lambda a: (a, 1), **kwargs),
                gn.ReduceByKey(name=self.name()+'_reduce',
                               inputs=[inputs['Bin']]+map_outputs, outputs=reduce_outputs,
                               reduction=lambda cv, v: (cv[0]+v[0], cv[1]+v[1]), **kwargs),
                gn.Map(name=self.name()+'_mean', inputs=reduce_outputs, outputs=outputs, func=mean,
                       **kwargs)
            ]

        return nodes


class MeanWaveformVsScan(CtrlNode):

    """
    MeanWaveformVsScan creates a 2d histogram using a variable number of bins.

    Returns a dict with keys Bins and values mean waveform of bins.
    """

    nodeName = "MeanWaveformVsScan"
    uiTemplate = [('binned', 'check', {'checked': False}),
                  ('bins', 'intSpin', {'value': 10, 'min': 1}),
                  ('min', 'intSpin', {'value': 0}),
                  ('max', 'intSpin', {'value': 10})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'Bin': {'io': 'in', 'ttype': float},
            'Value': {'io': 'in', 'ttype': Array1d},
            'X Bins': {'io': 'out', 'ttype': Array1d},
            'Y Bins': {'io': 'out', 'ttype': Array1d},
            'Counts': {'io': 'out', 'ttype': Array2d}
        })

    def to_operation(self, inputs, outputs, **kwargs):
        if self.values['binned']:
            bins = np.histogram_bin_edges(np.arange(self.values['min'], self.values['max']),
                                          bins=self.values['bins'],
                                          range=(self.values['min'], self.values['max']))
            map_outputs = [self.name()+'_bin', self.name()+'_map_count']
            reduce_outputs = [self.name()+'_reduce_count']

            def func(k, v):
                return np.digitize(k, bins), (v, 1)

            def mean(d):
                res = {}
                for k, v in d.items():
                    try:
                        res[bins[k]] = v[0]/v[1]
                    except IndexError:
                        pass

                missing_keys = set(bins).difference(res.keys())
                k, v = d.popitem()
                for k in missing_keys:
                    res[k] = np.zeros(v[0].shape)

                keys, values = zip(*sorted(res.items()))
                stack = np.stack(values, axis=1)
                return np.arange(0, stack.shape[0]), np.array(keys), stack

            nodes = [
                gn.Map(name=self.name()+'_map', inputs=inputs, outputs=map_outputs,
                       func=func, **kwargs),
                gn.ReduceByKey(name=self.name()+'_reduce',
                               inputs=map_outputs, outputs=reduce_outputs,
                               reduction=lambda cv, v: (cv[0]+v[0], cv[1]+v[1]), **kwargs),
                gn.Map(name=self.name()+'_mean', inputs=reduce_outputs, outputs=outputs, func=mean,
                       **kwargs)
            ]
        else:
            map_outputs = [self.name()+'_map_count']
            reduce_outputs = [self.name()+'_reduce_count']

            def mean(d):
                res = {}
                for k, v in d.items():
                    res[k] = v[0]/v[1]
                keys, values = zip(*sorted(res.items()))
                stack = np.stack(values, axis=1)
                return np.arange(0, stack.shape[0]), np.array(keys), stack

            nodes = [
                gn.Map(name=self.name()+'_map', inputs=[inputs['Value']], outputs=map_outputs,
                       func=lambda a: (a, 1), **kwargs),
                gn.ReduceByKey(name=self.name()+'_reduce',
                               inputs=[inputs['Bin']]+map_outputs, outputs=reduce_outputs,
                               reduction=lambda cv, v: (cv[0]+v[0], cv[1]+v[1]), **kwargs),
                gn.Map(name=self.name()+'_mean', inputs=reduce_outputs, outputs=outputs, func=mean,
                       **kwargs)
            ]

        return nodes


class Combinations(CtrlNode):

    """
    Generate combinations using itertools.combinations.
    """

    nodeName = "Combinations"
    uiTemplate = [('length', 'intSpin', {'value': 1, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})
        self.output_terms = []

    def state_changed(self, *args, **kwargs):
        super().state_changed(*args, **kwargs)

        while len(self.output_vars()) > self.values['length']:
            self.removeTerminal(self.output_terms.pop())

        while len(self.output_vars()) < self.values['length']:
            self.output_terms.append(self.addOutput())

    def to_operation(self, **kwargs):
        length = self.values['length']

        def func(*args):
            r = list(map(np.array, zip(*itertools.combinations(*args, length))))
            if r:
                return r
            else:
                return [np.array([])]*length

        return gn.Map(name=self.name()+"_operation", func=func, **kwargs)


class Export(CtrlNode):

    """
    Send data back to worker.
    """

    nodeName = "Export"
    uiTemplate = [('alias', 'text')]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any}},
                         exportable=True)


try:
    import sympy

    class CalcProc():

        def __init__(self, params):
            self.params = params
            self.func = None

        def __call__(self, *args, **kwargs):
            # note: args get passed in order of input terminals on node from top to bottom
            # sympy symbols need to be defined in same order for this to work correctly
            if self.func is None:
                self.func = sympy.lambdify(**self.params, modules=["numpy", "scipy"])

            args = list(args)
            for idx, arg in enumerate(args):
                if type(arg) is np.ndarray:
                    args[idx] = arg.astype(np.float64, copy=False)

            return self.func(*args, **kwargs)

    class Calculator(CtrlNode):
        """
        Calculator
        """

        nodeName = "Calculator"

        def __init__(self, name):
            super().__init__(name,
                             terminals={'In': {'io': 'in', 'ttype': Union[float, Array1d,
                                                                          Array2d, Array3d]},
                                        'Out': {'io': 'out', 'ttype': Any}},
                             allowAddInput=True)

            self.values = {'operation': ''}

        def isChanged(self, restore_ctrl, restore_widget):
            return restore_widget

        def display(self, topics, terms, addr, win, **kwargs):
            if self.widget is None:
                self.widget = CalculatorWidget(terms, win, self.values['operation'])
                self.widget.sigStateChanged.connect(self.state_changed)

            return self.widget

        def to_operation(self, **kwargs):
            args = []
            expr = self.values['operation']

            # sympy doesn't like symbols name likes Sum.0.Out, need to remove dots.
            for arg in self.input_vars().values():
                rarg = sanitize_name(arg)
                args.append(rarg)
                expr = expr.replace(arg, rarg)

            params = {'args': args,
                      'expr': expr}

            return gn.Map(name=self.name()+"_operation", **kwargs, func=CalcProc(params))

except ImportError as e:
    print(e)


try:
    from ami.flowchart.library.PythonEditorWidget import PythonEditorWidget
    import tempfile
    import importlib

    class PythonEditorProc(object):

        def __init__(self, text):
            self.text = text
            self.file = None
            self.mod = None

        def __call__(self, *args, **kwargs):
            if self.file is None:
                self.file = tempfile.NamedTemporaryFile(mode='w', suffix='.py')
                self.file.write(self.text)
                self.file.flush()
                spec = importlib.util.spec_from_file_location("module.name", self.file.name)
                self.mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.mod)

            return self.mod.func(*args, **kwargs)

        def __del__(self):
            if self.file:
                del self.mod
                self.file.close()

    class PythonEditor(CtrlNode):
        """
        Write a python function.
        """

        nodeName = "PythonEditor"

        def __init__(self, name):
            super().__init__(name,
                             terminals={'In': {'io': 'in', 'ttype': Any},
                                        'Out': {'io': 'out', 'ttype': Any}},
                             allowAddInput=True,
                             allowAddOutput=True)
            self.values = {'text': ''}

        def isChanged(self, restore_ctrl, restore_widget):
            return restore_widget

        def display(self, topics, terms, addr, win, **kwargs):
            if self.widget is None:
                self.widget = PythonEditorWidget(self.input_vars(), self.output_vars(), win, self.values['text'])
                self.widget.sigStateChanged.connect(self.state_changed)

            return self.widget

        def to_operation(self, **kwargs):
            return gn.Map(name=self.name()+"_operation", **kwargs, func=PythonEditorProc(self.values['text']))

    class Filter(CtrlNode):
        """
        Filter
        """

        nodeName = "Filter"

        def __init__(self, name):
            super().__init__(name,
                             terminals={'In': {'io': 'in', 'ttype': Any},
                                        'Out': {'io': 'out', 'ttype': Any}},
                             allowAddInput=True,
                             allowAddOutput=True)
            self.values = collections.defaultdict(dict)

        def display(self, topics, terms, addr, win, **kwargs):
            if self.widget is None:
                self.widget = FilterWidget(terms, self.output_vars(), win)
                self.widget.sigStateChanged.connect(self.state_changed)

            return self.widget

        def to_operation(self, **kwargs):
            values = self.values
            inputs = list(self.input_vars().values())
            outputs = list(self.output_vars())

            for idx, inp in enumerate(inputs):
                inputs[idx] = sanitize_name(inp)

            func = gen_filter_func(values, inputs, outputs)
            return gn.Map(name=self.name()+"_operation", **kwargs, func=PythonEditorProc(func))

except ImportError as e:
    print(e)
