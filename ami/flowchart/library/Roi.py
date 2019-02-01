from ami.flowchart.library.common import CtrlNode
from ami.graph_nodes import Map


class Roi(CtrlNode):

    nodeName = "Roi"
    uiTemplate = [
        ('row', 'intSpin', {'min': 0, 'max': 1024}),
        ('col', 'intSpin', {'min': 0, 'max': 1024})
    ]

    def to_operation(self):
        row = slice(self.ctrls['row'].value())
        col = slice(self.ctrls['col'].value())

        def func(img):
            return img[row, col]

        return Map(name=self.name, inputs=[self.name+"_input"], outputs=[self.name+"_output"], func=func)
