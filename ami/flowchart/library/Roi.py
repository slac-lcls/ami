from ami.flowchart.library.DisplayWidgets import AreaDetWidget
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn
import asyncio
import numpy as np


class Roi(CtrlNode):

    nodeName = "Roi"
    uiTemplate = [('origin x',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('extent x',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('origin y',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('extent y',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647})]
    desc = "Region of Interest"

    def __init__(self, name):
        super(Roi, self).__init__(name,
                                  terminals={'In': {'io': 'in', 'type': np.ndarray},
                                             'Out': {'io': 'out', 'type': np.ndarray}},
                                  viewable=True)
        self.func = lambda img: img

    def display(self, topics, addr, win, **kwargs):
        if self.widget is None:
            self.widget = AreaDetWidget(topics, addr, win)
            self.widget.roi.sigRegionChangeFinished.connect(self.setValues)

        if self.task is None:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def setValues(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        roi = args[0]
        extent, _, origin = roi.getAffineSliceParams(self.widget.image, self.widget.getImageItem())
        self.origin_x = int(origin[0])
        self.origin_y = int(origin[1])
        self.extent_x = int(extent[0])
        self.extent_y = int(extent[1])
        self.ctrls['origin x'].setValue(self.origin_x)
        self.ctrls['extent x'].setValue(self.extent_x)
        self.ctrls['origin y'].setValue(self.origin_y)
        self.ctrls['extent y'].setValue(self.extent_y)
        self.setFunc()
        self.stateGroup.blockSignals(False)

    def update(self, *args, **kwargs):
        self.origin_x = self.ctrls['origin x'].value()
        self.origin_y = self.ctrls['origin y'].value()
        self.extent_x = self.ctrls['extent x'].value()
        self.extent_y = self.ctrls['extent y'].value()
        self.setFunc()

    def setFunc(self):
        origin_x = self.origin_x
        origin_y = self.origin_y
        extent_x = self.extent_x
        extent_y = self.extent_y

        def func(img):
            return img[slice(origin_x, extent_x), slice(origin_y, extent_y)]

        self.func = func

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=self.func)
        return node
