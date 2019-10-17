from ami.flowchart.library.DisplayWidgets import AreaDetWidget, WaveformWidget, PixelDetWidget
from ami.flowchart.library.common import CtrlNode, MAX
from amitypes import Array2d, Array1d
import pyqtgraph as pg
import ami.graph_nodes as gn
import asyncio


class Roi2D(CtrlNode):

    """
    Region of Interest of image.
    """

    nodeName = "Roi2D"
    uiTemplate = [('origin x',  'intSpin', {'value': 0, 'min': 0, 'max': MAX}),
                  ('extent x',  'intSpin', {'value': 10, 'min': 1, 'max': MAX}),
                  ('origin y',  'intSpin', {'value': 0, 'min': 0, 'max': MAX}),
                  ('extent y',  'intSpin', {'value': 10, 'min': 1, 'max': MAX})]

    def __init__(self, name):
        super(Roi2D, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'ttype': Array2d},
                                               'Out': {'io': 'out', 'ttype': Array2d}},
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
        self.sigStateChanged.emit(self)

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
    Region of Interest of 1d array.
    """

    nodeName = "Roi1D"
    uiTemplate = [('origin',  'intSpin', {'value': 0, 'min': 0, 'max': MAX}),
                  ('extent',  'intSpin', {'value': 10, 'min': 1, 'max': MAX})]

    def __init__(self, name):
        super(Roi1D, self).__init__(name, terminals={"In": {"io": "in", "ttype": Array1d},
                                                     "Out": {"io": "out", "ttype": Array1d}},
                                    viewable=True)
        self.func = lambda img: img

    def display(self, topics, addr, win, **kwargs):
        if self.widget is None:
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
        self.sigStateChanged.emit(self)

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
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=self.func)
        return node


class Roi0D(CtrlNode):

    """
    Selects single pixel from image.
    """

    nodeName = "Roi0D"
    uiTemplate = [('x', 'intSpin', {'value': 0, 'min': 0, 'max': MAX}),
                  ('y', 'intSpin', {'value': 0, 'min': 0, 'max': MAX})]

    def __init__(self, name):
        super(Roi0D, self).__init__(name,
                                    terminals={'In': {'io': 'in', 'ttype': Array2d},
                                               'Out': {'io': 'out', 'ttype': float}},
                                    viewable=True)
        self.func = lambda img: img[0, 0]

    def display(self, topics, addr, win, **kwargs):
        if self.widget is None:
            self.widget = PixelDetWidget(topics, addr, win)
            self.widget.sigClicked.connect(self.set_values)
        if self.task is None:
            self.task = asyncio.ensure_future(self.widget.update())

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        self.x, self.y = args
        self.ctrls['x'].setValue(self.x)
        self.ctrls['y'].setValue(self.y)
        self.set_func()
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        self.x = self.ctrls['x'].value()
        self.y = self.ctrls['y'].value()
        self.set_func()
        if self.widget:
            self.widget.update_cursor(self.x, self.y)

    def set_func(self):
        x = self.x
        y = self.y

        def func(img):
            return img[x, y]

        self.func = func

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=self.func)
        return node
