from qtpy import QtWidgets
from amitypes import DataSource, Detector, Array1d, Array2d, Array3d
from ami.flowchart.Node import Node, NodeGraphicsItem
from ami.flowchart.Units import ureg
from ami.flowchart.library.common import CtrlNode
from ami.flowchart.library.Editors import ChannelEditor
import ami.graph_nodes as gn
import numpy as np

try:
    import logging
    logger = logging.getLogger(__name__)

except ImportError as e:
    print(e)

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
                                              'Calib': {'io': 'in', 'ttype': dict},
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
                    add_attr = QtWidgets.QAction(f"Add {attr}", self.menu)
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
                                              'Calib': {'io': 'in', 'ttype': dict},
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
    from psana.detector.mask_algos import MaskAlgos
    from psana.detector.NDArrUtils import info_ndarr
    from psana.pscalib.calib.NDArrIO import load_txt

    class MaskProd():

        def __init__(self, **kwa):
            logger.info('MaskProd.__init__ kwa: %s' % str(kwa))
            self.calibconsts = kwa.pop('calibconsts', {})
            self.kwa = kwa
            self.mask = None  # np.nan

        def __call__(self, calib):
            """ call frequency ~1Hz
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
            ('umask', 'file_in', {'value': 'select', 'group': 'Users mask from file'}),
            # ('umask', 'text', {'value': '', 'group': 'Users mask from file'}),
        ]

        def __init__(self, name):
            """class constructor - called at droppong CtrlNode on flowchart'.
            """
            super().__init__(name, terminals={'calibconst': {'io': 'in', 'ttype': dict},
                                              'Mask': {'io': 'out', 'ttype': Array2d},
                                              'Mask3D': {'io': 'out', 'ttype': Array3d}})
            logger.info('__init__: %s' % self.__init__.__doc__.rstrip()
                        + '\ndict_mask_pars_from_values: %s' % str(self.dict_mask_pars_from_values()))

        def umask_from_ctrls(self):
            logger.debug('self.ctrls: %s' % str(self.ctrls))
            w = self.ctrls['Users mask from file'].get('umask', None)  # expected PushButtonSelectFile
            fname = w.fname() if w is not None else ''
            if fname == 'select':
                fname = ''
            return fname

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

#            k = 'umask'
#            if k in d.keys():
#                fname = str(d[k])
#                ext = fname.split('.')[-1]
#                d[k] = np.loadtxt(fname) if fname and ext == 'npy' else\
#                    load_txt(fname) if fname and ext in ('data', 'dat', 'text', 'txt') else\
#                    None

            k = 'umask'
            fname = self.umask_from_ctrls()
            logger.info('umask file name: %s' % str(fname))
            ext = fname.split('.')[-1]

            try:
                d[k] = np.load(fname) if fname and ext == 'npy' else\
                   load_txt(fname) if fname and ext in ('data', 'dat', 'text', 'txt') else\
                   None

            except Exception as e:
                logger.debug('Exception: %s' % str(e))
                logger.warning('can not load umask file: %s' % str(fname))
                d[k] = None

            logger.info(info_ndarr(d[k], k))

            return d

        def to_operation(self, **kwargs):
            logger.debug('to_operation - at click on Apply')
            pars = {'calibconsts': {}}
            pars.update(self.dict_mask_pars_from_values())
            return gn.Map(name=self.name()+"_operation", **kwargs, func=MaskProd(**pars))

except ImportError as e:
    print(e)


try:
    from psana.pscalib.geometry.GeometryAccess import GeometryAccess, img_from_pixel_arrays
    import os

    class GeometryProd():

        def __init__(self, **kwa):
            logger.info('GeometryProd.__init__ kwa: %s' % str(kwa))
            self.calibconsts = kwa.pop('calibconsts', {})
            self.kwa = kwa
            self.geofname = None
            self.resp = (None, None, None)

        def __call__(self, calib, arr3d=None):  # mask2d=None):
            """ called frequency ~1 Hz
            """
            logger.debug('GeometryProd.kwa: %s' % str(self.kwa))

            self.do_load_geo = 0

            geofname = self.kwa.get('geofname', '')
            if geofname and (geofname != self.geofname):
                self.geofname = geofname
                if os.path.exists(geofname):
                    self.do_load_geo = 1
                    logger.info('GeometryProd.__call__ load geometry from file "%s"' % geofname)

            elif self.calibconsts.keys() != calib.keys():
                self.calibconsts = calib
                self.do_load_geo = 2

                logger.info('GeometryProd.__call__: calibconsts.keys(): %s' % str(self.calibconsts.keys()))
                data_and_meta = self.calibconsts.get('geometry', None)
                self.data, self.meta = (None, None) if data_and_meta is None else data_and_meta
                logger.info('geometry meta: %s' % str(self.meta))
                logger.info('geometry data: %s' % str(self.data))
                logger.info('GeometryProd.kwa: %s' % str(self.kwa))

            if self.do_load_geo > 0:  # =0 - do not load, =1 - from file, =2 - from DB
                o = GeometryAccess()
                if self.do_load_geo == 1:
                    o.load_pars_from_file(self.geofname)
                if self.do_load_geo == 2:
                    o.load_pars_from_str(self.data)
                x, y, z = o.get_pixel_coords()
                ix, iy = o.get_pixel_coord_indexes()
                shape3d = o.shape3d()
                # logger.info(info_ndarr(shape3d, 'shape3d:'))
                x.shape = shape3d
                y.shape = shape3d
                z.shape = shape3d
                ix.shape = shape3d
                iy.shape = shape3d

                logger.info('\n  %s\n  %s\n  %s\n  %s' %
                            (info_ndarr(ix, 'ix:'),
                             info_ndarr(iy, 'iy:'),
                             info_ndarr(x,  ' x:'),
                             info_ndarr(y,  ' y:')))

                img = None if arr3d is None else\
                    img_from_pixel_arrays(ix.ravel(), iy.ravel(), W=arr3d.ravel())  # dtype=np.float32, vbase=0

                # mask3d = None
                # if mask2d is not None:
                #    mask3d = convert_mask2d_to_ndarray(mask2d, ix, iy)
                #    if mask3d is not None:
                #        mask3d.shape = shape3d

                # logger.info(info_ndarr(arr3d, 'input arr3d:'))
                # logger.info(info_ndarr(mask2d, 'input mask2d:'))
                # logger.info(info_ndarr(mask3d, 'output mask3d:'))

                self.resp = ([ix, iy], [x, y, z], img)  # mask3d)
                self.do_load_geo = 0

            return self.resp

    class Geometry(CtrlNode):
        """ psana Geometry - uses geometry constants to generate arrays of pixel coordinates etc."""
        nodeName = "Geometry"

        uiTemplate = [
            ('geofname', 'file_in', {'value': 'select'}),
        ]

        def __init__(self, name):
            """constructor - called at droppong CtrlNode on flowchart'.
            """
            super().__init__(name, terminals={'calibcons':  {'io': 'in',  'ttype': dict},
                                              'arr3d':      {'io': 'in',  'ttype': Array3d, 'removable': True},
                                              'inds_xy':    {'io': 'out', 'ttype': list},
                                              'coords_xyz': {'io': 'out', 'ttype': list},
                                              'image':      {'io': 'out', 'ttype': Array2d},
                                              })
# 'mask2d':   {'io': 'in', 'ttype': Array2d, 'removable': True},
# 'mask3d':   {'io': 'out', 'ttype': Array3d}

            logger.info('Geometry.__init__: %s' % self.__init__.__doc__.rstrip())
            _ = self.dict_geometry_pars_from_values()  # just to print content of issue

        def dict_geometry_pars_from_values(self):
            """ due to some iunidentified bug in WidgetGroups self.values are not updated.
                As a way around grub status of the PushButtonSelectFile directly from
                self.ctrls['geofname'] = PushButtonSelectFile
            """
            logger.info('Geometry.dict_geometry_pars_from_values self.values: %s' % str(self.values))

            w = self.ctrls.get('geofname', None)  # PushButtonSelectFile
            fname = w.fname() if w is not None else ''
            if fname == 'select':
                fname = ''
            d = {'geofname': fname}
            # 'fname': self.values['fname'],
            # 'geofname': self.values['geofname'],
            logger.info('Geometry.dict_geometry_pars_from_values returns dict: %s' % str(d))
            return d

        def to_operation(self, **kwargs):
            logger.info('Geometry.to_operation - at click on Apply')
            pars = {'calibconsts': {}}
            pars.update(self.dict_geometry_pars_from_values())
            return gn.Map(name=self.name()+"_operation", **kwargs, func=GeometryProd(**pars))

except ImportError as e:
    print(e)


try:
    from psana.pscalib.geometry.GeometryAccess import convert_mask2d_to_ndarray

    class Mask3dFrom2dProd():

        def __init__(self, **kwa):
            logger.info('Mask3dFrom2dProd.__init__ kwa: %s' % str(kwa))
            self.kwa = kwa

        def __call__(self, inds_xy, mask2d):
            """ called frequency ~1 Hz
            """
            iy, ix = inds_xy

            logger.info('Mask3dFrom2dProd\n  %s\n  %s\n  %s' %
                        (info_ndarr(ix, 'ix:'),
                         info_ndarr(iy, 'iy:'),
                         info_ndarr(mask2d, 'input mask2d:')))

            mask3d = None
            if mask2d is not None:
                mask3d = convert_mask2d_to_ndarray(mask2d, ix, iy)
                if mask3d is not None:
                    mask3d.shape = ix.shape

            logger.info(info_ndarr(mask3d, 'output mask3d:'))

            return mask3d

    class Mask3dFrom2d(CtrlNode):
        """ psana Mask3dFrom2d - converts mask2d (as image) to mask3d array shaped as data"""
        nodeName = "Mask3dFrom2d"

        uiTemplate = [
            # ('geofname', 'file_in', {'value': 'select'}),
        ]

        def __init__(self, name):
            """constructor - called at droppong CtrlNode on flowchart'.
            """
            super().__init__(name, terminals={'inds_xy':  {'io': 'in', 'ttype': list},
                                              'mask2d':   {'io': 'in',  'ttype': Array2d},
                                              'mask3d':   {'io': 'out', 'ttype': Array3d}})

            logger.info('Mask3dFrom2d.__init__: %s' % self.__init__.__doc__.rstrip())

        def to_operation(self, **kwargs):
            logger.info('Mask3dFrom2d.to_operation - at click on Apply')
            pars = {}
            return gn.Map(name=self.name()+"_operation", **kwargs, func=Mask3dFrom2dProd(**pars))

except ImportError as e:
    print(e)


try:
    from ami.pyalgos.NDArrUtils import reshape_to_2d, arr_rot_n90  # info_ndarr
    from ami.pyalgos.PSUtils import table_nxn_epix10ka_from_ndarr, table_nxm_jungfrau_from_ndarr

    class TableFromArr3dProd():

        def __init__(self, **kwa):
            logger.info('TableFromArr3dProd.__init__ kwa: %s' % str(kwa))
            self.kwa = kwa

        def __call__(self, arr3d):
            """ call frequency ~1Hz
            """
            logger.info('TableFromArr3dProd.__call__ : %s' % self.__call__.__doc__.rstrip())
            logger.info(info_ndarr(arr3d, 'input arr3d:'))
            assert isinstance(arr3d, np.ndarray)
            assert len(arr3d.shape) >= 3
            # jungfrau shape (N, 512, 1024)
            # epix10ka/epixhr shape (N, 352, 384)/(N, 288, 384)
            arr2d = table_nxm_jungfrau_from_ndarr(arr3d) if (len(arr3d) % 512*1024) == 0 else\
                table_nxn_epix10ka_from_ndarr(arr3d) if (len(arr3d) % 384) == 0 else\
                reshape_to_2d(np.array(arr3d))
            logger.info(info_ndarr(arr2d, 'output 2-d table:'))
            logger.info('**kwa: %s' % str(self.kwa))
            transpose = self.kwa.get('transpose', False)
            ang_n90 = int(self.kwa.get('rot_n90', 90))
            if transpose:
                arr2d = arr2d.T
            if ang_n90 != 0:
                arr2d = arr_rot_n90(arr2d, rot_ang_n90=ang_n90)
            return arr2d

    class TableFromArr3d(CtrlNode):
        """ psana TableFromArr3d - converts n-d array (n>=3) for detector data to 2-d table of segments."""
        nodeName = "TableFromArr3d"

        uiTemplate = [
            ('transpose', 'check', {'checked': True, }),
            ('rot_n90', 'combo', {'value': '0', 'values': ['0', '90', '180', '270'], }),
        ]

        def __init__(self, name):
            """constructor - called at droppong CtrlNode on flowchart'."""
            super().__init__(name, terminals={'arr3d': {'io': 'in', 'ttype': Array3d},
                                              'arr2d': {'io': 'out', 'ttype': Array2d}})
            logger.info('__init__: %s' % self.__init__.__doc__.rstrip())

        def to_operation(self, **kwargs):
            logger.debug('to_operation - at click on Apply')
            # w = self.ctrls.get('transpose', False)
            # pars = {'transpose': self.ctrls.get('transpose', False),
            #        'rot_n90': self.ctrls.get('rot_n90', '0'),
            #       }
            pars = {} if self.values is None else self.values  # isinstance(self.values, dict)
            return gn.Map(name=self.name()+"_operation", **kwargs, func=TableFromArr3dProd(**pars))

except ImportError as e:
    print(e)

# ===========  TEMPORARY FOR TEST ONLY

try:
    # from psana.pyalgos.generic.NDArrUtils import info_ndarr, reshape_to_2d, arr_rot_n90
    # from psana.pyalgos.generic.PSUtils import table_nxn_epix10ka_from_ndarr, table_nxm_jungfrau_from_ndarr

    class TestQtPickleProd():

        def __init__(self, **kwa):
            logger.info('TestQtPickleProdProd.__init__ kwa: %s' % str(kwa))
            self.kwa = kwa

        def __call__(self, arr3d):
            """ call frequency ~1Hz
            """
            logger.info(info_ndarr(arr3d, 'TestQtPickleProd.__call__ input arr3d:'))
            assert isinstance(arr3d, np.ndarray)
            assert len(arr3d.shape) >= 3
            # jungfrau shape (N, 512, 1024)
            # epix10ka/epixhr shape (N, 352, 384)/(N, 288, 384)
            arr2d = table_nxm_jungfrau_from_ndarr(arr3d) if (len(arr3d) % 512*1024) == 0 else\
                table_nxn_epix10ka_from_ndarr(arr3d) if (len(arr3d) % 384) == 0 else\
                reshape_to_2d(np.array(arr3d))
            logger.info(info_ndarr(arr2d, 'output 2-d table:'))
            logger.info('**kwa: %s' % str(self.kwa))
            transpose = self.kwa.get('transpose', False)
            ang_n90 = int(self.kwa.get('rot_n90', 90))
            if transpose:
                arr2d = arr2d.T
            if ang_n90 != 0:
                arr2d = arr_rot_n90(arr2d, rot_ang_n90=ang_n90)
            return arr2d

    class TestQtPickle(CtrlNode):
        """ psana TestQtPickle - converts n-d array (n>=3) for detector data to 2-d table of segments."""
        nodeName = "TestQtPickle"

        uiTemplate = [
            ('transpose', 'check', {'checked': True}),
            ('rot_n90', 'combo', {'value': '0', 'values': ['0', '90', '180', '270']})
        ]

        def __init__(self, name):
            """constructor - called at droppong CtrlNode on flowchart'."""
            super().__init__(name, terminals={'arr3d': {'io': 'in', 'ttype': Array3d},
                                              'arr2d': {'io': 'out', 'ttype': Array2d}})
            logger.info('__init__: %s' % self.__init__.__doc__.rstrip())

        def to_operation(self, **kwargs):
            logger.debug('to_operation - at click on Apply')
            pars = {} if self.values is None else self.values  # isinstance(self.ctrls, dict)
            return gn.Map(name=self.name()+"_operation", **kwargs, func=TestQtPickleProd(**pars))

except ImportError as e:
    print(e)

# =========

class ThresholdingHitFinder(CtrlNode):

    """
    Apply a threshold to an image and infinitely sum.
    """

    nodeName = "ThresholdingHitFinder"
    uiTemplate = [('Threshold', 'doubleSpin', {'value': 1.0}),
                  # ('N', 'intSpin', {'value': 2, 'min': 2}),
                  # ('infinite', 'check')
                  ]

    def __init__(self, name):
        super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array2d},
                                          'Out': {'io': 'out', 'ttype': Array2d}},
                         global_op=True)

    def to_operation(self, inputs, outputs, **kwargs):
        mapped_outputs = [self.name()+'_threshold']

        threshold = self.values['Threshold']

        def threshold_img(img):
            return np.where(img >= threshold, 1, 0)

        # if self.values['infinite']:
        summed_outputs = [self.name()+"_sum"]

        def reduction(res, *rest):
            res += np.sum(rest, axis=0)
            return res

        nodes = [gn.Map(name=self.name()+"_map",
                        inputs=inputs, outputs=mapped_outputs,
                        func=threshold_img, **kwargs),
                 gn.Accumulator(name=self.name()+"_accumulated",
                                inputs=mapped_outputs, outputs=summed_outputs,
                                reduction=reduction, **kwargs),
                 gn.Map(name=self.name()+"_unzip",
                        inputs=summed_outputs, outputs=outputs,
                        func=lambda s: s, **kwargs)]
        # else:
        #     summed_outputs = [self.name()+"_count", self.name()+"_sum"]

        #     nodes = [gn.Map(name=self.name()+"_map",
        #                     inputs=inputs, outputs=mapped_outputs,
        #                     func=threshold_img, **kwargs),
        #              gn.SumN(name=self.name()+"_accumulated",
        #                      inputs=mapped_outputs, outputs=summed_outputs,
        #                      N=self.values['N'], **kwargs),
        #              gn.Map(name=self.name()+"_unzip",
        #                     inputs=summed_outputs, outputs=outputs,
        #                     func=lambda count, s: s, **kwargs)]

        return nodes
