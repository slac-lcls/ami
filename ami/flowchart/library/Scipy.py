from pyqtgraph.debug import printExc
from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode
from amitypes import Array1d, Array2d
import ami.graph_nodes as gn
import numpy as np
import scipy.stats as stats
import scipy.ndimage as ndimage


try:
    from psana.peakFinder import blobfinder

    class BlobFinder1D(CtrlNode):

        """
        Find blobs in a waveform.
        """

        nodeName = "BlobFinder1D"
        uiTemplate = [('threshold', 'doubleSpin'),
                      ('min sum', 'doubleSpin')]

        def __init__(self, name):
            super().__init__(name, terminals={
                'In': {'io': 'in', 'ttype': Array1d},
                'NBlobs': {'io': 'out', 'ttype': int},
                'X': {'io': 'out', 'ttype': Array1d},
                'Sum': {'io': 'out', 'ttype': Array1d}
            })

        def to_operation(self, **kwargs):
            threshold = self.values['threshold']
            min_sum = self.values['min sum']

            return gn.Map(name=self.name()+"_operation", **kwargs,
                          func=lambda arr: blobfinder.find_blobs_1d(arr, threshold, min_sum))

    class BlobFinder2D(CtrlNode):

        """
        Find blobs in an image.
        """

        nodeName = "BlobFinder2D"
        uiTemplate = [('threshold', 'doubleSpin'),
                      ('min sum', 'doubleSpin')]

        def __init__(self, name):
            super().__init__(name, terminals={
                'In': {'io': 'in', 'ttype': Array2d},
                'NBlobs': {'io': 'out', 'ttype': int},
                'X': {'io': 'out', 'ttype': Array1d},
                'Y': {'io': 'out', 'ttype': Array1d},
                'Sum': {'io': 'out', 'ttype': Array1d}
            })

        def to_operation(self, **kwargs):
            threshold = self.values['threshold']
            min_sum = self.values['min sum']

            return gn.Map(name=self.name()+"_operation", **kwargs,
                          func=lambda arr: blobfinder.find_blobs_2d(arr, threshold, min_sum))

except ImportError as e:
    print(e)


class Linregress0D(CtrlNode):

    """
    Collect N scalars and apply Scipy.stats.linregress
    """

    nodeName = "Linregress0D"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name, terminals={'X.In': {'io': 'in', 'ttype': float},
                                          'Y.In': {'io': 'in', 'ttype': float},
                                          'X': {'io': 'out', 'ttype': Array1d},
                                          'Y': {'io': 'out', 'ttype': Array1d},
                                          'Fit': {'io': 'out', 'ttype': Array1d},
                                          'rvalue': {'io': 'out', 'ttype': float}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        def fit(arr):
            arr = np.array(arr)
            slope, intercept, r_value, p_value, stderr = stats.linregress(arr[:, 0], arr[:, 1])
            return arr[:, 0], arr[:, 1], slope*arr[:, 0] + intercept, r_value

        picked_outputs = [self.name()+"_accumulated"]
        nodes = [gn.PickN(name=self.name()+"_picked",
                          inputs=inputs, outputs=picked_outputs,
                          N=self.values['N'], **kwargs),
                 gn.Map(name=self.name()+"_operation",
                        inputs=picked_outputs, outputs=outputs,
                        func=fit, **kwargs)]

        return nodes


class Linregress1D(Node):

    """
    Scipy.stats.linregress
    """

    nodeName = "Linregress1D"

    def __init__(self, name):
        super().__init__(name, terminals={'X': {'io': 'in', 'ttype': Array1d},
                                          'Y': {'io': 'in', 'ttype': Array1d},
                                          'slope': {'io': 'out', 'ttype': float},
                                          'intercept': {'io': 'out', 'ttype': float},
                                          'rvalue': {'io': 'out', 'ttype': float},
                                          'pvalue': {'io': 'out', 'ttype': float},
                                          'stderr': {'io': 'out', 'ttype': float},
                                          'fit': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, **kwargs):
        def fit(x, y):
            slope, intercept, r_value, p_value, stderr = stats.linregress(x, y)
            return slope, intercept, r_value, p_value, stderr, slope*x + intercept

        return gn.Map(name=self.name()+"_operation", **kwargs, func=fit)


try:
    import sympy as sp
    import scipy.optimize as optimize

    class FitProc():

        def __init__(self, *args, **kwargs):
            self.expr = kwargs['expr']
            self.step_size = kwargs['step size']
            self.p0 = kwargs.get('init vals', None)
            self.func = None

        def set_func(self):
            """
            scipy.curve_fit requires a function with x as the first argument
            so we need to reorder arguments
            """
            func = sp.sympify(self.expr)
            x = sp.Symbol('x')
            syms = list(func.free_symbols)
            syms.remove(x)
            syms.insert(0, x)
            return sp.lambdify(syms, func, modules=["numpy", "scipy"])

        def __call__(self, y, *args, **kwargs):
            if self.func is None:
                self.func = self.set_func()

            x = np.arange(0, y.size, 1)
            try:
                best_vals, covar = optimize.curve_fit(self.func, x, y, p0=self.p0)
                return self.func(x, *best_vals)
            except RuntimeError:
                printExc()

            return np.array([])

    class CurveFit(CtrlNode):
        """
        Fit a function to data.
        """

        nodeName = "CurveFit"
        uiTemplate = [('expr', 'text'),
                      ('step size', 'intSpin', {'value': 1, 'min': 1})]

        def __init__(self, name):
            super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                              'Out': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, **kwargs):
            return gn.Map(name=self.name()+"_operation", **kwargs, func=FitProc(**self.values))

except ImportError as e:
    print(e)


class GaussianFilter1D(CtrlNode):

    """
    Scipy Gaussian Filter 1D
    """

    nodeName = "GaussianFilter1D"

    uiTemplate = [('sigma', 'doubleSpin'),
                  ('axis', 'intSpin', {'value': -1, 'min': -1, 'max': 1}),
                  ('order', 'intSpin'),
                  ('mode', 'combo', {'value': 'reflect',
                                     'values': ['reflect', 'constant', 'nearest', 'mirror', 'wrap']}),
                  ('cval', 'doubleSpin'),
                  ('truncate', 'doubleSpin', {'value': 4.0})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, **kwargs):
        args = dict(self.values)

        return gn.Map(name=self.name()+"_operation", **kwargs,
                      func=lambda arr: ndimage.gaussian_filter1d(arr, **args))


class Rotate(CtrlNode):

    """
    Scipy.ndimage.rotate
    """

    nodeName = "Rotate"

    uiTemplate = [('angle', 'doubleSpin')]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}})

    def to_operation(self, **kwargs):
        args = dict(self.values)

        return gn.Map(name=self.name()+"_operation", **kwargs,
                      func=lambda arr: ndimage.rotate(arr, **args))
