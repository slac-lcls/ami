from pyqtgraph.debug import printExc
from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode
from amitypes import Array1d, Array2d
import ami.graph_nodes as gn
import numpy as np
import scipy.ndimage.measurements as smt
import scipy.stats as stats


class BlobFinder(CtrlNode):

    """
    Find blobs in an image.
    """

    nodeName = "BlobFinder"
    uiTemplate = [('threshold', 'doubleSpin', {'value': 10, 'min': 0.01}),
                  ('min sum', 'doubleSpin', {'value': 1, 'min': 0.01})]

    def __init__(self, name):
        super().__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Array2d},
            'NBlobs': {'io': 'out', 'ttype': int},
            'X': {'io': 'out', 'ttype': Array1d},
            'Y': {'io': 'out', 'ttype': Array1d},
            'Sum': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        threshold = self.values['threshold']
        min_sum = self.values['min sum']

        def find_blobs(img):
            blobs, nblobs = smt.label(img > threshold)
            if nblobs > 0:
                index = np.arange(1, nblobs+1)
                adu_sum = smt.sum(img, blobs, index)
                x, y = zip(*smt.center_of_mass(img, blobs, index))
                x = np.array(x, dtype=np.float32)
                y = np.array(y, dtype=np.float32)
                ind, = np.where(adu_sum > min_sum)
                nblobs = ind.size
                adu_sum = adu_sum[ind]
                x = x[ind]
                y = y[ind]
            else:
                nblobs = 0
                x = np.zeros(0, dtype=np.float32)
                y = np.zeros(0, dtype=np.float32)
                adu_sum = np.zeros(0, dtype=np.float32)
            return nblobs, x, y, adu_sum

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions, inputs=inputs, outputs=outputs,
                      func=find_blobs,
                      parent=self.name())
        return node


class Linregress(Node):

    """
    Scipy.stats.linregress
    """

    nodeName = "Linregress"

    def __init__(self, name):
        super().__init__(name, terminals={'X': {'io': 'in', 'ttype': Array1d},
                                          'Y': {'io': 'in', 'ttype': Array1d},
                                          'slope': {'io': 'out', 'ttype': float},
                                          'intercept': {'io': 'out', 'ttype': float},
                                          'rvalue': {'io': 'out', 'ttype': float},
                                          'pvalue': {'io': 'out', 'ttype': float},
                                          'stderr': {'io': 'out', 'ttype': float},
                                          'fit': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        def fit(x, y):
            slope, intercept, r_value, p_value, stderr = stats.linregress(x, y)
            return slope, intercept, r_value, p_value, stderr, slope*x + intercept

        nodes = [gn.Map(name=self.name()+"_operation",
                        condition_needs=conditions, inputs=inputs, outputs=outputs,
                        func=fit, parent=self.name())]

        return nodes


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

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
                          func=FitProc(**self.values), parent=self.name())

            return node

except ImportError as e:
    print(e)
