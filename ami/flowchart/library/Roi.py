from ami.flowchart.library.DisplayWidgets import AreaDetWidget, WaveformWidget, PixelDetWidget, ScatterWidget
from ami.flowchart.library.common import CtrlNode
from amitypes import Array2d, Array1d
import ami.graph_nodes as gn
import pyqtgraph as pg
import numpy as np
import asyncio


class Roi2D(CtrlNode):

    """
    Region of Interest of image.
    """

    nodeName = "Roi2D"
    uiTemplate = [('origin x',  'intSpin', {'value': 0, 'min': 0}),
                  ('extent x',  'intSpin', {'value': 10, 'min': 1}),
                  ('origin y',  'intSpin', {'value': 0, 'min': 0}),
                  ('extent y',  'intSpin', {'value': 10, 'min': 1})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': Array2d},
                                    'Out': {'io': 'out', 'ttype': Array2d}},
                         viewable=True)
        self.func = lambda img: img

    def display(self, topics, terms, addr, win, **kwargs):
        if self.widget is None:
            self.widget = AreaDetWidget(topics, terms, addr, win)
            self.widget.roi.sigRegionChangeFinished.connect(self.set_values)
            self.widget.ui.roiBtn.setChecked(True)
            self.widget.ui.roiBtn.hide()
            self.widget.roiClicked()
        if self.task is None and self.widget and addr:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        roi = args[0]
        extent, _, origin = roi.getAffineSliceParams(self.widget.image, self.widget.getImageItem())
        self.values['origin x'] = int(origin[0])
        self.values['origin y'] = int(origin[1])
        self.values['extent x'] = int(extent[0])
        self.values['extent y'] = int(extent[1])
        self.ctrls['origin x'].setValue(self.values['origin x'])
        self.ctrls['extent x'].setValue(self.values['extent x'])
        self.ctrls['origin y'].setValue(self.values['origin y'])
        self.ctrls['extent y'].setValue(self.values['extent y'])
        self.set_func()
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.set_func()
        if self.widget:
            self.widget.roi.setPos(self.values['origin x'], y=self.values['origin y'], finish=False)
            self.widget.roi.setSize((self.values['extent x'], self.values['extent y']), finish=False)

    def set_func(self):
        origin_x = self.values['origin x']
        origin_y = self.values['origin y']
        extent_x = self.values['extent x']
        extent_y = self.values['extent y']

        def func(img):
            return img[slice(origin_x, extent_x), slice(origin_y, extent_y)]

        self.func = func

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions, inputs=inputs, outputs=outputs,
                      func=self.func,
                      parent=self.name())
        return node


class Roi1D(CtrlNode):

    """
    Region of Interest of 1d array.
    """

    nodeName = "Roi1D"
    uiTemplate = [('origin',  'intSpin', {'value': 0, 'min': 0}),
                  ('extent',  'intSpin', {'value': 10, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {"io": "in", "ttype": Array1d},
                                          "Out": {"io": "out", "ttype": Array1d}},
                         viewable=True)
        self.func = lambda img: img

    def display(self, topics, terms, addr, win, **kwargs):
        if self.widget is None:
            self.widget = WaveformWidget(topics, terms, addr, win, **kwargs)
            self.widget.roi = pg.LinearRegionItem((0, 10))
            self.widget.roi.setBounds((0, None))
            self.widget.plot_view.addItem(self.widget.roi)
            self.widget.roi.sigRegionChangeFinished.connect(self.set_values)
        if self.task is None and self.widget and addr:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        roi = args[0]
        origin, extent = roi.getRegion()
        self.values['origin'] = int(origin)
        self.values['extent'] = int(extent)
        self.ctrls['origin'].setValue(self.values['origin'])
        self.ctrls['extent'].setValue(self.values['extent'])
        self.set_func()
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.set_func()
        if self.widget:
            self.widget.roi.setRegion((self.values['origin'], self.values['extent']))

    def set_func(self):
        origin = self.values['origin']
        extent = self.values['extent']

        def func(arr):
            return arr[slice(origin, extent)]

        self.func = func

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions, inputs=inputs, outputs=outputs,
                      func=self.func,
                      parent=self.name())
        return node


class ScatterRoi(CtrlNode):

    """
    Region of Interest of 1d array.
    """

    nodeName = "ScatterRoi"
    uiTemplate = [('origin',  'intSpin', {'value': 0, 'min': 0}),
                  ('extent',  'intSpin', {'value': 10, 'min': 1}),
                  ('Num Points', 'intSpin', {'value': 100, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"X": {"io": "in", "ttype": float},
                                          "Y": {"io": "in", "ttype": float},
                                          "Out.X": {"io": "out", "ttype": Array1d},
                                          "Out.Y": {"io": "out", "ttype": Array1d}},
                         buffered=True)

        def func(arr):
            x, y = zip(*arr)
            return np.array(x), np.array(y)

        self.func = func

    def display(self, topics, terms, addr, win, **kwargs):
        if self.widget is None:
            self.widget = ScatterWidget(topics, terms, addr, win, **kwargs)
            self.widget.roi = pg.LinearRegionItem((0, 10))
            self.widget.roi.setBounds((0, None))
            self.widget.plot_view.addItem(self.widget.roi)
            self.widget.roi.sigRegionChangeFinished.connect(self.set_values)
        if self.task is None and self.widget and addr:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        roi = args[0]
        origin, extent = roi.getRegion()
        self.values['origin'] = int(origin)
        self.values['extent'] = int(extent)
        self.ctrls['origin'].setValue(self.values['origin'])
        self.ctrls['extent'].setValue(self.values['extent'])
        self.set_func()
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.set_func()
        if self.widget:
            self.widget.roi.setRegion((self.values['origin'], self.values['extent']))

    def set_func(self):
        origin = self.values['origin']
        extent = self.values['extent']

        def func(arr):
            arr = np.array(arr)

            roi = arr[(origin < arr[:, 0]) & (arr[:, 0] < extent)]
            if roi.size > 0:
                return roi[:, 0], roi[:, 1]
            else:
                return np.array([]), np.array([])

        self.func = func

    def buffered_topics(self):
        terms = self.input_vars()
        return {terms["X"]: self.name()+"_displayX", terms["Y"]: self.name()+"_displayY"}

    def buffered_terms(self):
        terms = self.input_vars()
        return {"X": terms["X"], "Y": terms["Y"]}

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        pickn_outputs = [self.name()+"_picked"]
        display_outputs = [self.name()+"_displayX", self.name()+"_displayY"]

        def display_func(arr):
            x, y = zip(*arr)
            return np.array(x), np.array(y)

        nodes = [gn.PickN(name=self.name()+"_pickN", condition_needs=conditions,
                          inputs=inputs, outputs=pickn_outputs, parent=self.name(),
                          N=self.values['Num Points']),
                 gn.Map(name=self.name()+"_operation", inputs=pickn_outputs, outputs=outputs, func=self.func,
                        parent=self.name()),
                 gn.Map(name=self.name()+"_display", inputs=pickn_outputs, outputs=display_outputs,
                        parent=self.name(), func=display_func)]

        return nodes


class Roi0D(CtrlNode):

    """
    Selects single pixel from image.
    """

    nodeName = "Roi0D"
    uiTemplate = [('x', 'intSpin', {'value': 0, 'min': 0}),
                  ('y', 'intSpin', {'value': 0, 'min': 0})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': Array2d},
                                    'Out': {'io': 'out', 'ttype': float}},
                         viewable=True)
        self.func = lambda img: img[0, 0]

    def display(self, topics, terms, addr, win, **kwargs):
        if self.widget is None:
            self.widget = PixelDetWidget(topics, terms, addr, win)
            self.widget.sigClicked.connect(self.set_values)
        if self.task is None and self.widget and addr:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        self.values['x'], self.values['y'] = args
        self.ctrls['x'].setValue(self.x)
        self.ctrls['y'].setValue(self.y)
        self.set_func()
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.set_func()
        if self.widget:
            self.widget.update_cursor(self.x, self.y)

    def set_func(self):
        x = self.valaues['x']
        y = self.values['y']

        def func(img):
            return img[x, y]

        self.func = func

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=conditions, inputs=inputs, outputs=outputs,
                      func=self.func,
                      parent=self.name())
        return node
