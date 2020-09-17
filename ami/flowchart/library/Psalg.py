from pyqtgraph.Qt import QtGui, QtWidgets
from amitypes import DataSource, Detector, Array1d, Array2d
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
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
                          func=cfd_func, parent=self.name())
            return node

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

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()
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

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
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

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            dldpars = {'numchs': int(self.values['num chans']),
                       'numhits': self.values['num hits'],
                       'verbose': self.values['verbose'],
                       'consts': None}

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
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
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
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
        uiTemplate = [('threshold lo', 'doubleSpin', {'value': 0}),
                      ('threshold hi', 'doubleSpin', {'value': 1})]

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
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
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
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
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
                          condition_needs=conditions,
                          inputs=inputs, outputs=outputs,
                          func=EdgeFinderProc({}), parent=self.name())

            return node

except ImportError as e:
    print(e)
