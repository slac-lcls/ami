from ami.flowchart.library.DisplayWidgets import AreaDetWidget
from ami.flowchart.library.common import CtrlNode
from ami.graph_nodes import Map
import asyncio


class Roi(CtrlNode):

    nodeName = "Roi"
    uiTemplate = []
    # uiTemplate = [('sigma',  'spin', {'value': 1.0, 'step': 1.0, 'bounds': [0.0, None]})]

    def __init__(self, name):
        super(Roi, self).__init__(name, viewable=True)

    def display(self, inputs, addr, win):
        name, topic = inputs[0]
        if self.widget is None:
            self.widget = AreaDetWidget(name, topic, addr, win)
            self.task = asyncio.ensure_future(self.widget.update())
        return self.widget

    def to_operation(self, inputs, conditions=[]):
        outputs = [self.name()]

        if self.widget:
            func = self.widget.func
        else:
            def func(img):
                return img

        node = Map(name=self.name(), inputs=inputs, outputs=outputs, conditions=conditions, func=func)
        return node
