from ami.flowchart.library.common import CtrlNode
from ami.flowchart.Node import Node
import ami.graph_nodes as gn
import numpy as np


class Sum(Node):

    nodeName = "Sum"
    desc = "Sum"

    def __init__(self, name):
        super(Sum, self).__init__(name, terminals={
            'In': {'io': 'in', 'type': (type(None), np.ndarray, list)},
            'Out': {'io': 'out', 'type': np.float64}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=lambda a: np.sum(a, dtype=np.float64))
        return node


class BinByVar(Node):

    nodeName = "BinByVar"
    desc = "BinByVar"

    def __init__(self, name):
        super(BinByVar, self).__init__(name, terminals={
            'Values': {'io': 'in', 'type': np.float64},
            'Bins': {'io': 'in', 'type': (int, np.float64)},
            'Out': {'io': 'out', 'type': dict}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        ordered_inputs = [inputs['Bins'], inputs['Values']]
        node = gn.Binning(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=ordered_inputs, outputs=outputs)
        return node


class Binning(CtrlNode):

    nodeName = "Binning"
    uiTemplate = [('bins', 'intSpin', {'value': 10, 'min': 1, 'max': 2147483647}),
                  ('range min', 'intSpin', {'value': 1, 'min': 1, 'max': 2147483647}),
                  ('range max', 'intSpin', {'value': 100, 'min': 2, 'max': 2147483647})]
    desc = "Binning"

    def __init__(self, name):
        super(Binning, self).__init__(name, terminals={
            'In': {'io': 'in', 'type': (int, np.float64)},
            'Out': {'io': 'out', 'type': dict}
        })

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        map_outputs = [gn.Var(name=self.name()+"_hist", type=dict)]
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
