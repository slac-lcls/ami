from ami.flowchart.library.DisplayWidgets import ImageWidget, WaveformWidget, PixelDetWidget, \
    ScatterWidget, Histogram2DWidget
from ami.flowchart.library.common import CtrlNode
from amitypes import Array2d, Array1d
from pyqtgraph import QtCore
import pyqtgraph as pg
import ami.graph_nodes as gn
import numpy as np


class Roi2D(CtrlNode):

    """
    Region of Interest of image.
    """

    nodeName = "Roi2D"
    uiTemplate = [('origin x',  'intSpin', {'value': 0, 'min': 0}),
                  ('origin y',  'intSpin', {'value': 0, 'min': 0}),
                  ('extent x',  'intSpin', {'value': 10, 'min': 1}),
                  ('extent y',  'intSpin', {'value': 10, 'min': 1})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': Array2d},
                                    'Out': {'io': 'out', 'ttype': Array2d}},
                         viewable=True)

    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, ImageWidget, **kwargs)

        if self.widget:
            self.roi = pg.RectROI([self.values['origin x'], self.values['origin y']],
                                  [self.values['extent x'], self.values['extent y']])
            self.roi.sigRegionChangeFinished.connect(self.set_values)
            self.widget.view.addItem(self.roi)

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        roi = args[0]
        extent, _, origin = roi.getAffineSliceParams(self.widget.imageItem.image, self.widget.imageItem)
        self.values['origin x'] = int(origin[0])
        self.values['origin y'] = int(origin[1])
        self.values['extent x'] = int(extent[0])
        self.values['extent y'] = int(extent[1])
        self.ctrls['origin x'].setValue(self.values['origin x'])
        self.ctrls['extent x'].setValue(self.values['extent x'])
        self.ctrls['origin y'].setValue(self.values['origin y'])
        self.ctrls['extent y'].setValue(self.values['extent y'])
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)

        if self.widget:
            self.roi.setPos(self.values['origin x'], y=self.values['origin y'], finish=False)
            self.roi.setSize((self.values['extent x'], self.values['extent y']), finish=False)

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        ox = self.values['origin x']
        ex = self.values['extent x']
        oy = self.values['origin y']
        ey = self.values['extent y']

        def func(img):
            return img[slice(ox, ox+ex), slice(oy, oy+ey)]

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions, inputs=inputs, outputs=outputs,
                      func=func,
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

    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, WaveformWidget, **kwargs)

        if self.widget:
            self.roi = pg.LinearRegionItem((self.values['origin'], self.values['extent']))
            self.roi.setBounds((0, None))
            self.widget.plot_view.addItem(self.roi)
            self.roi.sigRegionChangeFinished.connect(self.set_values)

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
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)

        if self.widget:
            self.roi.setRegion((self.values['origin'], self.values['extent']))

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        origin = self.values['origin']
        extent = self.values['extent']

        def func(arr):
            return arr[slice(origin, origin+extent)]

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions, inputs=inputs, outputs=outputs,
                      func=func,
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

    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, ScatterWidget, **kwargs)

        if self.widget:
            self.roi = pg.LinearRegionItem((self.values['origin'], self.values['extent']))
            self.roi.setBounds((0, None))
            self.widget.plot_view.addItem(self.roi)
            self.roi.sigRegionChangeFinished.connect(self.set_values)

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
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        if self.widget:
            self.roi.setRegion((self.values['origin'], self.values['extent']))

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

        origin = self.values['origin']
        extent = self.values['extent']

        def func(arr):
            arr = np.array(arr)

            roi = arr[(origin < arr[:, 0]) & (arr[:, 0] < (origin+extent))]
            if roi.size > 0:
                return roi[:, 0], roi[:, 1]
            else:
                return np.array([]), np.array([])

        nodes = [gn.PickN(name=self.name()+"_pickN", condition_needs=conditions,
                          inputs=inputs, outputs=pickn_outputs, parent=self.name(),
                          N=self.values['Num Points']),
                 gn.Map(name=self.name()+"_operation", inputs=pickn_outputs, outputs=outputs, func=func,
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

    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, PixelDetWidget, **kwargs)

        if self.widget:
            self.widget.sigClicked.connect(self.set_values)
            self.widget.update_cursor(**self.values)

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        self.values['x'], self.values['y'] = args
        self.ctrls['x'].setValue(self.values['x'])
        self.ctrls['y'].setValue(self.values['y'])
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        if self.widget:
            self.widget.update_cursor(**self.values)

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        x = self.values['x']
        y = self.values['y']

        def func(img):
            return img[x, y]

        node = gn.Map(name=self.name()+"_operation",
                      conditions_needs=conditions, inputs=inputs, outputs=outputs,
                      func=func,
                      parent=self.name())
        return node


class Histogram2DRoi(CtrlNode):

    """
    Roi of 2d histogram
    """

    nodeName = "Histogram2DRoi"
    uiTemplate = [('origin x',  'intSpin', {'value': 0, 'min': 0}),
                  ('origin y',  'intSpin', {'value': 0, 'min': 0}),
                  ('extent x',  'intSpin', {'value': 10, 'min': 1}),
                  ('extent y',  'intSpin', {'value': 10, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={'XBins': {'io': 'in', 'ttype': Array1d},
                                          'YBins': {'io': 'in', 'ttype': Array1d},
                                          'Counts': {'io': 'in', 'ttype': Array2d},
                                          'XBins.Out': {'io': 'out', 'ttype': Array1d},
                                          'YBins.Out': {'io': 'out', 'ttype': Array1d},
                                          'Counts.Out': {'io': 'out', 'ttype': Array2d}},
                         viewable=True)

    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, Histogram2DWidget, **kwargs)

        if self.widget:
            self.roi = pg.RectROI([self.values['origin x'], self.values['origin y']],
                                  [self.values['extent x'], self.values['extent y']])
            self.roi.sigRegionChangeFinished.connect(self.set_values)
            self.widget.view.addItem(self.roi)

        return self.widget

    def set_values(self, *args, **kwargs):
        # need to block signals to the stateGroup otherwise stateGroup.sigChanged
        # will be emmitted by setValue causing update to be called
        self.stateGroup.blockSignals(True)
        roi = args[0]
        extent, _, origin = roi.getAffineSliceParams(self.widget.imageItem.image, self.widget.imageItem)
        origin = QtCore.QPoint(*origin)*self.widget.transform
        extent = QtCore.QPoint(*extent)
        self.values['origin x'] = origin.x()
        self.values['origin y'] = origin.y()
        self.values['extent x'] = extent.x()
        self.values['extent y'] = extent.y()
        self.ctrls['origin x'].setValue(self.values['origin x'])
        self.ctrls['extent x'].setValue(self.values['extent x'])
        self.ctrls['origin y'].setValue(self.values['origin y'])
        self.ctrls['extent y'].setValue(self.values['extent y'])
        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)

        if self.widget:
            origin = QtCore.QPoint(self.values['origin x'], self.values['origin y'])
            self.roi.setPos(origin.x(), origin.y(), finish=False)
            self.roi.setSize((self.values['extent x'], self.values['extent y']), finish=False)

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()

        ox = self.values['origin x']
        ex = self.values['extent x']
        oy = self.values['origin y']
        ey = self.values['extent y']

        def func(x, y, img):
            xstart = np.digitize(ox, x)
            ystart = np.digitize(oy, y)
            xs = slice(xstart, xstart+ex)
            ys = slice(ystart, ystart+ey)
            return x[xs], y[ys], img[xs, ys]

        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=conditions, inputs=inputs, outputs=outputs,
                      func=func,
                      parent=self.name())
        return node
