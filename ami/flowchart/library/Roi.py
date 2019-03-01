from ami.flowchart.library.DisplayWidgets import AreaDetWidget
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn
import asyncio
import numpy as np


class Roi(CtrlNode):

    nodeName = "Roi"
    uiTemplate = [('origin x',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('origin y',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('extent x',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('extent y',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647})]

    def __init__(self, name):
        super(Roi, self).__init__(name,
                                  terminals={'In': {'io': 'in', 'type': np.ndarray},
                                             'Out': {'io': 'out', 'type': np.ndarray}},
                                  viewable=True)
        self.origin_x = 0
        self.origin_y = 0
        self.extent_x = 0
        self.extent_y = 0
        self.func = lambda img: img

    def display(self, inputs, addr, win):
        name, topic = inputs[0]
        if self.widget is None:
            self.widget = AreaDetWidget(name, topic, addr, win)
            self.widget.roi.sigRegionChangeFinished.connect(self.changed)

        if self.task is None:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def update(self, *args, **kwargs):
        roi = None
        if len(args) == 1:
            roi = args[0]

        if roi:
            extent, _, origin = roi.getAffineSliceParams(self.widget.image, self.widget.getImageItem())
            self.origin_x = int(origin[0])
            self.origin_y = int(origin[1])
            self.extent_x = int(extent[0])
            self.extent_y = int(extent[1])
            ctrl = self.ctrls['origin x']
            ctrl.setValue(self.origin_x)
            ctrl = self.ctrls['origin y']
            ctrl.setValue(self.origin_y)
            ctrl = self.ctrls['extent x']
            ctrl.setValue(self.extent_x)
            ctrl = self.ctrls['extent y']
            ctrl.setValue(self.extent_y)
        else:
            self.origin_x = self.ctrls['origin x'].value()
            self.origin_y = self.ctrls['origin y'].value()
            self.extent_x = self.ctrls['extent x'].value()
            self.extent_y = self.ctrls['extent y'].value()

        origin_x = self.origin_x
        origin_y = self.origin_y
        extent_x = self.extent_x
        extent_y = self.extent_y

        def func(img):
            return img[slice(origin_x, extent_x), slice(origin_y, extent_y)]

        self.func = func

    def to_operation(self, inputs, outputs, conditions=[]):
        outputs = [gn.Var(self.name(), type=np.ndarray)]

        node = gn.Map(name=self.name()+"_operation",
                      inputs=inputs, outputs=outputs, conditions=conditions,
                      func=self.func)
        return node
