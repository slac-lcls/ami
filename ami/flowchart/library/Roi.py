from ami.flowchart.library.DisplayWidgets import AreaDetWidget, WaveformWidget
from ami.flowchart.library.common import CtrlNode
import pyqtgraph as pg
import ami.graph_nodes as gn
import asyncio
import numpy as np


class Roi(CtrlNode):

    """
    Region of Interest of image.

    Accepts 2D array.
    """

    nodeName = "Roi"
    uiTemplate = [('origin x',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('extent x',  'intSpin', {'value': 10, 'min': 1, 'max': 2147483647}),
                  ('origin y',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('extent y',  'intSpin', {'value': 10, 'min': 1, 'max': 2147483647})]
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
            self.widget.roi.sigRegionChangeFinished.connect(self.set_values)
            self.widget.ui.roiBtn.setChecked(True)
            self.widget.ui.roiBtn.hide()
            self.widget.roiClicked()
        if self.task is None:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def set_values(self, *args, **kwargs):
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
        self.set_func()
        self.stateGroup.blockSignals(False)

    def update(self, *args, **kwargs):
        self.origin_x = self.ctrls['origin x'].value()
        self.origin_y = self.ctrls['origin y'].value()
        self.extent_x = self.ctrls['extent x'].value()
        self.extent_y = self.ctrls['extent y'].value()
        self.set_func()
        if self.widget:
            self.widget.roi.setPos(self.origin_x, y=self.origin_y, finish=False)
            self.widget.roi.setSize((self.extent_x, self.extent_y), finish=False)

    def set_func(self):
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


class Roi1D(CtrlNode):

    """
    Collects scalars into array and returns selected region of interest.

    Accepts int, np.float64. Returns np.ndarray.
    """

    nodeName = "Roi1D"
    uiTemplate = [("Num Points", 'intSpin', {'value': 100, 'min': 1, 'max': 2147483647}),
                  ('origin',  'intSpin', {'value': 0, 'min': 0, 'max': 2147483647}),
                  ('extent',  'intSpin', {'value': 10, 'min': 1, 'max': 2147483647})]
    desc = "Region of Interest"

    def __init__(self, name):
        super(Roi1D, self).__init__(name, terminals={"In": {"io": "in", "type": (int, np.float64)},
                                                     "Out": {"io": "out", "type": np.ndarray}},
                                    buffered=True)
        self.func = lambda img: img

    def display(self, topics, addr, win, **kwargs):
        if self.widget is None:
            k, v = topics.popitem()
            v = v+"_picked1"
            topics = {k: v}
            self.widget = WaveformWidget(topics, addr, win, **kwargs)
            self.widget.roi = pg.LinearRegionItem((0, 10), swapMode='block')
            self.widget.roi.setBounds((0, None))
            self.widget.plot_view.addItem(self.widget.roi)
            self.widget.roi.sigRegionChangeFinished.connect(self.set_values)
        if self.task is None and self.widget:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        roi = args[0]
        origin, extent = roi.getRegion()
        self.origin = int(origin)
        self.extent = int(extent)
        self.ctrls['origin'].setValue(self.origin)
        self.ctrls['extent'].setValue(self.extent)
        self.set_func()
        self.stateGroup.blockSignals(False)

    def update(self, *args, **kwargs):
        self.origin = self.ctrls['origin'].value()
        self.extent = self.ctrls['extent'].value()
        self.set_func()
        if self.widget:
            self.widget.roi.setRegion((self.origin, self.extent))

    def set_func(self):
        origin = self.origin
        extent = self.extent

        def func(arr):
            return arr[slice(origin, extent)]

        self.func = func

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        buffer_outputs = [gn.Var(name=self.name()+"_buffered", type=np.ndarray)]
        pick1_outputs = [gn.Var(name=self.name()+"_picked1", type=object)]

        nodes = [gn.RollingBuffer(name=self.name()+"_buffer", N=self.Num_Points, use_numpy=True,
                                  conditions_needs=list(conditions.values()), inputs=list(inputs.values()),
                                  outputs=buffer_outputs),
                 gn.PickN(name=self.name()+"_pick1", inputs=buffer_outputs, outputs=pick1_outputs),
                 gn.Map(name=self.name()+"_map", inputs=buffer_outputs, outputs=outputs, func=self.func)]

        return nodes
