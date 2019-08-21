from ami.flowchart.library.common import CtrlNode, MAX
from amitypes import Array1d
import ami.graph_nodes as gn
import cfd


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
        super(CFD, self).__init__(name, terminals={'In': {'io': 'in', 'ttype': Array1d},
                                                   'Out': {'io': 'out', 'ttype': float}})
        self.set_func()

    def update(self, *args, **kwargs):
        super(CFD, self).update(*args, **kwargs)
        self.set_func()

    def set_func(self):
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

        self.func = cfd_func

    def to_operation(self, inputs, conditions={}):
        outputs = self.output_vars()
        node = gn.Map(name=self.name()+"_operation",
                      condition_needs=list(conditions.values()), inputs=list(inputs.values()), outputs=outputs,
                      func=self.func)
        return node
