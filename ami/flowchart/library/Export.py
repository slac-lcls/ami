from typing import Union, Any
from qtpy import QtCore, QtWidgets
from amitypes import Array1d, Array2d
from ami.comm import AMIWarning, GraphCommHandler
from ami.flowchart.library.common import CtrlNode
import ami.graph_nodes as gn
import socket
import time
import struct
import ipaddress


class ExportToWorker(CtrlNode):

    """
    Send data back to worker from global collector.
    """

    nodeName = "ExportToWorker"
    uiTemplate = [('alias', 'text', {'tip': "Name to export data under."})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any},
                                          "Timestamp": {'io': 'in', 'ttype': float},
                                          "Out": {'io': 'out', 'ttype': Any}},
                         exportable=True)


class PvExport(CtrlNode):

    """
    Export data through an AMI hosted PV using either PV access or channel access.
    """

    nodeName = "PvExport"
    uiTemplate = [('alias', 'text', {'tip': "PV name to export variable under."}),
                  ('events', 'intSpin', {'value': 2, 'min': 2, 'tip': "Number of events to export"})]

    def __init__(self, name):
        super().__init__(name, terminals={"In": {'io': 'in', 'ttype': Any},
                                          "eventid": {'io': 'in', 'ttype': int}},
                         exportable=True)

        self.lbl = QtWidgets.QLabel(parent=self.ui)
        self.ui.layout().addRow(self.lbl)
        self.graph = ""
        self.epics_prefix = ""
        self.graphCommHandler = None

    def display(self, topics, terms, addr, win, widget=None, **kwargs):
        if addr:
            self.graphCommHandler = GraphCommHandler(addr.name, addr.comm)
            self.graph = addr.name
            self.epics_prefix = self.graphCommHandler.epics_prefix

        val = self.values['alias']
        self.lbl.setText(f"pvname: {self.epics_prefix}:{self.graph}:data:{val}")
        return super().display(topics, terms, addr, win, widget, **kwargs)

    def state_changed(self, *args, **kwargs):
        super().state_changed(*args, **kwargs)
        name, group, val = args
        if name == 'alias':
            self.lbl.setText(f"pvname: {self.epics_prefix}:{self.graph}:{val}")

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
        super().__init__(name, terminals={"Timestamp": {'io': 'in', 'ttype': float},
                                          "In": {'io': 'in', 'ttype': Any}},
                         allowAddInput=True,
                         viewable=True)

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, ZMQWidget, **kwargs)


class McastProc():
    def __init__(self, grp, port, rate):
        self._nextTime = 0
        self.mcast_grp_port = (grp, int(port))
        self._rate = rate
        self._socket = None

    def __del__(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __call__(self, data, timestamp, pulseId):
        if self._socket is None:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self._socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 8)

        now = time.time()
        if now > self._nextTime:
            version = 0
            validMask = 0
            header = struct.pack('QQII', timestamp, pulseId, version, validMask)

            self._socket.sendmsg((header, data), (), 0, self.mcast_grp_port)
            self._nextTime = now + 1/self._rate
            #print(f"*** now {now}, nextTime {self._nextTime}, pd {1/self._rate}, ts %08x %08x, pid %08x %08x" % \
            #      (timestamp>>32, timestamp&((1<<32)-1), pulseId>>32, pulseId&((1<<32)-1)))

        return []


class Mcast(CtrlNode):

    """
    UDP multicast a reduced rate of input in BLD format.
    """

    nodeName = "Mcast"
    uiTemplate = [('Multicast Group', 'text'),
                  ('Port', 'text'),
                  ('rate_Hz', 'intSpin', {'value': 10, 'min': 1}),
                  ('global', 'check', {'checked': True,
                                       'tip': "Insert Pick1 and export values from global collector."})]

    def __init__(self, name):
        super().__init__(name,
                         terminals={'Data':  {'io': 'in', 'removable': False, 'ttype': Any},
                                    'Timestamp': {'io': 'in', 'removable': False, 'ttype': float},
                                    'PulseId':   {'io': 'in', 'removable': False, 'ttype': int}})

    def to_operation(self, inputs, outputs, **kwargs):

        if not ipaddress.IPv4Address(self.values['Multicast Group']).is_multicast:
            raise Exception("Invalid multicast address")

        picked_outputs = []
        for k, v in inputs.items():
            picked_outputs.append(f"{v}_picked")

        if self.values['global']:
            nodes = [gn.PickN(name=self.name()+"_picked",
                              inputs=inputs, outputs=picked_outputs,
                              N=1, **kwargs),
                     gn.Map(name=self.name()+"_operation",
                            inputs=picked_outputs, outputs=outputs,
                            func=McastProc(self.values['Multicast Group'],
                                           self.values['Port'],
                                           self.values['rate_Hz']), **kwargs)]
        else:
            nodes = [gn.Map(name=self.name()+"_operation",
                            inputs=inputs, outputs=outputs,
                            func=McastProc(self.values['Multicast Group'],
                                           self.values['Port'],
                                           self.values['rate_Hz']), **kwargs)]

        return nodes


try:
    import caproto
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
            try:
                return self.pv.write(value)
            except caproto._utils.CaprotoTimeoutError as e:
                raise AMIWarning(e)

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
            try:
                return self.ctx.put(self.pvname, value)
            except TimeoutError:
                raise AMIWarning("pvput timed out")

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
