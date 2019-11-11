from ami.flowchart.library.common import CtrlNode, MAX
from amitypes import Array1d, Array2d
import ami.graph_nodes as gn
import numpy as np
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
