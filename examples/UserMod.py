import ami.graph_nodes as gn
from ami.flowchart.library.common import CtrlNode
from amitypes import Array1d


class TestNode(CtrlNode):

    """
    Test
    """

    nodeName = "Test"
    uiTemplate = [('spin', 'intSpin', {'value': 0})]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                          'Out': {'io': 'out', 'ttype': Array1d}})

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions, inputs=inputs, outputs=outputs,
                      func=lambda img: img, parent=self.name())
        return node
