from typing import Union, Any
from qtpy import QtCore, QtWidgets
from amitypes import Array1d, Array2d
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn


class ExportToWorker(CtrlNode):

    """
    Send data back to worker from global collector.
    """

    nodeName = "ExportToWorker"
    uiTemplate = [('alias', 'text', {'tip': "Name to export data under."})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any},
                                          "Out": {'io': 'out', 'ttype': Any}},
                         exportable=True)


class PvExport(CtrlNode):

    """
    Export data through an AMI hosted PV using either PV access or channel access.
    """

    nodeName = "PvExport"
    uiTemplate = [('alias', 'text', {'tip': "PV name to export variable under."})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any}},
                         exportable=True)


class ZMQWidget(QtWidgets.QLabel):

    def __init__(self, topics=None, terms=None, addr=None, parent=None, **kwargs):
        super().__init__(parent)

        topic_label = ""

        if addr:
            topic_label = f"Address: {addr.view}\n"

        if terms:
            for term, name in terms.items():
                topic = topics[name]
                sub_topic = "Sub Topic Name: view:%s:%s\\0" % (addr.name, topic)
                topic_label += sub_topic + "\n"

        self.setText(topic_label)
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)


class ZMQ(CtrlNode):

    """
    Export data over ZMQ PUB/SUB
    """

    nodeName = "ZMQ"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any}},
                         allowAddInput=True,
                         viewable=True)

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, ZMQWidget, **kwargs)

try:
    import caproto.threading.client as ct

    class CaputProc():
        def __init__(self, pvname):
            self.pvname = pvname
            self.ctx = None
            self.pv = None

        def __call__(self, value):
            if self.ctx is None:
                self.ctx = ct.Context()
                self.pv = self.ctx.get_pvs(self.pvname)[0]
            return self.pv.write(value)

    class Caput(CtrlNode):

        """
        Send data to an existing externally hosted PV via Channel Access.
        """

        nodeName = "Caput"
        uiTemplate = [('pvname', 'text'),
                      ('global', 'check', {'checked': True,
                                           'tip': "Insert Pick1 and export values from global collector."})]

        def __init__(self, name):
            super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Union[str, int, float, Array1d]}})

        def to_operation(self, inputs, outputs, **kwargs):
            outputs = [self.name()+"_unused"]
            picked_outputs = [self.name()+"_pickedoutput"]

            if self.values['global']:
                nodes = [gn.PickN(name=self.name()+"_picked",
                                  inputs=inputs, outputs=picked_outputs, N=1, **kwargs),
                         gn.Map(name=self.name()+"_operation",
                                inputs=picked_outputs, outputs=outputs,
                                func=CaputProc(self.values['pvname']), **kwargs)]
            else:
                nodes = [gn.Map(name=self.name()+"_operation",
                                inputs=inputs, outputs=outputs,
                                func=CaputProc(self.values['pvname']), **kwargs)]

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
        Send data to an existing externally hosted PV via PVAccess.
        """

        nodeName = "Pvput"
        uiTemplate = [('pvname', 'text'),
                      ('global', 'check', {'checked': True,
                                           'tip': "Insert Pick1 and export values from global collector."})]

        def __init__(self, name):
            super().__init__(name,
                             terminals={"In": {'io': 'in', 'ttype': Union[str, int, float, Array1d, Array2d]}})

        def to_operation(self, inputs, outputs, **kwargs):
            outputs = [self.name()+"_unused"]
            picked_outputs = [self.name()+"_pickedoutput"]

            if self.values['global']:
                nodes = [gn.PickN(name=self.name()+"_picked",
                                  inputs=inputs, outputs=picked_outputs,
                                  N=1, **kwargs),
                         gn.Map(name=self.name()+"_operation",
                                inputs=picked_outputs, outputs=outputs,
                                func=PvputProc(self.values['pvname']), **kwargs)]
            else:
                nodes = [gn.Map(name=self.name()+"_operation",
                                inputs=inputs, outputs=outputs,
                                func=PvputProc(self.values['pvname']), **kwargs)]

            return nodes

except ImportError as e:
    print(e)
