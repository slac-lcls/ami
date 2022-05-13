
from ami.flowchart.library.DisplayWidgets import ImageWidget, WaveformWidget, PixelDetWidget,\
    ScatterWidget
from ami.flowchart.library.common import CtrlNode
from amitypes import Array2d, Array1d
import ami.graph_nodes as gn
import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn
import logging
logger = logging.getLogger(__name__)

from psana.pyalgos.generic.HPolar import HPolar, info_ndarr
import ami.flowchart.library.UtilsROI as ur
QPen, QBrush, QColor = ur.QPen, ur.QBrush, ur.QColor


class Storage:
    def __init__(self):
        self.hpolar = None
STORE = Storage()


def polar_histogram(shape, mask, cx, cy, ro, ri, ao, ai, nr, na):
    """Returns hp.HPolar object.
    """
    rows, cols = shape
    xarr1 = np.arange(cols) - cx
    yarr1 = np.arange(rows) - cy
    xarr, yarr = np.meshgrid(xarr1, yarr1)
    hpolar = HPolar(xarr, yarr, mask=mask, radedges=(ri,ro), nradbins=nr, phiedges=(ao,ai), nphibins=na)
    logger.debug('%s %s\n%s' %(info_ndarr(xarr,'pixel coordinate arrays: xarr'),\
                              info_ndarr(yarr,' yarr'),\
                              hpolar.info_attrs()))
    return hpolar


class RoiArch(CtrlNode):
    """
    Region of Interest of image shaped as arch (a.k.a. cut-donat).
    """
    nodeName = "RoiArch"
    uiTemplate = [('center x', 'intSpin', {'value':200, 'min': -1000}),
                  ('center y', 'intSpin', {'value':200, 'min': -1000}),
                  ('radius o', 'intSpin', {'value':200, 'min': 1}),
                  ('radius i', 'intSpin', {'value':100, 'min': 1}),
                  ('angdeg o', 'intSpin', {'value':  0, 'min': 0, 'max': 360}),
                  ('angdeg i', 'intSpin', {'value': 60, 'min': 0, 'max': 360}),
                  ('nbins rad','intSpin', {'value':100, 'min': 1}),
                  ('nbins ang','intSpin', {'value':  5, 'min': 1})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': Array2d},
                                    #'Out.Angular': {'io': 'out', 'ttype': Array1d},
                                    #'Out.Radial': {'io': 'out', 'ttype': Array1d},
                                    'Out.RadAng': {'io': 'out', 'ttype': Array2d},
                                    'Roi_Coordinates': {'io': 'out', 'ttype': Array1d}},
                         global_op=True,
                         viewable=True)


    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl


    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, ImageWidget, **kwargs)

        if self.widget:
            cx, cy, ro, ri, ao, ai = self.shape_values()
            width = 4
            kwargs = {'handlePen':QPen(QBrush(QColor('yellow')), width),\
                 'handleHoverPen':QPen(QBrush(QColor('blue')),  width)}
            self.roi = ur.ArchROI(center=(cx, cy), radius_out=ro, radius_int=ri,\
                                  angle_deg_out=ao, angle_deg_int=ai, hlwidth=None, **kwargs)
            self.roi.sigRegionChangeFinished.connect(self.set_values)
            self.widget.view.addItem(self.roi)
            nw = self.widget.parent()
            if nw: nw.setGeometry(500, 10, 900, 600)
        return self.widget


    def shape_values(self):
        return [self.values[s] for s in\
               ('center x', 'center y', 'radius o', 'radius i', 'angdeg o', 'angdeg i')]


    def ctrls_values(self):
        return [self.ctrls[s].value() for s in\
               ('center x', 'center y', 'radius o', 'radius i', 'angdeg o', 'angdeg i', 'nbins rad', 'nbins ang')]


    def set_values(self, *args, **kwargs):
        """set self.values/ctrls parameters from roi shape.
        """
        self.stateGroup.blockSignals(True)
        pos, size, center, rad1, rad2, ang1_deg, ang2_deg, ang1, ang2, p0, p1, p2, p3 = self.roi.shape_parameters()
        self.values['center x'] = round(center.x(),1)
        self.values['center y'] = round(center.y(),1)
        self.values['radius o'] = round(rad1,1)
        self.values['radius i'] = round(rad2,1)
        self.values['angdeg o'] = round(ang1_deg,1)
        self.values['angdeg i'] = round(ang2_deg,1)
        self.ctrls['center x'].setValue(self.values['center x'])
        self.ctrls['center y'].setValue(self.values['center y'])
        self.ctrls['radius o'].setValue(self.values['radius o'])
        self.ctrls['radius i'].setValue(self.values['radius i'])
        self.ctrls['angdeg o'].setValue(self.values['angdeg o'])
        self.ctrls['angdeg i'].setValue(self.values['angdeg i'])

        self.stateGroup.blockSignals(False)
        self.sigStateChanged.emit(self)


    def update(self, *args, **kwargs):
        """set roi shape from self.values.
        """
        super().update(*args, **kwargs)

        if self.widget:
            cx, cy, ro, ri, ao, ai, nr, na = self.ctrls_values()
            self.roi.set_shape_parameters(cx, cy, ro, ri, ao, ai)


    def to_operation(self, **kwargs): #inputs, outputs

        # self.input_vars() #  {'In': 'tmo_opal1:raw:image'}
        # self.name() # RoiArch.0
        # kwargs # {'parent': 'RoiArch.0'}
        # inputs # {'In': 'tmo_opal1:raw:image'}
        # outputs # ['RoiArch.0.Out.Angular', 'RoiArch.0.Out.Radial', 'RoiArch.0.Out.RadAng', 'RoiArch.0.Roi_Coordinates']

        cx, cy, ro, ri, ao, ai, nr, na = self.ctrls_values()
        logger.info('XXX cx:%.1f, cy:%.1f, ro:%d, ri:%d, ao:%.1f, ai:%.1f, nr:%d, na:%d'%\
                    (cx, cy, ro, ri, ao, ai, nr, na))

        def func(img, mask=None):
            logger.debug('img.shape: %s' % str(img.shape))
            #if STORE.hpolar is None: IT DOES NOT WORK bcause of func is caching????
            #   STORE.hpolar = hpolar
            hpolar = polar_histogram(img.shape, mask, cx, cy, ro, ri, ao, ai, nr, na)
            logger.info(hpolar.info_attrs())
            return hpolar.bin_avrg_rad_phi(img, do_transp=True), (ri, ro-ri, ao, ai-ao)

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)


class Roi2D(CtrlNode):

    """
    Region of Interest of image.
    """

    nodeName = "Roi2D"
    uiTemplate = [('origin x', 'intSpin', {'value': 0, 'min': 0}),
                  ('origin y', 'intSpin', {'value': 0, 'min': 0}),
                  ('extent x', 'intSpin', {'value': 10, 'min': 1}),
                  ('extent y', 'intSpin', {'value': 10, 'min': 1})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'In': {'io': 'in', 'ttype': Array2d},
                                    'Out': {'io': 'out', 'ttype': Array2d},
                                    'Roi_Coordinates': {'io': 'out', 'ttype': Array1d}},
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

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

    def to_operation(self, **kwargs):
        ox = self.values['origin x']
        ex = self.values['extent x']
        oy = self.values['origin y']
        ey = self.values['extent y']

        def func(img):
            return img[slice(ox, ox+ex), slice(oy, oy+ey)], (ox, ex, oy, ey)

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)


class Roi1D(CtrlNode):

    """
    Region of Interest of 1d array.
    """

    nodeName = "Roi1D"
    uiTemplate = [('origin', 'intSpin', {'value': 0, 'min': 0}),
                  ('extent', 'intSpin', {'value': 10, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {"io": "in", "ttype": Array1d},
                                          "Out": {"io": "out", "ttype": Array1d}},
                         viewable=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, WaveformWidget, **kwargs)

        if self.widget:
            self.roi = pg.LinearRegionItem((self.values['origin'], self.values['extent']),
                                           brush=fn.mkBrush(0, 255, 0, 100), swapMode='None')
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

    def to_operation(self, **kwargs):
        origin = self.values['origin']
        extent = self.values['extent']
        size = list(sorted([origin, extent]))

        def func(arr):
            return arr[slice(*size)]

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)


class ScatterRoi(CtrlNode):
    """
    Region of Interest of 1d array.
    """

    nodeName = "ScatterRoi"
    uiTemplate = [('origin', 'intSpin', {'value': 0, 'min': 0}),
                  ('extent', 'intSpin', {'value': 10, 'min': 1}),
                  ('Num Points', 'intSpin', {'value': 100, 'min': 1})]

    def __init__(self, name):
        super().__init__(name, terminals={"X": {"io": "in", "ttype": float},
                                          "Y": {"io": "in", "ttype": float},
                                          "Out.X": {"io": "out", "ttype": Array1d},
                                          "Out.Y": {"io": "out", "ttype": Array1d}},
                         buffered=True,
                         global_op=True)

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

    def display(self, topics, terms, addr, win, **kwargs):
        super().display(topics, terms, addr, win, ScatterWidget, **kwargs)

        if self.widget:
            self.roi = pg.LinearRegionItem((self.values['origin'], self.values['extent']), swapMode='sort',
                                           brush=fn.mkBrush(0, 255, 0, 100))
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

    def to_operation(self, inputs, outputs, **kwargs):
        pickn_outputs = [self.name()+"_picked"]
        display_outputs = [self.name()+"_displayX", self.name()+"_displayY"]

        def display_func(arr):
            x, y = zip(*arr)
            return np.array(x), np.array(y)

        origin = self.values['origin']
        extent = self.values['extent']

        def func(arr):
            arr = np.array(arr)

            roi = arr[(origin < arr[:, 0]) & (arr[:, 0] < extent)]
            if roi.size > 0:
                return roi[:, 0], roi[:, 1]
            else:
                return np.array([]), np.array([])

        nodes = [gn.PickN(name=self.name()+"_pickN",
                          inputs=inputs, outputs=pickn_outputs, **kwargs,
                          N=self.values['Num Points']),
                 gn.Map(name=self.name()+"_operation", inputs=pickn_outputs, outputs=outputs, func=func,
                        **kwargs),
                 gn.Map(name=self.name()+"_display", inputs=pickn_outputs, outputs=display_outputs,
                        **kwargs, func=display_func)]

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

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

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

    def to_operation(self, **kwargs):
        x = self.values['x']
        y = self.values['y']

        def func(img):
            return img[x, y]

        return gn.Map(name=self.name()+"_operation", **kwargs, func=func)

# EOF
