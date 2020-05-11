from pyqtgraph.Qt import QtGui, QtWidgets
from amitypes import DataSource, Detector, Array1d, Array2d
from ami.flowchart.Node import Node, NodeGraphicsItem
from ami.flowchart.library.common import CtrlNode, MAX
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
        uiTemplate = [('Sample Interval', 'doubleSpin', {'value': 1, 'min': 0.01, 'max': MAX}),
                      ('horpos', 'doubleSpin', {'value': 0, 'min': 0, 'max': MAX}),
                      ('gain', 'doubleSpin', {'value': 1, 'min': 0.01, 'max': MAX}),
                      ('offset', 'doubleSpin', {'value': 0, 'min': 0, 'max': MAX}),
                      ('delay', 'intSpin', {'value': 1, 'min': 0, 'max': MAX}),
                      ('walk', 'doubleSpin', {'value': 0, 'min': 0, 'max': MAX}),
                      ('threshold', 'doubleSpin', {'value': 0, 'min': 0, 'max': MAX}),
                      ('fraction', 'doubleSpin', {'value': 0.5, 'min': 0, 'max': MAX})]

        def __init__(self, name):
            super().__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                              'Out': {'io': 'out', 'ttype': float}})

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

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

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=cfd_func,
                          parent=self.name())
            return node

except ImportError as e:
    print(e)

try:
    import psana.hexanode.WFPeaks as psWFPeaks

    def build_layout(channels):
        template = [('num chans', 'combo', {'values': ["5"]}),
                    ('num hits', 'intSpin', {'value': 16, 'min': 1, 'max': MAX})]

        for channel in channels:
            channel_group = [('name', 'text', {'values': f'Channel {channel}', 'group': channel}),
                             ('delay', 'doubleSpin', {'group': channel}),
                             ('fraction', 'doubleSpin', {'group': channel}),
                             ('offset', 'doubleSpin', {'group': channel}),
                             ('polarity', 'combo', {'values': ["Negative"], 'group': channel}),
                             ('sample_interval', 'doubleSpin', {'group': channel}),
                             ('threshold', 'doubleSpin', {'group': channel}),
                             ('timerange_high', 'doubleSpin', {'group': channel}),
                             ('timerange_low', 'doubleSpin', {'group': channel}),
                             ('walk', 'doubleSpin', {'group': channel})]
            template.extend(channel_group)

        return template

    class WFPeaks(CtrlNode):

        """
        WFPeaks
        """

        nodeName = "WFPeaks"
        channels = ['Channel 0', 'Channel 1', 'Channel 2', 'Channel 3', 'Channel 4']
        channel_attrs = ['name', 'delay', 'fraction', 'offset', 'polarity', 'sample_interval',
                         'threshold', 'timerange_high', 'timerange_low', 'walk']
        uiTemplate = build_layout(channels)

        def __init__(self, name):
            super().__init__(name, terminals={'Times': {'io': 'in', 'ttype': Array2d},
                                              'Waveform': {'io': 'in', 'ttype': Array2d},
                                              'Num of Hits': {'io': 'out', 'ttype': Array1d},
                                              'Index': {'io': 'out', 'ttype': Array2d},
                                              'Values': {'io': 'out', 'ttype': Array2d},
                                              'Peak Times': {'io': 'out', 'ttype': Array2d}})

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            cfdpars = {'numchs': int(self.num_chans),
                       'numhits': self.num_hits,
                       'version': 4}

            paramsCFD = {}
            for channel, name in enumerate(WFPeaks.channels):
                name = name.replace(' ', '_')
                attrs = {}
                for attr in WFPeaks.channel_attrs:
                    attrs[attr] = getattr(self, attr+'_'+name)
                paramsCFD[channel] = attrs

            cfdpars['paramsCFD'] = paramsCFD
            wfpeaks = psWFPeaks.WFPeaks(**cfdpars)

            def peakFinder(wts, wfs):
                peaks = wfpeaks(wfs, wts)
                return peaks

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=peakFinder, parent=self.name())
            return node

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
                      ('num hits', 'intSpin', {'value': 16, 'min': 1, 'max': MAX}),
                      ('verbose', 'check', {'checked': False})]

        def __init__(self, name):
            super().__init__(name, terminals={'Event Number': {'io': 'in', 'ttype': int},
                                              'Num of Hits': {'io': 'in', 'ttype': Array1d},
                                              'Peak Times': {'io': 'in', 'ttype': Array2d},
                                              'Calib': {'io': 'in', 'ttype': typing.Dict},
                                              'X': {'io': 'out', 'ttype': Array1d},
                                              'Y': {'io': 'out', 'ttype': Array1d},
                                              'R': {'io': 'out', 'ttype': Array1d},
                                              'T': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            dldpars = {'numchs': int(self.values['num chans']),
                       'numhits': self.values['num hits'],
                       'verbose': self.values['verbose'],
                       'consts': None}

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=DLDProc(**dldpars), parent=self.name())

            return node

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
        uiTemplate = [('num bunches', 'intSpin', {'value': 1, 'min': 1, 'max': MAX}),
                      ('snr filter', 'doubleSpin', {'value': 10.0, 'min': 0, 'max': MAX}),
                      ('roi expand', 'doubleSpin', {'value': 1.0, 'min': -MAX, 'max': MAX}),
                      ('roi fraction', 'doubleSpin', {'value': 0.001, 'min': 0, 'max': 1}),
                      ('island split method',  'combo', {'values': ["scipyLabel", "contourLabel"]}),
                      ('island split par1', 'doubleSpin', {'value': 3.0, 'min': -MAX, 'max': MAX}),
                      ('island split par2', 'doubleSpin', {'value': 5.0, 'min': -MAX, 'max': MAX})]

        def __init__(self, name):
            super().__init__(name, terminals={'src': {'io': 'in', 'ttype': DataSource},
                                              'cam': {'io': 'in', 'ttype': Detector},
                                              'pars': {'io': 'in', 'ttype': Detector},
                                              'time': {'io': 'out', 'ttype': Array2d},
                                              'power': {'io': 'out', 'ttype': Array2d},
                                              'agreement': {'io': 'out', 'ttype': float},
                                              'pulse': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            locpars = {'num_bunches': self.values['num bunches'],
                       'snr_filter': self.values['snr filter'],
                       'roi_expand': self.values['roi expand'],
                       'roi_fraction': self.values['roi fraction'],
                       'island_split_method': self.values['island split method'],
                       'island_split_par1': self.values['island split par1'],
                       'island_split_par2': self.values['island split par2']}

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=LOCProc(**locpars), parent=self.name())

            return node

except ImportError as e:
    print(e)

try:
    from numba import jit

    class PeakFinder1D(CtrlNode):

        """
        1D Peakfinder
        """

        nodeName = "PeakFinder1D"
        uiTemplate = [('threshold lo', 'doubleSpin', {'value': 0, 'min': -MAX, 'max': MAX}),
                      ('threshold hi', 'doubleSpin', {'value': 1, 'min': -MAX, 'max': MAX})]

        def __init__(self, name):
            super().__init__(name, terminals={"Waveform": {'io': 'in', 'ttype': Array1d},
                                              "Centroid": {'io': 'out', 'ttype': Array1d},
                                              "Width": {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

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

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=peakfinder1d, parent=self.name())
            return node

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

            self.menu.removeAction(addInput)
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
        uiTemplate = [('npix min', 'doubleSpin', {'value': 20, 'min': -MAX, 'max': MAX}),
                      ('npix max', 'doubleSpin', {'value': 25, 'min': -MAX, 'max': MAX}),
                      ('amax thr', 'doubleSpin', {'value': 0, 'min': -MAX, 'max': MAX}),
                      ('atot thr', 'doubleSpin', {'value': 0, 'min': -MAX, 'max': MAX}),
                      ('son min', 'doubleSpin', {'value': 0, 'min': -MAX, 'max': MAX}),
                      # pass to peak_finder_v4r3_d2
                      ('thr low', 'doubleSpin', {'value': 35, 'min': -MAX, 'max': MAX}),
                      ('thr high', 'doubleSpin', {'value': 100, 'min': -MAX, 'max': MAX}),
                      ('rank', 'doubleSpin', {'value': 2, 'min': -MAX, 'max': MAX}),
                      ('r0', 'doubleSpin', {'value': 4, 'min': -MAX, 'max': MAX}),
                      ('dr', 'doubleSpin', {'value': 0.05, 'min': -MAX, 'max': MAX})]

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

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

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

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=PeakfinderAlgos(constructor_params, call_params, list(self.outputs().keys())),
                          parent=self.name())

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

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=EdgeFinderProc({}), parent=self.name())

            return node

except ImportError as e:
    print(e)


try:
    from psana.pop.POP import POP as psanaPOP

    class POPProc(object):

        def __init__(self, args):
            self.args = args
            self.calibconsts = {}
            self.accum_num = args.pop('accum_num', 1)
            self.normalize_dist = args.pop('normalizeDist', True)
            self.proc = None
            self.img = None
            self.counter = 0

        def __call__(self, img, calib):
            init = False
            if self.calibconsts.keys() != calib.keys():
                init = True
            elif not all(np.array_equal(self.calibconsts[key], calib[key]) for key in calib):
                init = True

            if init:
                self.calibconsts = calib
                self.img = np.zeros(img.shape)
                self.counter += 1
                calib_dict, _ = calib.get('pop_rbfs')
                self.proc = psanaPOP(img=img, RBFs_dict=calib_dict, **self.args)

                self.slice_img = np.array([[np.nan]])
                self.rbins = np.array([np.nan, np.nan])
                self.distr = np.array([np.nan])
                self.ebins = np.array([np.nan, np.nan])
                self.diste = np.array([np.nan])

            self.img += img

            if self.counter % self.accum_num == 0:
                pop = self.proc
                pop.Peel(self.img)
                self.slice_img = pop.GetSlice()
                self.rbins, self.distr = pop.GetRadialDist()
                self.ebins, self.diste = pop.GetEnergyDist()
                self.counter = 1
                self.img = np.zeros(img.shape)
                if self.normalize_dist:
                    self.distr = self.distr/self.distr.max()
                    self.diste = self.diste/self.diste.max()
            else:
                self.counter += 1

            return self.slice_img, self.rbins[1:], self.distr, self.ebins[1:], self.diste

    class POP(CtrlNode):

        """
        psana POP
        """

        nodeName = "POP"

        uiTemplate = [('lmax', 'intSpin', {'value': 4, 'values': ['2', '4', '6', '8', '10', '12']}),
                      ('reg', 'doubleSpin', {'value': 0, 'max': MAX}),
                      ('alpha', 'doubleSpin', {'value': 4e-4, 'max': MAX})
                      ('X0', 'intSpin', {'value': 512, 'max': MAX}),
                      ('Y0', 'intSpin', {'value': 512, 'max': MAX}),
                      ('Rmax', 'intSpin', {'value': 512, 'max': MAX}),
                      ('edge_w', 'intSpin', {'value': 10, 'max': MAX}),
                      ('accum_num', 'intSpin', {'value': 30, 'min': 0}),
                      ('normalizeDist', 'check', {'checked': True})]

        def __init__(self, name):
            super().__init__(name, terminals={'Image': {'io': 'in', 'ttype': Array2d},
                                              'sliceImg': {'io': 'out', 'ttype': Array2d},
                                              'Rbins': {'io': 'out', 'ttype': Array1d},
                                              'DistR': {'io': 'out', 'ttype': Array1d},
                                              'Ebins': {'io': 'out', 'ttype': Array1d},
                                              'DistE': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()),
                          inputs=list(inputs.values()), outputs=outputs, parent=self.name(),
                          func=POPProc(self.values))
            return node

except ImportError as e:
    print(e)
