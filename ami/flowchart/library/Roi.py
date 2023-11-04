
from ami.flowchart.library.DisplayWidgets import ImageWidget,\
        WaveformWidget, PixelDetWidget, ScatterWidget
from ami.flowchart.library.common import CtrlNode
from amitypes import Array2d, Array1d
from typing import Any
import ami.graph_nodes as gn
import numpy as np
import pyqtgraph as pg
from pyqtgraph import functions as fn

try:
    import logging
    logger = logging.getLogger(__name__)
    import ami.flowchart.library.UtilsROI as ur
    from ami.pyalgos.NDArrUtils import info_ndarr
    QPen, QBrush, QColor = ur.QPen, ur.QBrush, ur.QColor

    class PolarHistogram():

        def __init__(self, *args):
            logger.info('in PolarHistogram.__init__')
            self.args = args
            self.hpolar = None

        def __call__(self, img, mask=None):
            logger.debug('in PolarHistogram.__call__ %s' % info_ndarr(img, 'image'))
            cx, cy, ro, ri, ao, ai, nr, na = self.args
            if self.hpolar is None:
                logger.info('update hpolar with cx:%.1f, cy:%.1f, ro:%d, ri:%d, ao:%.1f, ai:%.1f, nr:%d, na:%d' %
                            (cx, cy, ro, ri, ao, ai, nr, na))
                hp = self.hpolar = ur.polar_histogram(img.shape, mask, cx, cy, ro, ri, ao, ao+ai, nr, na)
                logger.info(info_ndarr(hp.obj_radbins().bincenters(), '\n  rad bin centers')
                          + info_ndarr(hp.obj_phibins().bincenters(), '\n  ang bin centers'))
                            #hp.info_attrs()

            hp = self.hpolar
            orbins = hp.obj_radbins()
            oabins = hp.obj_phibins()
            ra2d = hp.bin_avrg_rad_phi(img, do_transp=True)
            rproj = np.sum(ra2d, axis=1)/oabins.nbins()  # normalized per pixel
            aproj = np.sum(ra2d, axis=0)/orbins.nbins()

            ranpix = hp.bin_number_of_pixels()[:-1]  # remove the last out of ROI bin
            ranpix.shape = (oabins.nbins(), orbins.nbins())
            ranpix = np.transpose(ranpix)

            logger.debug(info_ndarr(ra2d, '\n  ra2d')
                         + info_ndarr(ranpix, '\n  ranpix')
                         + info_ndarr(orbins.bincenters(), '\n  orbins')
                         + info_ndarr(oabins.bincenters(), '\n  oabins')
                         + info_ndarr(rproj, '\n  radial  projection')
                         + info_ndarr(aproj, '\n  angular projection'))

            mask_arc = ur.um.mask_arc(img.shape, cx, cy, ro, ri, ao, ai, dtype=np.uint8)

            return orbins.bincenters(),\
                oabins.bincenters(),\
                orbins.binedges(),\
                oabins.binedges(),\
                ra2d,\
                ranpix,\
                rproj,\
                aproj,\
                (cx, cy, ro, ri, ao, ai, nr, na),\
                (ri, ro-ri, ao, ai-ao),\
                mask_arc

    class RoiArch(CtrlNode):
        """
        Region of Interest of image shaped as arch (a.k.a. cut-donat).
        """
        nodeName = "RoiArch"
        uiTemplate = [('center x',  'intSpin', {'value': 200, 'min': -1000}),
                      ('center y',  'intSpin', {'value': 200, 'min': -1000}),
                      ('radius o',  'intSpin', {'value': 200, 'min': 1}),
                      ('radius i',  'intSpin', {'value': 100, 'min': 1}),
                      ('angdeg o',  'intSpin', {'value':   0, 'min': 0, 'max': 360}),
                      ('angdeg i',  'intSpin', {'value':  60, 'min': 0, 'max': 360}),
                      ('nbins rad', 'intSpin', {'value': 100, 'min': 1}),
                      ('nbins ang', 'intSpin', {'value':   5, 'min': 1})]

        def __init__(self, name):
            super().__init__(name,
                             terminals={'image': {'io': 'in', 'ttype': Array2d},
                                        'mask': {'io': 'in', 'ttype': Array2d, 'removable': True},
                                        # 'mask': {'io': 'in', 'ttype': Array2d, 'optional': True},
                                        'RBinCent': {'io': 'out', 'ttype': Array1d},
                                        'ABinCent': {'io': 'out', 'ttype': Array1d},
                                        'RBinEdges': {'io': 'out', 'ttype': Array1d},
                                        'ABinEdges': {'io': 'out', 'ttype': Array1d},
                                        'RadAngNormIntens': {'io': 'out', 'ttype': Array2d},
                                        'RadAngBinStatist': {'io': 'out', 'ttype': Array2d},
                                        'RProj': {'io': 'out', 'ttype': Array1d},
                                        'AProj': {'io': 'out', 'ttype': Array1d},
                                        'ROIPars': {'io': 'out', 'ttype': Array1d},
                                        'BBox': {'io': 'out', 'ttype': Array1d},
                                        'Mask': {'io': 'out', 'ttype': Array2d}},
                             global_op=True,
                             viewable=True)

        def isChanged(self, restore_ctrl, restore_widget):
            return restore_ctrl

        def set_scene_click_radius(self, r=10):
            scene = self.widget.view.scene()
            logger.info('change scene._clickRadius from %d to %d:' % (scene._clickRadius, r))
            scene.setClickRadius(r)

        def do_something_to_activate_handles(self):
            """NOTHNG WORKS SO FAR - image object is selected along with handle on mouseClick event.
            """
            _ = self.widget.view  # pyqtgraph.graphicsItems.ViewBox.ViewBox.ViewBox object
            # w = view.getViewWidget()  # pyqtgraph.widgets.GraphicsLayoutWidget.GraphicsLayoutWidget
            # vb = view.graphicsItem()  # pyqtgraph.graphicsItems.ViewBox.ViewBox.ViewBox object
            # w.update()
            # print('in set_zoom view:', view)
            # view.setScale(factor)
            # view.update()
            # view.moveBy(100,100)
            # view.setMouseEnabled(False)
            # print(w, 'dir(w):', dir(w))
            # print(vb, 'dir(vb):', dir(vb))
            # i.setZValue(100)

        def display(self, topics, terms, addr, win, **kwargs):
            """call-back at click on RoiArch CtrlNode box. Why does it called twise on a single click?
            """
            super().display(topics, terms, addr, win, ImageWidget, **kwargs)
            logger.info('in display - %s' % self.display.__doc__.rstrip())
            if self.widget:
                self.set_scene_click_radius(r=10)
                logger.info('create new ArchROI')
                cx, cy, ro, ri, ao, ai = self.shape_values()
                width = 4
                kwargs = {'handlePen': QPen(QBrush(QColor('yellow')), width),
                          'handleHoverPen': QPen(QBrush(QColor('blue')), width)}
                self.roi = ur.ArchROI(center=(cx, cy), radius_out=ro, radius_int=ri,
                                      angle_deg_out=ao, angle_deg_int=ai, hlwidth=None, **kwargs)
                self.roi.sigRegionChangeFinished.connect(self.set_values)
                self.widget.view.addItem(self.roi)
                nw = self.widget.parent()
                if nw:
                    nw.setGeometry(500, 10, 900, 600)
                    self.do_something_to_activate_handles()

            return self.widget

        def shape_values(self):
            return [self.values[s] for s in
                    ('center x', 'center y', 'radius o', 'radius i', 'angdeg o', 'angdeg i')]

        def ctrls_values(self):
            return [self.ctrls[s].value() for s in
                    ('center x', 'center y', 'radius o', 'radius i', 'angdeg o', 'angdeg i', 'nbins rad', 'nbins ang')]

        def set_values(self, *args, **kwargs):
            """call-back-1 on mouse release - set self.values/ctrls from roi shape parameters
            """
            logger.debug('in set_values - %s' % self.set_values.__doc__.rstrip())
            self.stateGroup.blockSignals(True)
            pos, size, center, rad1, rad2, ang1_deg, ang2_deg, ang1, ang2, p0, p1, p2, p3 = self.roi.shape_parameters()

            self.values['center x'] = round(center.x(), 1)
            self.values['center y'] = round(center.y(), 1)
            self.values['radius o'] = round(rad1, 1)
            self.values['radius i'] = round(rad2, 1)
            self.values['angdeg o'] = round(ang1_deg, 1)
            self.values['angdeg i'] = round(ang2_deg, 1)
            self.ctrls['center x'].setValue(self.values['center x'])
            self.ctrls['center y'].setValue(self.values['center y'])
            self.ctrls['radius o'].setValue(self.values['radius o'])
            self.ctrls['radius i'].setValue(self.values['radius i'])
            self.ctrls['angdeg o'].setValue(self.values['angdeg o'])
            self.ctrls['angdeg i'].setValue(self.values['angdeg i'])

            self.stateGroup.blockSignals(False)
            self.sigStateChanged.emit(self)

        def update(self, *args, **kwargs):
            """call-back-2 on mouse release - set roi shape from self.ctrls[s].values.
            """
            super().update(*args, **kwargs)
            logger.debug('in update - %s' % self.update.__doc__.rstrip())

            if self.widget:
                cx, cy, ro, ri, ao, ai, nr, na = self.ctrls_values()
                self.roi.set_shape_parameters(cx, cy, ro, ri, ao, ai)

        def to_operation(self, inputs, outputs, **kwargs):
            """call-back on Apply button.
            """
            logger.info('in to_operation - %s' % self.to_operation.__doc__.rstrip())
            cx, cy, ro, ri, ao, ai, nr, na = args = self.ctrls_values()
            logger.info('to_operation cx:%.1f, cy:%.1f, ro:%d, ri:%d, ao:%.1f, ai:%.1f, nr:%d, na:%d' %
                        (cx, cy, ro, ri, ao, ai, nr, na))
            return gn.Map(name=self.name()+"_operation", inputs=inputs, outputs=outputs, func=PolarHistogram(*args), **kwargs)


except ImportError as e:
    print(e)


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
        if self.widget:
            self.rotation = self.widget.rotate
        else:
            self.rotation = 0
        print(self.rotation) # it does not take the starting rotation.. How to fix that?

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
            self.rotation = self.widget.rotate
            print(self.rotation)
            self.roi.setPos(self.values['origin x'], y=self.values['origin y'], finish=False)
            self.roi.setSize((self.values['extent x'], self.values['extent y']), finish=False)

    def to_operation(self, **kwargs):
        ox = self.values['origin x']
        ex = self.values['extent x']
        oy = self.values['origin y']
        ey = self.values['extent y']
        if hasattr(self, 'rotation'):
            rotate = self.rotation
        else:
            rotate = 0
        #breakpoint()

        def func(img):
            #print(rotate)
            return np.rot90(img.T, rotate)[slice(ox, ox+ex), slice(oy, oy+ey)], (ox, ex, oy, ey)

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
