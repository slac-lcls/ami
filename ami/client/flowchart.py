#!/usr/bin/env python
import logging
import multiprocessing as mp
import time
import dill
import tempfile
import asyncio
import zmq
import zmq.asyncio

from ami.client import flowchart_messages as fcMsgs
from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.Node import Node
from ami.flowchart.library import LIBRARY
from ami import LogConfig
from ami.comm import GraphCommHandler
from pyqtgraph.Qt import QtGui
from asyncqt import QEventLoop


logger = logging.getLogger(LogConfig.get_package_name(__name__))


def run_editor_window(broker_addr, graphmgr_addr, node_addr):
    app = QtGui.QApplication([])

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create main window with grid layout
    win = QtGui.QMainWindow()
    win.setWindowTitle('AMI Client')
    cw = QtGui.QWidget()
    win.setCentralWidget(cw)
    layout = QtGui.QGridLayout()
    cw.setLayout(layout)

    # TODO fix this
    time.sleep(2)
    comm = GraphCommHandler(graphmgr_addr)

    # Create flowchart, define input/output terminals
    fc = Flowchart(broker_addr=broker_addr,
                   graphmgr_addr=graphmgr_addr,
                   node_addr=node_addr)

    y = 0
    for name in comm.names:
        fc.addNode(Node(name=name, terminals={'Out': {'io': 'out'}}), name=name, pos=[0, y])
        y += 150

    w = fc.widget()
    fw = w.chartWidget

    # Add flowchart control panel to the main window
    layout.addWidget(w.ui.toolBar, 0, 0, 1, -1)
    layout.addWidget(fw, 1, 0)

    win.show()
    with loop:
        loop.run_forever()


class NodeWindow(object):

    def __init__(self, msg, broker_addr, graphmgr_addr, editor_addr):
        self.app = QtGui.QApplication([])
        loop = QEventLoop(self.app)
        asyncio.set_event_loop(loop)

        self.win = QtGui.QMainWindow()

        self.node = LIBRARY.getNodeType(msg.node_type)(msg.name)
        self.graphmgr_addr = graphmgr_addr
        self.inputs = []
        self.conditions = []

        self.ctx = zmq.asyncio.Context()

        self.broker = self.ctx.socket(zmq.SUB)
        self.broker.connect(broker_addr)
        self.broker.setsockopt_string(zmq.SUBSCRIBE, msg.name)

        self.editor = self.ctx.socket(zmq.PUSH)
        self.editor.connect(editor_addr)

        self.ctrlWidget = None
        self.widget = None
        self.show = False
        self.win.setWindowTitle(msg.name)

        with loop:
            loop.run_until_complete(self.process())

    async def process(self):
        while True:
            await self.broker.recv_string()
            msg = await self.broker.recv_pyobj()

            if isinstance(msg, fcMsgs.UpdateNodeAttributes):
                self.update(msg)
            elif isinstance(msg, fcMsgs.DisplayNode):
                self.display(msg)
            elif isinstance(msg, fcMsgs.GetNodeOperation):
                self.operation()
            elif isinstance(msg, fcMsgs.CloseNode):
                return

    def update(self, msg):
        self.inputs = msg.inputs
        self.conditions = msg.conditions

    def display(self, msg):
        if self.ctrlWidget is None and self.widget is None:
            self.ctrlWidget = self.node.ctrlWidget()
            self.widget = self.node.display(msg.inputs, self.graphmgr_addr, self.win)

            if self.ctrlWidget and self.widget:
                cw = QtGui.QWidget()
                self.win.setCentralWidget(cw)
                layout = QtGui.QGridLayout()
                cw.setLayout(layout)
                layout.addWidget(self.ctrlWidget, 0, 0)
                layout.addWidget(self.widget, 0, 1, -1, -1)
                layout.setColumnStretch(1, 10)
            elif self.ctrlWidget:
                self.win.setCentralWidget(self.ctrlWidget)
            elif self.widget:
                self.win.setCentralWidget(self.widget)

        self.show = not self.show
        if self.show:
            self.win.show()
        else:
            self.win.hide()

    def operation(self):
        node = dill.dumps(self.node.to_operation(self.inputs, self.conditions))
        self.editor.send(node)


class MessageBroker(object):

    def __init__(self, graphmgr_addr, load):

        ipcdir = tempfile.mkdtemp()

        self.graphmgr_addr = graphmgr_addr
        self.broker_sub_addr = "ipc://%s/broker_sub" % ipcdir
        self.broker_pub_addr = "ipc://%s/broker_pub" % ipcdir
        self.node_addr = "ipc://%s/nodes" % ipcdir

        self.lock = asyncio.Lock()
        self.msgs = {}
        self.widget_procs = {}

        self.ctx = zmq.asyncio.Context()
        self.broker_sub_sock = self.ctx.socket(zmq.SUB)
        self.broker_sub_sock.setsockopt_string(zmq.SUBSCRIBE, '')
        self.broker_sub_sock.bind(self.broker_sub_addr)

        self.broker_pub_sock = self.ctx.socket(zmq.XPUB)
        self.broker_pub_sock.bind(self.broker_pub_addr)

        self.launch_editor_window()

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.run())

    def launch_editor_window(self):
        editor_proc = mp.Process(
            target=run_editor_window,
            args=(self.broker_sub_addr, self.graphmgr_addr, self.node_addr),
            daemon=True)
        editor_proc.start()

        self.widget_procs["editor"] = editor_proc

    async def handle_connect(self):

        while True:
            topic = await self.broker_pub_sock.recv_string()

            if topic.startswith('\x01'):
                topic = topic.lstrip('\x01')
                async with self.lock:
                    if topic in self.msgs:
                        msg = self.msgs[topic]
                        self.broker_pub_sock.send_string(topic, zmq.SNDMORE)
                        self.broker_pub_sock.send_pyobj(msg)
                    else:
                        continue

    async def forward_message(self, topic, msg):
        if isinstance(msg, fcMsgs.NodeMsg):
            async with self.lock:
                self.msgs[topic] = msg
                await self.broker_pub_sock.send_string(topic, zmq.SNDMORE)
                await self.broker_pub_sock.send_pyobj(msg)

    async def process_messages(self):

        while True:
            topic = await self.broker_sub_sock.recv_string()
            msg = await self.broker_sub_sock.recv_pyobj()

            if isinstance(msg, fcMsgs.CreateNode):
                proc = mp.Process(
                    target=NodeWindow,
                    args=(msg, self.broker_pub_addr, self.graphmgr_addr, self.node_addr),
                    daemon=True
                )
                proc.start()
                logger.info("creating process: %s pid: %d", msg.name, proc.pid)
                async with self.lock:
                    self.widget_procs[msg.name] = proc

            elif isinstance(msg, fcMsgs.UpdateNodeAttributes):
                await self.forward_message(topic, msg)

            elif isinstance(msg, fcMsgs.GetNodeOperation):
                await self.forward_message(topic, msg)

            elif isinstance(msg, fcMsgs.DisplayNode):
                await self.forward_message(topic, msg)

            elif isinstance(msg, fcMsgs.CloseNode):
                await self.forward_message(topic, msg)

                async with self.lock:
                    if topic in self.widget_procs:
                        proc = self.widget_procs[topic]
                        logger.info("deleting process: %s pid: %d", topic, proc.pid)
                        proc.join()
                        del self.widget_procs[topic]

            elif isinstance(msg, fcMsgs.ExitMsg):
                logger.info("received exit signal - exiting!")
                for topic in self.msgs:
                    await self.broker_pub_sock.send_string(topic)
                    await self.broker_pub_sock.send_pyobj(fcMsgs.CloseMsg())

                for name, proc in self.widget_procs.items():
                    proc.join()
                break

            dead_procs = []
            for name, proc in self.widget_procs.items():
                if not proc.is_alive():
                    dead_procs.append(name)

            for name in dead_procs:
                del self.widget_procs[name]

    async def run(self):
        await asyncio.gather(self.handle_connect(),
                             self.process_messages())


def run_client(graphmgr_addr, load):
    MessageBroker(graphmgr_addr, load)
