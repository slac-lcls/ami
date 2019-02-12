#!/usr/bin/env python
import logging
import multiprocessing as mp
import time
import dill
import tempfile
import asyncio
import zmq
import zmq.asyncio
import ami.client.flowchart_messages as fcMsgs

from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.Node import Node
from ami.flowchart.library import LIBRARY
from ami import LogConfig
from ami.comm import GraphCommHandler
from pyqtgraph.Qt import QtGui
from asyncqt import QEventLoop


logger = logging.getLogger(LogConfig.get_package_name(__name__))


def run_main_window(queue, graphmgr_addr, node_pubsub_addr, node_pushpull_addr):
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
    fc = Flowchart(queue=queue, graphmgr_addr=graphmgr_addr,
                   node_pubsub_addr=node_pubsub_addr, node_pushpull_addr=node_pushpull_addr)

    y = 0
    for name in comm.names:
        fc.addNode(Node(name=name, terminals={'Out': {'io': 'out'}}), name=name, pos=[0, y])
        y += 150

    w = fc.widget()
    fw = w.chartWidget

    # Add flowchart control panel to the main window
    layout.addWidget(w, 0, 0, 2, 1)
    layout.addWidget(fw, 0, 1)

    win.show()
    with loop:
        loop.run_forever()

    queue.put(fcMsgs.Msg("exit"))


class NodeWindow:

    def __init__(self, msg, graphmgr_addr, node_pubsub_addr, node_pushpull_addr):
        self.app = QtGui.QApplication([])
        loop = QEventLoop(self.app)
        asyncio.set_event_loop(loop)

        self.win = QtGui.QMainWindow()

        self.node = LIBRARY.getNodeType(msg.node_type)(msg.name)
        self.graphmgr_addr = graphmgr_addr
        self.inputs = []
        self.conditions = []

        self.ctx = zmq.asyncio.Context()
        self.sub_sock = self.ctx.socket(zmq.SUB)

        self.sub_sock.connect(node_pubsub_addr)
        self.sub_sock.setsockopt_string(zmq.SUBSCRIBE, msg.name)

        self.push_sock = self.ctx.socket(zmq.PUSH)
        self.push_sock.connect(node_pushpull_addr)

        self.widget = None
        self.show = False
        self.win.setWindowTitle(msg.name)

        with loop:
            loop.run_until_complete(self.process())

    async def process(self):
        while True:
            await self.sub_sock.recv_string()
            msg = await self.sub_sock.recv_pyobj()

            if isinstance(msg, fcMsgs.UpdateNodeAttributes):
                self.update(msg)
            elif isinstance(msg, fcMsgs.Display):
                self.display(msg)
            elif isinstance(msg, fcMsgs.Msg):
                if msg.name == 'operation':
                    self.operation()
                elif msg.name == 'exit':
                    return

    def update(self, msg):
        print("Received", self.node.name(), msg.inputs, msg.conditions)
        self.inputs = msg.inputs
        self.conditions = msg.conditions

    def display(self, msg):
        if self.widget is None:
            self.widget = self.node.display(msg.inputs, self.graphmgr_addr, self.win)
            self.win.setCentralWidget(self.widget)

        self.show = not self.show
        if self.show:
            self.win.show()
        else:
            self.win.hide()

    def operation(self):
        print(self.node.name(), self.inputs, self.conditions)
        node = dill.dumps(self.node.to_operation(self.inputs, self.conditions))
        self.push_sock.send(node)


def run_client(graphmgr_addr, load):
    ipcdir = tempfile.mkdtemp()
    node_pubsub_addr = "ipc://%s/node_pubsub" % ipcdir
    node_pushpull_addr = "ipc://%s/node_pushpull" % ipcdir
    queue = mp.Queue()

    list_proc = mp.Process(
        target=run_main_window,
        args=(queue, graphmgr_addr, node_pubsub_addr, node_pushpull_addr),
        daemon=True)
    list_proc.start()

    widget_procs = {}
    while True:
        msg = queue.get()

        if msg.name == 'exit':
            logger.info("received exit signal - exiting!")
            for name, proc in widget_procs.items():
                proc.join()
            break

        elif isinstance(msg, fcMsgs.CreateNode):
            proc = mp.Process(
                target=NodeWindow,
                args=(msg, graphmgr_addr, node_pubsub_addr, node_pushpull_addr),
                daemon=True
            )
            proc.start()
            logger.info("creating process: %s pid: %d", msg.name, proc.pid)
            widget_procs[msg.name] = proc

        dead_procs = []
        for name, proc in widget_procs.items():
            if not proc.is_alive():
                dead_procs.append(name)

        for name in dead_procs:
            del widget_procs[name]
