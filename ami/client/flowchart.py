#!/usr/bin/env python
import logging
import multiprocessing as mp
import tempfile
import asyncio
import zmq
import zmq.asyncio

from ami import LogConfig
from ami.client import flowchart_messages as fcMsgs
from ami.profiler import Profiler
from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.library import LIBRARY
from ami.flowchart.library.common import SourceNode
from ami.asyncqt import QEventLoop, asyncSlot
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets


logger = logging.getLogger(LogConfig.get_package_name(__name__))


def run_editor_window(broker_addr, graphmgr_addr, checkpoint_addr, load=None):
    app = QtGui.QApplication([])

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create main window with grid layout
    win = QtGui.QMainWindow()
    win.setWindowTitle('AMI Client')

    # Create flowchart, define input/output terminals
    fc = Flowchart(broker_addr=broker_addr,
                   graphmgr_addr=graphmgr_addr,
                   checkpoint_addr=checkpoint_addr)

    def update_title(filename):
        if filename:
            win.setWindowTitle('AMI Client - ' + filename.split('/')[-1])
        else:
            win.setWindowTitle('AMI Client')

    fc.sigFileLoaded.connect(update_title)
    fc.sigFileSaved.connect(update_title)

    loop.run_until_complete(fc.updateSources(init=True))

    # Add flowchart control panel to the main window
    win.setCentralWidget(fc.widget())
    win.show()

    # Load a flowchart chart into the editor window
    if load:
        fc.loadFile(load)

    try:
        task = asyncio.ensure_future(fc.run())
        loop.run_forever()
    finally:
        if not task.done():
            task.cancel()
        loop.close()


class NodeWindow(QtGui.QMainWindow):

    def __init__(self, proc, parent=None):
        super().__init__(parent)
        self.proc = proc

    def closeEvent(self, event):
        self.proc.send_checkpoint(self.proc.node)
        self.proc.node.clear()
        self.proc.widget = None
        self.proc.show = False
        self.destroy()
        event.ignore()


class NodeProcess(QtCore.QObject):

    def __init__(self, msg, broker_addr="", graphmgr_addr="", checkpoint_addr="", loop=None):
        super().__init__()

        if loop is None:
            self.app = QtGui.QApplication([])
            loop = QEventLoop(self.app)

        asyncio.set_event_loop(loop)

        self.win = NodeWindow(self)

        if msg.node_type == "SourceNode":
            self.node = SourceNode(name=msg.name)
        else:
            self.node = LIBRARY.getNodeType(msg.node_type)(msg.name)

        self.node.restoreState(msg.state)
        self.graphmgr_addr = graphmgr_addr
        self.ctx = zmq.asyncio.Context()

        self.broker = self.ctx.socket(zmq.SUB)
        self.broker.connect(broker_addr)
        self.broker.setsockopt_string(zmq.SUBSCRIBE, msg.name)

        self.checkpoint = self.ctx.socket(zmq.PUB)
        self.checkpoint.connect(checkpoint_addr)

        self.ctrlWidget = self.node.ctrlWidget()
        self.widget = None
        self.show = False

        self.win.setWindowTitle(msg.name)

        with loop:
            loop.run_until_complete(asyncio.gather(self.process(), self.monitor_node_task()))

    async def monitor_node_task(self):
        if hasattr(self.node, 'task'):
            while self.node.task is None:
                await asyncio.sleep(0.1)
            # await the node task so we can see any exceptions it raised
            try:
                await self.node.task
            except asyncio.CancelledError:
                # ignore cancelled errors just means the window was closed
                pass

    async def process(self):
        while True:
            await self.broker.recv_string()
            msg = await self.broker.recv_pyobj()

            if isinstance(msg, fcMsgs.DisplayNode):
                self.display(msg)
            elif isinstance(msg, fcMsgs.CloseNode):
                return

    def display(self, msg):
        if self.show and msg.redisplay:
            self.node.clear()
            self.widget = None

        if self.widget is None:
            self.widget = self.node.display(msg.topics, msg.terms, self.graphmgr_addr, self.win)

            if self.ctrlWidget and self.widget:
                cw = QtGui.QWidget()
                self.win.setCentralWidget(cw)
                layout = QtGui.QGridLayout()
                cw.setLayout(layout)
                layout.addWidget(self.ctrlWidget, 0, 0)
                layout.addWidget(self.widget, 0, 1, -1, -1)
                layout.setColumnStretch(1, 10)
                self.node.update()
            elif self.ctrlWidget:
                scrollarea = QtWidgets.QScrollArea()
                scrollarea.setWidget(self.ctrlWidget)
                self.win.setCentralWidget(scrollarea)
            elif self.widget:
                self.win.setCentralWidget(self.widget)

            if msg.state and hasattr(self.widget, 'restoreState'):
                self.widget.restoreState(msg.state)

            self.node.sigStateChanged.connect(self.send_checkpoint)

        if not msg.redisplay:
            if self.show:
                self.win.activateWindow()
            else:
                self.show = True
                self.win.show()

    @asyncSlot(object)
    async def send_checkpoint(self, node):
        state = node.saveState()
        state['viewed'] = self.show

        msg = fcMsgs.NodeCheckpoint(node.name(),
                                    state=state)
        await self.checkpoint.send_string(node.name(), zmq.SNDMORE)
        await self.checkpoint.send_pyobj(msg)


class MessageBroker(object):

    def __init__(self, graphmgr_addr, load, ipcdir=None):

        if ipcdir is None:
            ipcdir = tempfile.mkdtemp()

        self.graphmgr_addr = graphmgr_addr
        self.broker_sub_addr = "ipc://%s/broker_sub" % ipcdir
        self.broker_pub_addr = "ipc://%s/broker_pub" % ipcdir

        self.checkpoint_sub_addr = "ipc://%s/checkpoint_sub" % ipcdir
        self.checkpoint_pub_addr = "ipc://%s/checkpoint_pub" % ipcdir

        self.load = load

        self.lock = asyncio.Lock()
        self.msgs = {}
        self.checkpoints = {}
        self.widget_procs = {}
        self.editor = None

        self.ctx = zmq.asyncio.Context()

        self.broker_sub_sock = self.ctx.socket(zmq.SUB)                # receives messages from editor
        self.broker_sub_sock.setsockopt_string(zmq.SUBSCRIBE, '')
        self.broker_sub_sock.bind(self.broker_sub_addr)

        self.broker_pub_sock = self.ctx.socket(zmq.XPUB)               # sends messages to node process
        self.broker_pub_sock.bind(self.broker_pub_addr)

        self.checkpoint_sub_sock = self.ctx.socket(zmq.SUB)            # receives messages from node process
        self.checkpoint_sub_sock.setsockopt_string(zmq.SUBSCRIBE, '')
        self.checkpoint_sub_sock.bind(self.checkpoint_sub_addr)

        self.checkpoint_pub_sock = self.ctx.socket(zmq.PUB)            # sends messages to editor
        self.checkpoint_pub_sock.bind(self.checkpoint_pub_addr)

        self.profiler = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        for name, (node_type, proc) in self.widget_procs.items():
            logger.info("terminating widget proc %s of type %s", name, node_type)
            proc.terminate()
            proc.join()
            logger.info("terminated widget proc %s", name)
        if self.editor is not None:
            self.editor.terminate()
            self.editor.join()
        self.ctx.destroy()

    def launch_editor_window(self):
        editor_proc = mp.Process(
            target=run_editor_window,
            args=(self.broker_sub_addr,
                  self.graphmgr_addr,
                  self.checkpoint_pub_addr,
                  self.load),
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

                    state = {}
                    if name in self.checkpoints:
                        state = self.checkpoints[name].state

                    msg = fcMsgs.CreateNode(name, typ, state)

                    # don't resend last message
                    del self.msgs[msg.name]

                    proc = mp.Process(
                        target=NodeProcess,
                        args=(msg, self.broker_pub_addr, self.graphmgr_addr, self.checkpoint_sub_addr),
                        daemon=True
                    )
                    proc.start()
                    logger.info("restarting process: %s pid: %d", msg.name, proc.pid)
                    self.widget_procs[msg.name] = (msg.node_type, proc)

    async def process_messages(self):

        while True:
            topic = await self.broker_sub_sock.recv_string()
            msg = await self.broker_sub_sock.recv_pyobj()

            if isinstance(msg, fcMsgs.CreateNode):
                proc = mp.Process(
                    target=NodeProcess,
                    args=(msg, self.broker_pub_addr, self.graphmgr_addr, self.checkpoint_sub_addr),
                    daemon=True
                )
                proc.start()
                logger.info("creating process: %s pid: %d", msg.name, proc.pid)
                async with self.lock:
                    self.widget_procs[msg.name] = (msg.node_type, proc)

            elif isinstance(msg, fcMsgs.Profiler):
                if self.profiler is None:
                    self.profiler = mp.Process(target=Profiler,
                                               args=(self.broker_pub_addr, self.graphmgr_addr.profile, msg.name),
                                               daemon=True)
                    self.profiler.start()
                    logger.info("creating process: Profiler pid: %d", self.profiler.pid)

                async with self.lock:
                    self.msgs[topic] = msg

                await self.broker_pub_sock.send_string(topic, zmq.SNDMORE)
                await self.broker_pub_sock.send_pyobj(msg)

            elif isinstance(msg, fcMsgs.DisplayNode):
                await self.forward_message_to_node(topic, msg)

            elif isinstance(msg, fcMsgs.CloseNode):
                await self.forward_message_to_node(topic, msg)

                async with self.lock:
                    if topic in self.widget_procs:
                        logger.info("deleting process: %s pid: %d", topic, proc.pid)
                        _, proc = self.widget_procs[topic]
                        proc.terminate()
                        proc.join()
                        del self.widget_procs[topic]

                    if topic in self.msgs:
                        del self.msgs[topic]

    async def run(self):
        await asyncio.gather(self.handle_connect(),
                             self.handle_checkpoint(),
                             self.process_messages(),
                             self.monitor_processes())


def run_client(graphmgr_addr, load):
    with tempfile.TemporaryDirectory() as ipcdir:
        mb = MessageBroker(graphmgr_addr, load, ipcdir=ipcdir)
        mb.launch_editor_window()
        loop = asyncio.get_event_loop()
        task = asyncio.ensure_future(mb.run())

        # wait for the editor window to exit
        loop.run_until_complete(loop.run_in_executor(None, mb.wait_editor_exit))

        # if the message brokers task is still running cancel it
        if not task.done():
            task.cancel()
