from typing import TypeVar, List
from ami.flowchart.Node import Node
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn

T = TypeVar('T')


class Pick1(Node):

    """
    Pick1 collects one of its input.
    """

    nodeName = "Pick1"

    def __init__(self, name):
        super(Pick1, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'ttype': T},
                                               'Out': {'io': 'out', 'ttype': T}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=list(inputs.values()), outputs=outputs, condition_needs=list(conditions.values()),
                        N=1, parent=self.name())
        return node


class PickN(CtrlNode):

    """
    PickN collects N of its input.
    """

    nodeName = "PickN"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2, 'max': 4096})]

    def __init__(self, name):
        super(PickN, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'ttype': T},
                                               'Out': {'io': 'out', 'ttype': List[T]}},
                                    allowAddInput=True)
        self.N = 2

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=list(inputs.values()), outputs=outputs, condition_needs=list(conditions.values()),
                        N=self.N, parent=self.name())
        return node
