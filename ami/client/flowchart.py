#!/usr/bin/env python
import logging
import multiprocessing as mp
import time
import dill
import tempfile
import asyncio
import zmq
import zmq.asyncio
import numpy as np

from ami.client import flowchart_messages as fcMsgs
from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.Node import Node
from ami.flowchart.library import LIBRARY
from ami import LogConfig
from ami.comm import GraphCommHandler
from pyqtgraph.Qt import QtGui, QtCore
from asyncqt import QEventLoop, asyncSlot


logger = logging.getLogger(LogConfig.get_package_name(__name__))


def run_editor_window(broker_addr, graphmgr_addr, node_addr, checkpoint_addr):
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
                   node_addr=node_addr,
                   checkpoint_addr=checkpoint_addr)

    y = 0
    types = {'cspad': np.ndarray, 'laser': bool, 'delta_t': int}
    for name in comm.names:
        fc.addNode(Node(name=name, terminals={'Out': {'io': 'out', 'type': types[name]}}), name=name, pos=[0, y])
        y += 150

    w = fc.widget()
    fw = w.chartWidget

    # Add flowchart control panel to the main window
    layout.addWidget(w.ui.toolBar, 0, 0, 1, -1)
    layout.addWidget(fw, 1, 0)

    win.show()
    with loop:
        loop.run_forever()


class NodeWindow(QtGui.QMainWindow):

    def __init__(self, proc, parent=None):
        super(NodeWindow, self).__init__(parent)
        self.proc = proc

    def closeEvent(self, event):
        self.proc.node.clear()
        self.proc.widget = None
        self.destroy()
        event.ignore()


class NodeProcess(QtCore.QObject):

    def __init__(self, msg, broker_addr, graphmgr_addr, editor_addr, checkpoint_addr):
        super(NodeProcess, self).__init__()
        self.app = QtGui.QApplication([])
        loop = QEventLoop(self.app)
        asyncio.set_event_loop(loop)

        self.win = NodeWindow(self)

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

        self.checkpoint = self.ctx.socket(zmq.PUB)
        self.checkpoint.connect(checkpoint_addr)

        self.ctrlWidget = self.node.ctrlWidget()
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
                await self.operation()
            elif isinstance(msg, fcMsgs.NodeCheckpoint):
                self.restore_checkpoint(msg)
            elif isinstance(msg, fcMsgs.CloseNode):
                return

    def update(self, msg):
        self.inputs = msg.inputs
        self.conditions = msg.conditions

    def display(self, msg):
        if self.widget is None:
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

            if self.ctrlWidget:
                self.node.sigStateChanged.connect(self.send_checkpoint)

        self.show = not self.show
        if self.show:
            self.win.show()
        else:
            self.win.hide()

    async def operation(self):
        node = dill.dumps(self.node.to_operation(self.inputs, self.conditions))
        await self.editor.send(node)

    @asyncSlot(object)
    async def send_checkpoint(self, node):
        msg = fcMsgs.NodeCheckpoint(node.name(),
                                    inputs=self.inputs,
                                    conditions=self.conditions,
                                    state=node.saveState())
        await self.checkpoint.send_string(node.name(), zmq.SNDMORE)
        await self.checkpoint.send_pyobj(msg)

    def restore_checkpoint(self, checkpoint):
        self.inputs = checkpoint.inputs
        self.conditions = checkpoint.conditions
        self.node.restoreState(checkpoint.state)


class MessageBroker(object):

    def __init__(self, graphmgr_addr, load):

        ipcdir = tempfile.mkdtemp()

        self.graphmgr_addr = graphmgr_addr
        self.broker_sub_addr = "ipc://%s/broker_sub" % ipcdir
        self.broker_pub_addr = "ipc://%s/broker_pub" % ipcdir
        self.node_addr = "ipc://%s/nodes" % ipcdir

        self.checkpoint_sub_addr = "ipc://%s/checkpoint_sub" % ipcdir
        self.checkpoint_pub_addr = "ipc://%s/checkpoint_pub" % ipcdir

        self.lock = asyncio.Lock()
        self.msgs = {}
        self.checkpoints = {}
        self.widget_procs = {}

        self.ctx = zmq.asyncio.Context()

        self.broker_sub_sock = self.ctx.socket(zmq.SUB)
        self.broker_sub_sock.setsockopt_string(zmq.SUBSCRIBE, '')
        self.broker_sub_sock.bind(self.broker_sub_addr)

        self.broker_pub_sock = self.ctx.socket(zmq.XPUB)
        self.broker_pub_sock.bind(self.broker_pub_addr)

        self.checkpoint_sub_sock = self.ctx.socket(zmq.SUB)
        self.checkpoint_sub_sock.setsockopt_string(zmq.SUBSCRIBE, '')
        self.checkpoint_sub_sock.bind(self.checkpoint_sub_addr)

        self.checkpoint_pub_sock = self.ctx.socket(zmq.PUB)
        self.checkpoint_pub_sock.bind(self.checkpoint_pub_addr)

        self.launch_editor_window()

    def launch_editor_window(self):
        editor_proc = mp.Process(
            target=run_editor_window,
            args=(self.broker_sub_addr, self.graphmgr_addr, self.node_addr, self.checkpoint_pub_addr),
            daemon=True)
        editor_proc.start()

        self.editor = editor_proc

    def wait_editor_exit(self):
        self.editor.join()

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

    async def handle_checkpoint(self):

        while True:
            topic = await self.checkpoint_sub_sock.recv_string()
            msg = await self.checkpoint_sub_sock.recv_pyobj()

            async with self.lock:
                self.checkpoints[topic] = msg

            await self.checkpoint_pub_sock.send_string(topic)
            await self.checkpoint_pub_sock.send_pyobj(msg.state)

    async def forward_message_to_node(self, topic, msg):
        if isinstance(msg, fcMsgs.NodeMsg):
            async with self.lock:
                self.msgs[topic] = msg

            await self.broker_pub_sock.send_string(topic, zmq.SNDMORE)
            await self.broker_pub_sock.send_pyobj(msg)

    async def monitor_processes(self):

        while True:
            await asyncio.sleep(0.25)

            dead_procs = []
            for name, ntp in self.widget_procs.items():
                node_type, proc = ntp
                if not proc.is_alive():
                    dead_procs.append(name)

            async with self.lock:
                for name in dead_procs:
                    typ, proc = self.widget_procs[name]
                    msg = fcMsgs.CreateNode(name, typ)

                    # don't resend last message
                    del self.msgs[msg.name]

                    proc = mp.Process(
                        target=NodeProcess,
                        args=(msg, self.broker_pub_addr, self.graphmgr_addr, self.node_addr, self.checkpoint_sub_addr),
                        daemon=True
                    )
                    proc.start()
                    logger.info("restarting process: %s pid: %d", msg.name, proc.pid)
                    self.widget_procs[msg.name] = (msg.node_type, proc)

                    if name in self.checkpoints:
                        checkpoint = self.checkpoints[name]
                        self.msgs[name] = checkpoint
                        await self.broker_pub_sock.send_string(name, zmq.SNDMORE)
                        await self.broker_pub_sock.send_pyobj(checkpoint)

    async def process_messages(self):

        while True:
            topic = await self.broker_sub_sock.recv_string()
            msg = await self.broker_sub_sock.recv_pyobj()

            if isinstance(msg, fcMsgs.CreateNode):
                proc = mp.Process(
                    target=NodeProcess,
                    args=(msg, self.broker_pub_addr, self.graphmgr_addr, self.node_addr, self.checkpoint_sub_addr),
                    daemon=True
                )
                proc.start()
                logger.info("creating process: %s pid: %d", msg.name, proc.pid)
                async with self.lock:
                    self.widget_procs[msg.name] = (msg.node_type, proc)

            elif isinstance(msg, fcMsgs.UpdateNodeAttributes):
                await self.forward_message_to_node(topic, msg)

            elif isinstance(msg, fcMsgs.GetNodeOperation):
                await self.forward_message_to_node(topic, msg)

            elif isinstance(msg, fcMsgs.DisplayNode):
                await self.forward_message_to_node(topic, msg)

            elif isinstance(msg, fcMsgs.NodeCheckpoint):
                # Receive checkpoints from editor when we load a saved graph
                await self.forward_message_to_node(topic, msg)
                async with self.lock:
                    self.checkpoints[topic] = msg

            elif isinstance(msg, fcMsgs.CloseNode):
                await self.forward_message_to_node(topic, msg)

                async with self.lock:
                    if topic in self.widget_procs:
                        logger.info("deleting process: %s pid: %d", topic, proc.pid)
                        _, proc = self.widget_procs[topic]
                        proc.join()
                        del self.widget_procs[topic]

            elif isinstance(msg, fcMsgs.ExitMsg):
                logger.info("received exit signal - exiting!")
                for topic in self.msgs:
                    await self.broker_pub_sock.send_string(topic)
                    await self.broker_pub_sock.send_pyobj(fcMsgs.CloseMsg())

                for name, ntp in self.widget_procs.items():
                    node_type, proc = np
                    proc.join()
                break

    async def run(self):
        await asyncio.gather(self.handle_connect(),
                             self.handle_checkpoint(),
                             self.process_messages(),
                             self.monitor_processes())


def run_client(graphmgr_addr, load):
    mb = MessageBroker(graphmgr_addr, load)

    loop = asyncio.get_event_loop()
    task = asyncio.ensure_future(mb.run())

    # wait for the editor window to exit
    loop.run_until_complete(loop.run_in_executor(None, mb.wait_editor_exit))

    # if the message brokers task is still running cancel it
    if not task.done():
        task.cancel()
