from typing import Union
from amitypes import Array1d, Array2d
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn

try:
    import epics

    class CaputProc():
        def __init__(self, pvname):
            self.pvname = pvname
            self.pv = None

        def __call__(self, value):
            if self.pv is None:
                self.pv = epics.PV(self.pvname)
            return self.pv.put(value)

    class Caput(CtrlNode):

        """
        Send data to a PV via Channel Access.
        """

        nodeName = "Caput"
        uiTemplate = [('pvname', 'text')]

        def __init__(self, name):
            super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Union[str, int, float, Array1d]}})

        def to_operation(self, inputs, conditions={}):
            outputs = [self.name()+"_unused"]
            picked_outputs = [self.name()+"_pickedoutput"]

            nodes = [gn.PickN(name=self.name()+"_picked",
                              condition_needs=conditions, inputs=inputs, outputs=picked_outputs,
                              N=1, parent=self.name()),
                     gn.Map(name=self.name()+"_operation",
                            condition_needs=conditions, inputs=picked_outputs, outputs=outputs,
                            func=CaputProc(self.values['pvname']), parent=self.name())]
            return nodes

except ImportError as e:
    print(e)

try:
    import p4p.client.thread as pct

    class PvputProc():
        def __init__(self, pvname):
            self.pvname = pvname
            self.ctx = None

        def __call__(self, value):
            if self.ctx is None:
                self.ctx = pct.Context('pva')
            return self.ctx.put(self.pvname, value)

    class Pvput(CtrlNode):

        """
        Send data to a PV via PVAccess.
        """

        nodeName = "Pvput"
        uiTemplate = [('pvname', 'text')]

        def __init__(self, name):
            super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Union[str, int, float, Array1d, Array2d]}})

        def to_operation(self, inputs, conditions={}):
            outputs = [self.name()+"_unused"]
            picked_outputs = [self.name()+"_pickedoutput"]

            nodes = [gn.PickN(name=self.name()+"_picked",
                              condition_needs=conditions, inputs=inputs, outputs=picked_outputs,
                              N=1, parent=self.name()),
                     gn.Map(name=self.name()+"_operation",
                            condition_needs=conditions, inputs=picked_outputs, outputs=outputs,
                            func=PvputProc(self.values['pvname']), parent=self.name())]
            return nodes


except ImportError as e:
    print(e)
