import ami.graph_nodes as gn
from ami.flowchart.library.common import CtrlNode
from amitypes import Array1d, Peaks
import numpy as np


class HSDPeakTest(CtrlNode):

    """
    HSDPeakTest
    """

    nodeName = "HSDPeakTest"

    def __init__(self, name):
        super().__init__(name, terminals={'Waveform': {'io': 'in', 'ttype': Array1d},
                                          'Peaks': {'io': 'in', 'ttype': Peaks},
                                          'Pass': {'io': 'out', 'ttype': int},
                                          'Fail': {'io': 'out', 'ttype': int}})

    def to_operation(self, **kwargs):

        def func(waveform, peaks):
            for i in range(len(peaks[0])):
                swf = peaks[1][i]
                s0 = peaks[0][i]
                ns = len(swf)
                if s0+ns >= len(waveform):
                    break
                if not np.array_equal(swf, waveform[s0:s0+ns]):
                    return 0, 1
            return 1, 0

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)
