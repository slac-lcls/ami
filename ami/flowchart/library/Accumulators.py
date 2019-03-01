from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn


class Pick1(CtrlNode):

    nodeName = "Pick1"
    uiTemplate = []

    def __init__(self, name):
        super(Pick1, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'type': object},
                                               'Out': {'io': 'out', 'type': object}})

    def to_operation(self, inputs, conditions=[]):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=inputs, outputs=outputs, condition_needs=conditions,
                        N=1)
        return node


class PickN(CtrlNode):

    nodeName = "PickN"
    uiTemplate = [('N', 'intSpin', {'value': 2, 'min': 2, 'max': 4096})]

    def __init__(self, name):
        super(PickN, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'type': object},
                                               'Out': {'io': 'out', 'type': (type(None), list)}})
        self.N = 2

    def to_operation(self, inputs, conditions=[]):
        outputs = self.output_vars()
        node = gn.PickN(name=self.name()+"_operation",
                        inputs=inputs, outputs=outputs, condiiton_needs=conditions,
                        N=self.N)
        return node
