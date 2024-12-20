from pyqtgraph.debug import printExc
from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode
from amitypes import Array1d, Array2d
import ami.graph_nodes as gn
import numpy as np
import scipy.stats as stats
import scipy.ndimage as ndimage


def gaussian_func(x, ampl, mu, sigma):
    return ampl * np.exp( -(x-mu)**2/(2.0*sigma**2) )
    #return ampl *   np.exp( -(x-mu)**2/(2.0*sigma**2) )

def lorentzian_func(x, ampl, x0, gamma):
    return ampl * ( gamma / ((x-x0)**2 + gamma**2) )

def stats_from_moments(x, y=None):
    """
    Weigted mean, sigma, and skew.
    Use case is typically for quick stats on a gaussian-like
    distribution.

    Parameters
    ----------
    x: np.ndarray
        values
    y: np.ndarray
        weights
    """
    if y is None:
        y = np.ones_like(x)
    #y = np.abs(y)  # negative values in the baseline screw things up
    mean = np.sum(x*y) / np.sum(y)
    variance = np.sum((x-mean)**2*y) / y.sum()
    sigma = np.sqrt(variance)
    skew = np.sum((x-mean)**3*y) / sigma**3
    return mean, sigma, skew


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
            self.expr = kwargs['f']
            self.p0 = kwargs['p0']
            self.syms = kwargs['variables']

            if not self.p0:
                self.p0 = None
            else:
                self.p0 = tuple(map(float, self.p0.split(',')))
            self.func = None

        def set_func(self):
            """
            scipy.curve_fit requires a function with x as the first argument
            so we need to reorder arguments
            """
            func = sp.sympify(self.expr)
            return sp.lambdify(self.syms, func, modules=["numpy", "scipy"])

        def __call__(self, y, *args, **kwargs):
            if self.func is None:
                self.func = self.set_func()
                self.x = np.arange(0, y.size, 1)

            if args:
                x = args[0]
            else:
                x = self.x

            try:
                popt, covar = optimize.curve_fit(self.func, x, y, p0=self.p0)
                return self.func(x, *popt), popt, covar
            except RuntimeError:
                printExc()

            return np.array([])

    class CurveFit(CtrlNode):
        """
        Calls scipy.optimize.curve_fit to fit a function to its inputs.
        """

        nodeName = "CurveFit"
        uiTemplate = [('f', 'text', {'tip': "Function to fit."}),
                      ('variables', 'text', {'tip': "Comma separated list of variables in f."}),
                      ('p0', 'text', {'tip': "Optional comma separated list of initial guesses."})]

        def __init__(self, name):
            super().__init__(name, terminals={'Y': {'io': 'in', 'ttype': Array1d},
                                              'fx': {'io': 'out', 'ttype': Array1d},
                                              'p0': {'io': 'out', 'ttype': Array1d},
                                              'pcov': {'io': 'out', 'ttype': Array2d}},
                             allowAddInput=True)

        def addInput(self, **args):
            if "X" not in self.terminals:
                self.addTerminal(name="X", io='in', ttype=Array1d, **args)

        def to_operation(self, **kwargs):
            return gn.Map(name=self.name()+"_operation", **kwargs, func=FitProc(**self.values))



    class FitPeakProc():

        def __init__(self, *args, **kwargs):
            self.model = kwargs['Model']
            self.use_offset = kwargs['Use offset']
            self.a_0 = kwargs['Initial amplitude']
            self.x_0 = kwargs['Initial x0']
            self.fwhm_0 = kwargs['Initial FWHM']
            self.c_0 = kwargs['Initial offset']
            self.func = None

        def get_func(self):
            if self.model == "Gaussian":
                sigma_0 = self.fwhm_0 / 2.355
                if self.use_offset:
                    p0 = [self.a_0, self.x_0, sigma_0, self.c_0]
                    func = lambda x, a, mu, sig, c: gaussian_func(x, a, mu, sig) + c
                    return func, p0
                else:
                    p0 = [self.a_0, self.x_0, sigma_0]
                    return gaussian_func, p0

            elif self.model == "Lorentzian":
                gamma_0 = self.fwhm_0 / 2
                if self.use_offset:
                    p0 = [self.a_0, self.x_0, gamma_0, self.c_0]
                    func = lambda x, a, x0, gamma, c: lorentzian_func(x, a, x0, gamma) + c
                    return func, p0
                else:
                    p0 = [self.a_0, self.x_0, gamma_0]
                    return lorentzian_func, p0

            elif self.model == "Moments":
                return stats_from_moments, None
            return

        def __call__(self, y, *args, **kwargs):
            if self.func is None:
                self.func, self.p0 = self.get_func()

            x = np.arange(0, y.size, 1)

            if self.p0 is None:
                # Calculate moments and make-up a gaussian
                # Dirtier but faster
                mean, sigma, skew = self.func(x, y=y)
                fwhm = 2.355 * sigma
                ampl = np.max(y)
                y = gaussian_func(x, ampl, mean, sigma)
                return y, ampl, mean, sigma, fwhm, 0.0

            try:
                # Real fits
                best_vals, covar = optimize.curve_fit(self.func, x, y, p0=self.p0)
                if self.model == "Gaussian":
                    fwhm = 2.355 * best_vals[2]
                elif self.model == "Lorentzian":
                    fwhm = 2 * best_vals[2]

                if self.use_offset:
                    return self.func(x, *best_vals), best_vals[0], best_vals[1], best_vals[2], fwhm, best_vals[3]
                else:
                    return self.func(x, *best_vals), best_vals[0], best_vals[1], best_vals[2], fwhm, 0.0
            except Exception as e:  # catch a number of fitting errors
                raise gn.AMIWarning(e)

            return np.array([])


    class PeakFit(CtrlNode):
        """
        Fit a peak to 1d data
        Models:
            Gaussian
            Lorentzian
        """

        nodeName = "PeakFit"
        uiTemplate = [('Model', 'combo', {'values':['Gaussian', 'Lorentzian', 'Moments']}),
                      ('Use offset', 'check', {'checked': True}),
                      ('Initial amplitude', 'doubleSpin', {'value': 1}),
                      ('Initial x0', 'doubleSpin'),
                      ('Initial FWHM', 'doubleSpin', {'value': 1}),
                      ('Initial offset', 'doubleSpin')]

        def __init__(self, name):
            super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                              'fit': {'io': 'out', 'ttype': Array1d},
                                              'ampl': {'io': 'out', 'ttype': float},
                                              'center': {'io': 'out', 'ttype': float},
                                              'width': {'io': 'out', 'ttype': float},
                                              'fwhm': {'io': 'out', 'ttype': float},
                                              'offset': {'io': 'out', 'ttype': float}})

        def to_operation(self, **kwargs):
            return gn.Map(name=self.name()+"_operation", **kwargs, func=FitPeakProc(**self.values))

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
