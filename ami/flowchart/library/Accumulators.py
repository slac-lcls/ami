from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn


class Pick1(Node):

    nodeName = "Pick1"
    desc = "Pick1"

    def __init__(self, name):
        super(Pick1, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'type': object},
                                               'Out': {'io': 'out', 'type': object}})

    def to_operation(self, inputs, conditions=[]):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=list(inputs.values()), outputs=outputs, condition_needs=list(conditions.values()),
                        N=1)
        return node


class PickN(CtrlNode):

    nodeName = "PickN"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2, 'max': 4096})]
    desc = "PickN"

    def __init__(self, name):
        super(PickN, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'type': object},
                                               'Out': {'io': 'out', 'type': (type(None), list, tuple)}},
                                    allowAddInput=True)
        self.N = 2

    def to_operation(self, inputs, conditions=[]):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=list(inputs.values()), outputs=outputs, condiiton_needs=list(conditions.values()),
                        N=self.N)
        return node
