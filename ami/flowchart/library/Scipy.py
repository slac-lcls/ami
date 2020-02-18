from ami.flowchart.library.common import CtrlNode, MAX
from ami.flowchart.library.DisplayWidgets import FitWidget
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
    uiTemplate = [('threshold', 'doubleSpin', {'value': 10, 'min': 0.01, 'max': MAX}),
                  ('min sum', 'doubleSpin', {'value': 1, 'min': 0.01, 'max': MAX})]

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

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=find_blobs,
                      parent=self.name())
        return node


class Linregress(CtrlNode):

    """
    Scipy.stats.linregress
    """

    nodeName = "Linregress"

    def __init__(self, name):
        super().__init__(name, terminals={'X': {'io': 'in', 'ttype': Array1d},
                                          'Y': {'io': 'in', 'ttype': Array1d}},
                         buffered=True)

    def buffered_topics(self):
        topics = super().buffered_topics()
        topics[self.name()+".Fit"] = self.name()+".Fit"
        return topics

    def buffered_terms(self):
        terms = self.input_vars()
        terms["Fit"] = self.name()+".Fit"
        return terms

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, FitWidget, **kwargs)

    def to_operation(self, inputs, conditions={}):
        outputs = [self.name()+".X", self.name()+".Y", self.name()+".Fit"]

        def fit(x, y):
            slope, intercept, r_value, p_value, stderr = stats.linregress(x, y)
            return x, y, intercept + slope*x

        nodes = [gn.Map(name=self.name()+"_operation",
                        condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                        func=fit, parent=self.name())]

        return nodes
