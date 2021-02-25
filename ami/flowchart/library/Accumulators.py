from amitypes import Array1d, T
from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn


class Pick1(Node):

    """
    Pick1 collects one of its input.
    """

    nodeName = "Pick1"

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': T},
                                    'Out': {'io': 'out', 'ttype': T}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=inputs, outputs=outputs, condition_needs=conditions,
                        N=1, parent=self.name())
        return node


class PickN(CtrlNode):

    """
    PickN collects N of its input.
    """

    nodeName = "PickN"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': T},
                                    'Out': {'io': 'out', 'ttype': Array1d}},
                         allowAddInput=True)

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=inputs, outputs=outputs, condition_needs=conditions,
                        N=self.values['N'], parent=self.name())
        return node
