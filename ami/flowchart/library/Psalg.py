from ami.flowchart.library.common import CtrlNode, MAX
from amitypes import Array1d
import ami.graph_nodes as gn
import numpy as np


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

            sampleInterval = self.Sample_Interval
            horpos = self.horpos
            gain = self.gain
            offset = self.offset
            delay = self.delay
            walk = self.walk
            threshold = self.threshold
            fraction = self.fraction

            def cfd_func(waveform):
                return cfd.cfd(sampleInterval, horpos, gain, offset, waveform, delay, walk, threshold, fraction)

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=cfd_func,
                          parent=self.name())
            return node

except ImportError:
    pass

try:
    import psana.hexanode.WFPeaks as psWFPeaks
    from typing import Any

    class WFPeaks(CtrlNode):

        """
        WFPeaks
        """

        nodeName = "WFPeaks"
        uiTemplate = [('num chans', 'combo', {'values': ["5", "7"]}),
                      ('num hits', 'intSpin', {'value': 16, 'min': 1, 'max': MAX}),
                      ('base', 'doubleSpin', {'value': 0., 'min': 0., 'max': MAX}),
                      ('thr', 'doubleSpin', {'value': -0.05}),
                      ('cfr', 'doubleSpin', {'value': 0.85}),
                      ('deadtime', 'doubleSpin', {'value': 10.0}),
                      ('leadingedge', 'check', {'checked': True}),
                      ('ioffsetbeg', 'intSpin', {'value': 1000, 'min': 0, 'max': MAX}),
                      ('ioffsetend', 'intSpin', {'value': 2000, 'min': 0, 'max': MAX}),
                      ('wfbinbeg', 'intSpin', {'value': 6000, 'min': 0, 'max': MAX}),
                      ('wfbinend', 'intSpin', {'value': 22000, 'min': 0, 'max': MAX})]

        def __init__(self, name):
            super().__init__(name, terminals={'Waveform.1': {'io': 'in', 'ttype': Array1d},
                                              'Waveform.2': {'io': 'in', 'ttype': Array1d},
                                              'Waveform.3': {'io': 'in', 'ttype': Array1d},
                                              'Waveform.4': {'io': 'in', 'ttype': Array1d},
                                              'Waveform.5': {'io': 'in', 'ttype': Array1d},
                                              'Times': {'io': 'in', 'ttype': Array1d},
                                              'Num of Hits': {'io': 'out', 'ttype': float},
                                              'Kinds': {'io': 'out', 'ttype': Any},
                                              'Values': {'io': 'out', 'ttype': Array1d},
                                              'Peak Times': {'io': 'out', 'ttype': Array1d}})

        def to_operation(self, inputs, conditions={}):
            outputs = self.output_vars()

            cfdpars = {'numchs': self.num_chans,
                       'numhits': self.num_hits,
                       'cfd_base':  self.base,
                       'cfd_thr': self.thr,
                       'cfd_cfr':  self.cfr,
                       'cfd_deadtime':  self.deadtime,
                       'cfd_leadingedge':  self.leadingedge,
                       'cfd_ioffsetbeg':  self.ioffsetbeg,
                       'cfd_ioffsetend':  self.ioffsetend,
                       'cfd_wfbinbeg':  self.wfbinbeg,
                       'cfd_wfbinend': self.wfbinend}

            def peakFinder(wfs0, wfs1, wfs2, wfs3, wfs4, wfs5, wts):
                wfs = np.vstack((wfs0, wfs1, wfs2, wfs3, wfs4, wfs5))
                wfpeaks = psWFPeaks.WFPeaks(**cfdpars)
                peaks = wfpeaks(wfs, wts)
                return peaks

            node = gn.Map(name=self.name()+"_operation",
                          condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                          func=peakFinder, parent=self.name())
            print(node)
            return node

except ImportError:
    pass
