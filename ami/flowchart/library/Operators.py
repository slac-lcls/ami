from ami.flowchart.library.common import CtrlNode, MAX
from ami.flowchart.Node import Node
from amitypes import Array, Array1d, Array2d
from typing import Dict
import ami.graph_nodes as gn
import numpy as np


class Sum(Node):

    """
    Sum returns the sum of an array.
    """

    nodeName = "Sum"

    def __init__(self, name):
        super(Sum, self).__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Array},
            'Out': {'io': 'out', 'ttype': float}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda a: np.sum(a, dtype=np.float64))
        return node


class Projection(CtrlNode):

    """
    Projection projects a 2d array along the selected axis.
    """

    nodeName = "Projection"
    uiTemplate = [('axis', 'intSpin', {'value': 0, 'min': 0, 'max': 1})]

    def __init__(self, name):
        super(Projection, self).__init__(name, terminals={
            'In': {'io': 'in', 'ttype': Array2d},
            'Out': {'io': 'out', 'ttype': Array1d}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        axis = self.axis
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda a: np.sum(a, axis=axis))
        return node


class BinByVar(Node):

    """
    BinByVar creates a histogram using a variable number of bins.

    Returns a dict with keys Bins and values mean of bins.
    """

    nodeName = "BinByVar"

    def __init__(self, name):
        super(BinByVar, self).__init__(name, terminals={
            'Values': {'io': 'in', 'ttype': float},
            'Bins': {'io': 'in', 'ttype': float},
            'Out': {'io': 'out', 'ttype': Dict[float, float]}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        ordered_inputs = [inputs['Bins'], inputs['Values']]
        node = gn.Binning(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=ordered_inputs, outputs=outputs)
        return node


class Binning(CtrlNode):

    """
    Binning creates a histogram with a fixed number of bins.
    """

    nodeName = "Binning"
    uiTemplate = [('bins', 'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('range min', 'intSpin', {'value': 1, 'min': 1, 'max': MAX}),
                  ('range max', 'intSpin', {'value': 100, 'min': 2, 'max': MAX})]

    def __init__(self, name):
        super(Binning, self).__init__(name, terminals={
            'In': {'io': 'in', 'ttype': float},
            'Out': {'io': 'out', 'ttype': Dict[float, float]}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [self.name()+"_hist"]
        nbins = self.bins
        rmin = self.range_min
        rmax = self.range_max

        def bin(arr):
            counts, bins = np.histogram(arr, bins=nbins, range=(rmin, rmax))
            return dict(zip(bins, counts))

        node = [gn.Map(name=self.name()+"_map",
                       conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=map_outputs,
                       func=bin),
                gn.ReduceByKey(name=self.name()+"_reduce", inputs=map_outputs, outputs=outputs)]
        return node


try:
    import scipy.ndimage.measurements as smt

    class BlobFinder(CtrlNode):

        """
        Find blobs in an image.
        """

        nodeName = "BlobFinder"
        uiTemplate = [('threshold', 'doubleSpin', {'value': 10, 'min': 0.01, 'max': MAX}),
                      ('min sum', 'doubleSpin', {'value': 1, 'min': 0.01, 'max': MAX})]

        def __init__(self, name):
            super(BlobFinder, self).__init__(name, terminals={
                'In': {'io': 'in', 'ttype': Array2d},
                'NBlobs': {'io': 'out', 'ttype': int},
                'X': {'io': 'out', 'ttype': Array1d},
                'Y': {'io': 'out', 'ttype': Array1d},
                'Sum': {'io': 'out', 'ttype': Array1d}
            })
            self.set_func()

        def update(self, *args, **kwargs):
            self.set_func()

        def set_func(self):
            threshold = self.threshold
            min_sum = self.min_sum

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

            self.func = find_blobs

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()
            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=self.func)
            return node

except ImportError:
    pass
