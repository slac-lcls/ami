from pyqtgraph.Qt import QtGui, QtWidgets
from amitypes import DataSource, Detector, Array1d, Array2d, Array3d
from ami.flowchart.Node import Node, NodeGraphicsItem
from ami.flowchart.Units import ureg
from ami.flowchart.library.common import CtrlNode
from ami.flowchart.library.Editors import ChannelEditor
import ami.graph_nodes as gn
import numpy as np
import typing


try:
    import constFracDiscrim as cfd

    class CFD(CtrlNode):

        """
        Constant fraction descriminator
        """

        nodeName = "CFD"
        uiTemplate = [('Sample Interval', 'doubleSpin', {'value': 1, 'min': 0.01}),
                      ('horpos', 'doubleSpin', {'value': 0, 'min': 0}),
                      ('gain', 'doubleSpin', {'value': 1, 'min': 0.01}),
                      ('offset', 'doubleSpin', {'value': 0, 'min': 0}),
                      ('delay', 'intSpin', {'value': 1, 'min': 0}),
                      ('walk', 'doubleSpin', {'value': 0, 'min': 0}),
                      ('threshold', 'doubleSpin', {'value': 0, 'min': 0}),
                      ('fraction', 'doubleSpin', {'value': 0.5, 'min': 0})]

        def __init__(self, name):
            super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                              'Out': {'io': 'out', 'ttype': float}})

        def to_operation(self, **kwargs):
            sampleInterval = self.values['Sample Interval']
            horpos = self.values['horpos']
            gain = self.values['gain']
            offset = self.values['offset']
            delay = self.values['delay']
            walk = self.values['walk']
            threshold = self.values['threshold']
            fraction = self.values['fraction']

            def cfd_func(waveform):
                return cfd.cfd(sampleInterval, horpos, gain, offset, waveform, delay, walk, threshold, fraction)

            return gn.Map(name=self.name()+"_operation", **kwargs, func=cfd_func)

except ImportError as e:
    print(e)

try:
    import psana.hexanode.WFPeaks as psWFPeaks

    class WFPeaks(CtrlNode):

        """
        WFPeaks
        """

        nodeName = "WFPeaks"

        def __init__(self, name):
            super().__init__(name, terminals={'Times': {'io': 'in', 'ttype': Array2d},
                                              'Waveform': {'io': 'in', 'ttype': Array2d},
                                              'Num of Hits': {'io': 'out', 'ttype': Array1d},
                                              'Index': {'io': 'out', 'ttype': Array2d},
                                              'Values': {'io': 'out', 'ttype': Array2d},
                                              'Peak Times': {'io': 'out', 'ttype': Array2d}})
            self.values = {}

        def display(self, topics, terms, addr, win, **kwargs):
            if self.widget is None:
                self.widget = ChannelEditor(parent=win)
                self.values = self.widget.values
                self.widget.sigStateChanged.connect(self.state_changed)

            return self.widget

        def to_operation(self, **kwargs):
            numchs = len(self.widget.channel_groups)
            cfdpars = {'numchs': numchs,
                       'numhits': self.values['num hits'],
                       'DLD': self.values['DLD'],
                       'version': 4,
                       'cfd_wfbinbeg': self.values['cfd_wfbinbeg'],
                       'cfd_wfbinend': self.values['cfd_wfbinend']}

            paramsCFD = {}
            for chn in range(0, numchs):
                paramsCFD[chn] = self.values[f"Channel {chn}"]

            cfdpars['paramsCFD'] = paramsCFD
            wfpeaks = psWFPeaks.WFPeaks(**cfdpars)

            def peakFinder(wts, wfs):
                peaks = wfpeaks(wfs, wts)
                return peaks

            return gn.Map(name=self.name()+"_operation", **kwargs, func=peakFinder)

    import psana.hexanode.DLDProcessor as psfDLD

    class DLDProc():

        def __init__(self, **params):
            self.params = params
            self.proc = None

        def __call__(self, nev, nhits, pktsec, calib):
            if self.params['consts'] != calib:
                self.params['consts'] = calib
                self.proc = psfDLD.DLDProcessor(**self.params)

            r = self.proc.xyrt_list(nev, nhits, pktsec)
            if r:
                x, y, r, t = zip(*r)
                return (np.array(x), np.array(y), np.array(r), np.array(t))
            else:
                return (np.array([]), np.array([]), np.array([]), np.array([]))

    class Hexanode(CtrlNode):

        """
        Hexanode
        """

        nodeName = "Hexanode"
        uiTemplate = [('num chans', 'combo', {'values': ["5", "7"]}),
                      ('num hits', 'intSpin', {'value': 16, 'min': 1}),
                      ('verbose', 'check', {'checked': False})]

        def __init__(self, name):
            super().__init__(name, terminals={'Event Number': {'io': 'in', 'ttype': float},
                                              'Num of Hits': {'io': 'in', 'ttype': Array1d},
                                              'Peak Times': {'io': 'in', 'ttype': Array2d},
                                              'Calib': {'io': 'in', 'ttype': typing.Dict},
                                              'X': {'io': 'out', 'ttype': Array1d},
                                              'Y': {'io': 'out', 'ttype': Array1d},
                                              'R': {'io': 'out', 'ttype': Array1d},
                                              'T': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, **kwargs):
            dldpars = {'numchs': int(self.values['num chans']),
                       'numhits': self.values['num hits'],
                       'verbose': self.values['verbose'],
                       'consts': None}

            return gn.Map(name=self.name()+"_operation", **kwargs, func=DLDProc(**dldpars))

    import psana.hexanode.HitFinder as psfHitFinder

    class HitFinder(CtrlNode):

        """
        HitFinder
        """

        nodeName = "HitFinder"
        uiTemplate = [('runtime_u', 'doubleSpin'),
                      ('runtime_v', 'doubleSpin'),
                      ('tsum_avg_u', 'doubleSpin'),
                      ('tsum_hw_u', 'doubleSpin'),
                      ('tsum_avg_v', 'doubleSpin'),
                      ('tsum_hw_v', 'doubleSpin'),
                      ('f_u', 'doubleSpin'),
                      ('f_v', 'doubleSpin'),
                      ('Rmax', 'doubleSpin')]

        def __init__(self, name):
            super().__init__(name, terminals={'Num of Hits': {'io': 'in', 'ttype': Array1d},
                                              'Peak Times': {'io': 'in', 'ttype': Array2d},
                                              'X': {'io': 'out', 'ttype': Array1d},
                                              'Y': {'io': 'out', 'ttype': Array1d},
                                              'T': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, **kwargs):
            HF = psfHitFinder.HitFinder(self.values)

            def func(nhits, pktsec):
                HF.FindHits(pktsec[4, :nhits[4]],
                            pktsec[0, :nhits[0]],
                            pktsec[1, :nhits[1]],
                            pktsec[2, :nhits[2]],
                            pktsec[3, :nhits[3]])
                return HF.GetXYT()

            return gn.Map(name=self.name()+"_operation", **kwargs, func=func)

except ImportError as e:
    print(e)

try:
    import psana.xtcav.LasingOnCharacterization as psLOC

    class LOCProc():

        def __init__(self, **params):
            self.params = params
            self.proc = None
            self.dets = None
            self.src_key = 0

        def __call__(self, src, cam, pars):
            time = None
            power = None
            agreement = None
            pulse = None

            if self.proc is None or self.src_key != src.key:
                if src.cfg['type'] == 'psana':
                    self.src_key = src.key
                    self.dets = psLOC.setDetectors(src.run, camera=cam.det, xtcavpars=pars.det)
                    self.proc = psLOC.LasingOnCharacterization(self.params, src.run, self.dets)
                else:
                    raise NotImplementedError("XTCAVLasingOn does not support the %s source type!" % src.cfg['type'])

            if self.proc.processEvent(src.evt):
                time, power, agreement, pulse = self.proc.resultsProcessImage()

            return time, power, agreement, pulse

    class XTCAVLasingOn(CtrlNode):

        """
        XTCAVLasingOn
        """

        nodeName = "XTCAVLasingOn"
        uiTemplate = [('num bunches', 'intSpin', {'value': 1, 'min': 1}),
                      ('snr filter', 'doubleSpin', {'value': 10.0, 'min': 0}),
                      ('roi expand', 'doubleSpin', {'value': 1.0}),
                      ('roi fraction', 'doubleSpin', {'value': 0.001, 'min': 0, 'max': 1}),
                      ('island split method',  'combo', {'values': ["scipyLabel", "contourLabel"]}),
                      ('island split par1', 'doubleSpin', {'value': 3.0}),
                      ('island split par2', 'doubleSpin', {'value': 5.0})]

        def __init__(self, name):
            super().__init__(name, terminals={'src': {'io': 'in', 'ttype': DataSource},
                                              'cam': {'io': 'in', 'ttype': Detector},
                                              'pars': {'io': 'in', 'ttype': Detector},
                                              'time': {'io': 'out', 'ttype': Array2d, 'unit': ureg.femtosecond},
                                              'power': {'io': 'out', 'ttype': Array2d, 'unit': ureg.gigawatt},
                                              'agreement': {'io': 'out', 'ttype': float},
                                              'pulse': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, **kwargs):
            locpars = {'num_bunches': self.values['num bunches'],
                       'snr_filter': self.values['snr filter'],
                       'roi_expand': self.values['roi expand'],
                       'roi_fraction': self.values['roi fraction'],
                       'island_split_method': self.values['island split method'],
                       'island_split_par1': self.values['island split par1'],
                       'island_split_par2': self.values['island split par2']}

            return gn.Map(name=self.name()+"_operation", **kwargs, func=LOCProc(**locpars))

except ImportError as e:
    print(e)

try:
    from numba import jit

    class PeakFinder1D(CtrlNode):

        """
        1D Peakfinder
        """

        nodeName = "PeakFinder1D"
        uiTemplate = [('threshold lo', 'doubleSpin', {'value': 0}),
                      ('threshold hi', 'doubleSpin', {'value': 1})]

        def __init__(self, name):
            super().__init__(name, terminals={"Waveform": {'io': 'in', 'ttype': Array1d},
                                              "Centroid": {'io': 'out', 'ttype': Array1d},
                                              "Width": {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, **kwargs):
            threshold_lo = self.values['threshold lo']
            threshold_hi = self.values['threshold hi']

            @jit(nopython=True)
            def peakfinder1d(waveform):
                centroids = []
                widths = []

                for i in range(1, waveform.shape[0]-1):
                    if waveform[i] < threshold_hi:
                        continue

                    weighted_sum = 0
                    weights = 0

                    left = i - 1
                    right = i + 1

                    peak = waveform[i]

                    left_found = False
                    while threshold_lo < waveform[left] <= peak:
                        left_found = True
                        weighted_sum += waveform[left]*left
                        weights += waveform[left]
                        left -= 1
                        if left < 0:
                            break

                    right_found = False
                    while threshold_lo < waveform[right] <= peak:
                        right_found = True
                        weighted_sum += waveform[right]*right
                        weights += waveform[right]
                        right += 1
                        if right > waveform.shape[0] - 1:
                            break

                    if left_found and right_found:
                        weighted_sum += peak*i
                        weights += peak
                        centroids.append(weighted_sum/weights)
                        widths.append(right-left-1)

                return np.array(centroids), np.array(widths)

            return gn.Map(name=self.name()+"_operation", **kwargs, func=peakfinder1d)

except ImportError as e:
    print(e)

try:
    from psalg_ext import peak_finder_algos

    peak_attrs = ['seg', 'row', 'col', 'npix', 'amp_max', 'amp_tot',
                  'row_cgrav', 'col_cgrav', 'row_sigma', 'col_sigma',
                  'row_min', 'row_max', 'col_min', 'col_max',
                  'bkgd', 'noise', 'son']

    class PeakFinderGraphicsItem(NodeGraphicsItem):

        def buildMenu(self, reset=False):
            super().buildMenu(reset)
            actions = self.menu.actions()
            addInput = actions[2]

            self.output_group = QtWidgets.QActionGroup(self.menu)

            for attr in peak_attrs:
                if attr not in self.node.terminals:
                    add_attr = QtGui.QAction(f"Add {attr}", self.menu)
                    add_attr.attr = attr
                    self.output_group.addAction(add_attr)
                    self.menu.insertAction(addInput, add_attr)

            self.output_group.triggered.connect(self.output_added)

        def output_added(self, action):
            self.node.addTerminal(action.attr, io='out', ttype=Array1d, removable=True)
            self.buildMenu(reset=True)

    class PeakfinderAlgos():

        def __init__(self, constructor_params={}, call_params={}, outputs=[]):
            self.constructor_params = constructor_params
            self.call_params = call_params
            self.outputs = outputs
            self.proc = None

        def __call__(self, img):
            if self.proc is None:
                self.proc = peak_finder_algos(pbits=0)
                self.proc.set_peak_selection_parameters(**self.constructor_params)

            mask = np.ones(img.shape, dtype=np.uint16)
            peaks = self.proc.peak_finder_v4r3_d2(img, mask, **self.call_params)

            outputs = []
            for output in self.outputs:
                outputs.append(np.array(list(map(lambda peak: getattr(peak, output), peaks))))

            return outputs

    class PeakFinderV4R3(CtrlNode):

        """
        psana peakfinder v4r3d2
        """

        nodeName = "PeakFinderV4R3"
        uiTemplate = [('npix min', 'doubleSpin', {'value': 20}),
                      ('npix max', 'doubleSpin', {'value': 25}),
                      ('amax thr', 'doubleSpin', {'value': 0}),
                      ('atot thr', 'doubleSpin', {'value': 0}),
                      ('son min', 'doubleSpin', {'value': 0}),
                      # pass to peak_finder_v4r3_d2
                      ('thr low', 'doubleSpin', {'value': 35}),
                      ('thr high', 'doubleSpin', {'value': 100}),
                      ('rank', 'doubleSpin', {'value': 2}),
                      ('r0', 'doubleSpin', {'value': 4}),
                      ('dr', 'doubleSpin', {'value': 0.05})]

        def __init__(self, name):
            super().__init__(name, terminals={'Image': {'io': 'in', 'ttype': Array2d},
                                              'row_cgrav': {'io': 'out', 'ttype': Array1d, 'removable': True},
                                              'col_cgrav': {'io': 'out', 'ttype': Array1d, 'removable': True},
                                              'npix': {'io': 'out', 'ttype': Array1d, 'removable': True},
                                              'son': {'io': 'out', 'ttype': Array1d, 'removable': True},
                                              'amp_tot': {'io': 'out', 'ttype': Array1d, 'removable': True}})
            self.graphicsItem().buildMenu(reset=True)

        def graphicsItem(self, brush=None):
            if self._graphicsItem is None:
                self._graphicsItem = PeakFinderGraphicsItem(self, brush)
            return self._graphicsItem

        def to_operation(self, **kwargs):
            constructor_params = {'npix_min': self.values['npix min'],
                                  'npix_max': self.values['npix max'],
                                  'amax_thr': self.values['amax thr'],
                                  'atot_thr': self.values['atot thr'],
                                  'son_min': self.values['son min']}

            call_params = {'thr_low': self.values['thr low'],
                           'thr_high': self.values['thr high'],
                           'rank': self.values['rank'],
                           'r0': self.values['r0'],
                           'dr': self.values['dr']}

            node = gn.Map(name=self.name()+"_operation", **kwargs,
                          func=PeakfinderAlgos(constructor_params, call_params, list(self.outputs().keys())))

            return node

except ImportError as e:
    print(e)


try:
    from psana.pyalgos.generic import edgefinder

    class EdgeFinderProc():

        def __init__(self, calibconsts={}):
            self.calibconsts = calibconsts
            self.proc = None

        def __call__(self, image, iir, calib):

            if self.calibconsts.keys() != calib.keys():
                self.calibconsts = calib
                self.proc = edgefinder.EdgeFinder(self.calibconsts)
            elif all(np.array_equal(self.calibconsts[key], calib[key]) for key in calib):
                self.calibconsts = calib
                self.proc = edgefinder.EdgeFinder(self.calibconsts)

            r = self.proc(image, iir)
            if r:
                return r.edge, r.fwhm, r.amplitude, r.amplitude_next, r.ref_amplitude
            return np.nan, np.nan, np.nan, np.nan, np.nan

    class EdgeFinder(Node):

        """
        psana edgefinder
        """

        nodeName = "EdgeFinder"

        def __init__(self, name):
            super().__init__(name, terminals={'Image': {'io': 'in', 'ttype': Array1d},
                                              'IIR': {'io': 'in', 'ttype': Array1d},
                                              'Calib': {'io': 'in', 'ttype': typing.Dict},
                                              'edge': {'io': 'out', 'ttype': float},
                                              'fwhm': {'io': 'out', 'ttype': float},
                                              'amplitude': {'io': 'out', 'ttype': float},
                                              'amplitude_next': {'io': 'out', 'ttype': float},
                                              'ref_amplitude': {'io': 'out', 'ttype': float}})

        def to_operation(self, **kwargs):
            return gn.Map(name=self.name()+"_operation", **kwargs, func=EdgeFinderProc({}))

except ImportError as e:
    print(e)


try:
    import logging
    logger = logging.getLogger(__name__)
    from psana.detector.mask_algos import MaskAlgos
    from psana.detector.NDArrUtils import info_ndarr
    from psana.pscalib.calib.NDArrIO import load_txt
    from ami.flowchart.library.DisplayWidgets import ImageWidget

    class MaskProd():

        def __init__(self, **kwa):
            logger.info('MaskProd.__init__ kwa: %s' % str(kwa))
            self.calibconsts = kwa.pop('calibconsts', {})
            self.kwa = kwa
            self.mask = None  # np.nan

        def __call__(self, calib):
            """ is called freq ~1Hz
            """
            logger.debug('MaskProd.__call__ : %s' % self.__call__.__doc__.rstrip())

            if self.calibconsts.keys() != calib.keys():
                self.calibconsts = calib

                logger.info('MaskProd.__call__: calibconsts.keys(): %s' % str(self.calibconsts.keys()))
                data_and_meta = self.calibconsts.get('pixel_status', None)
                self.data, self.meta = (np.nan, None) if data_and_meta is None else data_and_meta
                logger.debug('pixel_status meta: %s' % str(self.meta))
                logger.debug('pixel_status data: %s' % str(self.data))

                o = MaskAlgos(self.calibconsts)
                logger.info('MaskProd.__call__: create mask_comb with pars: %s' % str(self.kwa))
                self.mask = o.mask_comb(**self.kwa)
                logger.debug(info_ndarr(self.mask, 'mask_comb:'))

            return (None, None) if self.mask is None else\
                   (self.mask, None) if self.mask.ndim == 2 else\
                   (None, self.mask) if self.mask.ndim == 3 else\
                   (None, None)

    class Mask(CtrlNode):
        """ psana Mask """
        nodeName = "Mask"

        uiTemplate = [
            ('status', 'check', {'checked': True, 'group': 'Mask from status'}),
            ('status_bits', 'intSpin', {'value': 511, 'group': 'Mask from status'}),
            ('gain_range_inds', 'text', {'value': '0,1,2,3,4', 'group': 'Mask from status'}),
            ('neighbors', 'check', {'checked': False, 'group': 'Mask of neighbors'}),
            ('rad', 'intSpin', {'value': 5, 'min': 1, 'group': 'Mask of neighbors'}),
            ('ptrn', 'combo', {'values': ['r', 'c', 's'], 'group': 'Mask of neighbors'}),
            ('edges', 'check', {'checked': False, 'group': 'Mask of segment edges'}),
            ('width', 'intSpin', {'value': 0, 'min': 0, 'group': 'Mask of segment edges'}),
            ('edge_rows', 'intSpin', {'value': 1, 'min': 0, 'group': 'Mask of segment edges'}),
            ('edge_cols', 'intSpin', {'value': 1, 'min': 0, 'group': 'Mask of segment edges'}),
            ('center', 'check', {'checked': False, 'group': 'Mask of segment central rows/columns'}),
            ('wcenter', 'intSpin', {'value': 0, 'min': 0, 'group': 'Mask of segment central rows/columns'}),
            ('center_rows', 'intSpin', {'value': 1, 'min': 0, 'group': 'Mask of segment central rows/columns'}),
            ('center_cols', 'intSpin', {'value': 1, 'min': 0, 'group': 'Mask of segment central rows/columns'}),
            ('calib', 'check', {'checked': False, 'group': 'Mask from pixel_mask'}),
            ('umask', 'text', {'value': '', 'group': 'Users mask from file'}),
        ]

        def __init__(self, name):
            """class constructor - called at droppong CtrlNode on flowchart'.
            """
            super().__init__(name, terminals={'calibconst': {'io': 'in', 'ttype': typing.Dict},
                                              'Mask': {'io': 'out', 'ttype': Array2d},
                                              'Mask3D': {'io': 'out', 'ttype': Array3d}})
            logger.info('__init__: %s' % self.__init__.__doc__.rstrip()
                        + '\ndict_mask_pars_from_values: %s' % str(self.dict_mask_pars_from_values()))

        def display_v0(self, topics, terms, addr, win, **kwargs):
            """call-back at click on Mask CtrlNode box.
            """
            logger.info('in display')
            super().display(topics, terms, addr, win, ImageWidget, **kwargs)
            logger.debug('in display - %s' % self.display.__doc__.rstrip())
            if self.widget:
                logger.debug('TBD - create new Mask')
            return self.widget

        def dict_mask_pars_from_values(self):
            """self.values {
            'Mask from status': {'status': True, 'status_bits': 511, 'gain_range_inds': '0,1,2,3,4'},
            'Mask of neighbors': {'neighbors': False, 'rad': 5, 'ptrn': None},
            'Mask of segment edges': {'edges': False, 'width': 0, 'edge_rows': 1, 'edge_cols': 1},
            'Mask of segment central rows/columns': {'center': False, 'wcenter': 0, 'center_rows': 1, 'center_cols': 1},
            'Mask from pixel_mask': {'calib': False},
            'Users mask from file': {'umask': ''}}
            """
            d = {}
            for v in self.values.values():
                if not isinstance(v, dict):
                    continue
                d.update(v)

            k = 'gain_range_inds'
            if k in d.keys():
                d[k] = [int(v) for v in d[k].split(',')]

            k = 'umask'
            logger.debug('umask:', d[k])
            if k in d.keys():
                fname = str(d[k])
                ext = fname.split('.')[-1]
                d[k] = np.loadtxt(fname) if fname and ext == 'npy' else\
                    load_txt(fname) if fname and ext in ('data', 'dat', 'text', 'txt') else\
                    None
            return d

        def to_operation(self, **kwargs):
            logger.debug('to_operation - at click on Apply')
            pars = {'calibconsts': {}}
            pars.update(self.dict_mask_pars_from_values())
            return gn.Map(name=self.name()+"_operation", **kwargs, func=MaskProd(**pars))

            """self.ctrls: {
            'Mask from status': {'groupbox': <PyQt5.QtWidgets.QGroupBox object at 0x7fbf594137d0>,
                                 'status': <PyQt5.QtWidgets.QCheckBox object at 0x7fbf59413910>,
                                 'status_bits': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf594139b0>,
                                 'gain_range_inds': <PyQt5.QtWidgets.QLineEdit object at 0x7fbf59413a50>},
            'Mask of neighbors': {'groupbox': <PyQt5.QtWidgets.QGroupBox object at 0x7fbf59413af0>,
                                 'neighbors': <PyQt5.QtWidgets.QCheckBox object at 0x7fbf59413c30>,
                                 'rad': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf59413cd0>,
                                 'ptrn': <PyQt5.QtWidgets.QComboBox object at 0x7fbf59413d70>},
            'Mask of segment edges': {'groupbox': <PyQt5.QtWidgets.QGroupBox object at 0x7fbf59413e10>,
                                 'edges': <PyQt5.QtWidgets.QCheckBox object at 0x7fbf59413f50>,
                                 'width': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf59419050>,
                                 'edge_rows': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf594190f0>,
                                 'edge_cols': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf59419190>},
            'Mask of segment central rows/columns': {'groupbox': <PyQt5.QtWidgets.QGroupBox object at 0x7fbf59419230>,
                                 'center': <PyQt5.QtWidgets.QCheckBox object at 0x7fbf59419370>,
                                 'wcenter': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf59419410>,
                                 'center_rows': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf594194b0>,
                                 'center_cols': <PyQt5.QtWidgets.QSpinBox object at 0x7fbf59419550>},
            'Mask from pixel_mask': {'groupbox': <PyQt5.QtWidgets.QGroupBox object at 0x7fbf594195f0>,
                                 'calib': <PyQt5.QtWidgets.QCheckBox object at 0x7fbf59419730>},
            'Users mask from file': {'groupbox': <PyQt5.QtWidgets.QGroupBox object at 0x7fbf594197d0>,
                                                 'umask': <PyQt5.QtWidgets.QLineEdit object at 0x7fbf59419910>}}
            """

except ImportError as e:
    print(e)
