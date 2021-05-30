#!/usr/bin/env python
import os
import sys
import logging
import importlib
import tempfile
import asyncio
import zmq
import zmq.asyncio
import subprocess
import ami.multiproc as mp
import pyqtgraph as pg

from ami import LogConfig
from ami.client import flowchart_messages as fcMsgs
from ami.comm import ZMQ_TOPIC_DELIM
from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.library import LIBRARY
from ami.flowchart.NodeLibrary import isNodeClass
from ami.flowchart.library.common import SourceNode
from ami.asyncqt import QEventLoop, asyncSlot
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets


logger = logging.getLogger(LogConfig.get_package_name(__name__))


def run_editor_window(broker_addr, graphmgr_addr, checkpoint_addr, load=None, prometheus_dir=None,
                      prometheus_port=None, hutch=None, configure=False):
    subprocess.call(["dmypy", "start"])
    check_file = None
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("from typing import *\n")
        f.write("from mypy_extensions import TypedDict\n")
        f.write("import numbers\n")
        f.write("import amitypes\n")
        f.write("T = TypeVar('T')\n")
        f.flush()
        check_file = f.name
        proc = subprocess.Popen(["dmypy", "check", f.name])

    app = QtGui.QApplication([])

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create main window with grid layout
    win = QtGui.QMainWindow()
    title = 'AMI Client'
    if hutch:
        title += f' hutch: {hutch}'
    win.setWindowTitle(title)

    # Create flowchart, define input/output terminals
    fc = Flowchart(broker_addr=broker_addr,
                   graphmgr_addr=graphmgr_addr,
                   checkpoint_addr=checkpoint_addr,
                   prometheus_dir=prometheus_dir, hutch=hutch,
                   configure=configure)

    fc.start_prometheus(prometheus_port)

    def update_title(filename):
        title = 'AMI Client'
        if hutch:
            title += f' hutch: {hutch}'
        if filename:
            title += ' - ' + filename.split('/')[-1]

        win.setWindowTitle(title)

    fc.sigFileLoaded.connect(update_title)
    fc.sigFileSaved.connect(update_title)

    loop.run_until_complete(fc.updateSources(init=True))

    # Add flowchart control panel to the main window
    win.setCentralWidget(fc.widget())
    win.show()

    try:
        task = asyncio.create_task(fc.run(load))
        loop.run_forever()
    finally:
        if not task.done():
            loop.run_until_complete(fc.widget().clear())
            task.cancel()
        loop.close()

    try:
        proc.communicate(timeout=1)
        subprocess.call(["dmypy", "stop"])
    except subprocess.TimeoutExpired:
        proc.terminate()
        subprocess.call(["dmypy", "kill"])
    finally:
        if check_file:
            os.remove(check_file)


class NodeWindow(QtGui.QMainWindow):

    def __init__(self, proc, parent=None):
        super().__init__(parent)
        self.proc = proc

    def moveEvent(self, event):
        super().moveEvent(event)
        self.proc.node.geometry = self.saveGeometry()
        self.proc.send_checkpoint(self.proc.node)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.proc.node.geometry = self.saveGeometry()
        self.proc.send_checkpoint(self.proc.node)

    def closeEvent(self, event):
        self.proc.node.viewed = False
        self.proc.node.geometry = self.saveGeometry()
        self.proc.send_checkpoint(self.proc.node)
        self.proc.node.close()
        self.proc.widget = None
        self.destroy()
        event.ignore()


class NodeProcess(QtCore.QObject):

    def __init__(self, msg, broker_addr="", graphmgr_addr="", checkpoint_addr="", loop=None,
                 library_paths=None, hutch=''):
        super().__init__()

        if loop is None:
            self.app = QtGui.QApplication([])
            loop = QEventLoop(self.app)

        asyncio.set_event_loop(loop)

        self.win = NodeWindow(self)
        self.win.resize(800, 800)

        if msg.node_type == "SourceNode":
            self.node = SourceNode(name=msg.name)
        else:
            if library_paths:
                dirs = set(map(os.path.dirname, library_paths))
                sys.path.extend(dirs)

                for mod in library_paths:
                    mod = os.path.basename(mod)
                    mod = os.path.splitext(mod)[0]
                    mod = importlib.import_module(mod)

                    nodes = [getattr(mod, name) for name in dir(mod) if isNodeClass(getattr(mod, name))]

                    for node in nodes:
                        LIBRARY.addNodeType(node, [(mod.__name__, )])

            self.node = LIBRARY.getNodeType(msg.node_type)(msg.name)

        self.node.restoreState(msg.state)
        self.graphmgr_addr = graphmgr_addr
        self.ctx = zmq.asyncio.Context()

        self.broker = self.ctx.socket(zmq.SUB)
        self.broker.connect(broker_addr)
        self.broker.setsockopt_string(zmq.SUBSCRIBE, msg.name + ZMQ_TOPIC_DELIM)

        self.checkpoint = self.ctx.socket(zmq.PUB)
        self.checkpoint.connect(checkpoint_addr)

        self.ctrlWidget = self.node.ctrlWidget(self.win)
        self.widget = None

        title = msg.name
        if hutch:
            title += f' hutch: {hutch}'
        self.win.setWindowTitle(title)

        with loop:
            loop.run_until_complete(self.process())

    async def process(self):
        while True:
            await self.broker.recv_string()
            msg = await self.broker.recv_pyobj()

            if isinstance(msg, fcMsgs.DisplayNode):
                self.display(msg)
            elif isinstance(msg, fcMsgs.ReloadLibrary):
                self.reloadLibrary(msg)
            elif isinstance(msg, fcMsgs.CloseNode):
                return

    def display(self, msg):
        if self.node.viewed and msg.redisplay:
            self.node.close()
            self.widget = None

        if msg.geometry:
            self.win.restoreGeometry(msg.geometry)

        if self.widget is None:
            self.widget = self.node.display(msg.topics, msg.terms, self.graphmgr_addr, self.win,
                                            units=msg.units)

            if self.ctrlWidget and self.widget:
                splitter = QtWidgets.QSplitter(parent=self.win)
                splitter.addWidget(self.ctrlWidget)
                splitter.addWidget(self.widget)
                splitter.setStretchFactor(1, 10)
                self.win.setCentralWidget(splitter)
                self.ctrlWidget.setParent(splitter)
                self.widget.setParent(splitter)
            elif self.ctrlWidget:
                scrollarea = QtWidgets.QScrollArea(parent=self.win)
                scrollarea.setWidget(self.ctrlWidget)
                self.ctrlWidget.setParent(scrollarea)
                self.win.setCentralWidget(scrollarea)
            elif self.widget:
                scrollarea = QtWidgets.QScrollArea(parent=self.win)
                scrollarea.setWidgetResizable(True)
                scrollarea.setWidget(self.widget)
                self.widget.setParent(scrollarea)
                self.win.setCentralWidget(scrollarea)

            if msg.state and hasattr(self.widget, 'restoreState'):
                self.widget.restoreState(msg.state)

            self.node.sigStateChanged.connect(self.send_checkpoint)

        self.win.show()
        if self.node.viewed:
            self.win.activateWindow()
        self.node.viewed = True

    def reloadLibrary(self, msg):
        for mod in msg.mods:
            mod = sys.modules[mod]
            pg.reload.reload(mod)

    @asyncSlot(object)
    async def send_checkpoint(self, node):
        state = node.saveState()

        msg = fcMsgs.NodeCheckpoint(node.name(),
                                    state=state)
        await self.checkpoint.send_string(node.name() + ZMQ_TOPIC_DELIM, zmq.SNDMORE)
        await self.checkpoint.send_pyobj(msg)


class MessageBroker(object):

    def __init__(self, graphmgr_addr, load, ipcdir=None, prometheus_dir=None, prometheus_port=None, hutch=""):

        if ipcdir is None:
            ipcdir = tempfile.mkdtemp()

        self.graphmgr_addr = graphmgr_addr
        self.broker_sub_addr = "ipc://%s/broker_sub" % ipcdir
        self.broker_pub_addr = "ipc://%s/broker_pub" % ipcdir

        self.checkpoint_sub_addr = "ipc://%s/checkpoint_sub" % ipcdir
        self.checkpoint_pub_addr = "ipc://%s/checkpoint_pub" % ipcdir

        self.load = load
        self.library_paths = set()

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

        self.prometheus_dir = prometheus_dir
        self.prometheus_port = prometheus_port
        self.hutch = hutch

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

    def launch_editor_window(self, configure):
        editor_proc = mp.Process(
            name='editor',
            target=run_editor_window,
            args=(self.broker_sub_addr,
                  self.graphmgr_addr,
                  self.checkpoint_pub_addr,
                  self.load,
                  self.prometheus_dir,
                  self.prometheus_port,
                  self.hutch,
                  configure),
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
                topic = topic.rstrip(ZMQ_TOPIC_DELIM)
                async with self.lock:
                    if topic in self.msgs:
                        msg = self.msgs[topic]
                        self.broker_pub_sock.send_string(topic + ZMQ_TOPIC_DELIM, zmq.SNDMORE)
                        self.broker_pub_sock.send_pyobj(msg)
                    else:
                        continue

    async def handle_checkpoint(self):

        while True:
            topic = await self.checkpoint_sub_sock.recv_string()
            topic = topic.rstrip(ZMQ_TOPIC_DELIM)
            msg = await self.checkpoint_sub_sock.recv_pyobj()

            async with self.lock:
                self.checkpoints[topic] = msg

            await self.checkpoint_pub_sock.send_string(topic + ZMQ_TOPIC_DELIM)
            await self.checkpoint_pub_sock.send_pyobj(msg)

    async def forward_message_to_node(self, topic, msg):

        if isinstance(msg, fcMsgs.NodeMsg):

            async with self.lock:
                self.msgs[topic] = msg

            await self.broker_pub_sock.send_string(topic + ZMQ_TOPIC_DELIM, zmq.SNDMORE)
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

                    if type(self.msgs[msg.name]) is fcMsgs.DisplayNode and state:
                        self.msgs[msg.name].state = state['widget']
                    else:
                        # don't resend last message
                        del self.msgs[msg.name]

                    proc = mp.Process(
                        target=NodeProcess,
                        name=msg.name,
                        args=(msg, self.broker_pub_addr, self.graphmgr_addr, self.checkpoint_sub_addr),
                        kwargs={'library_paths': self.library_paths},
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
                    name=msg.name,
                    args=(msg, self.broker_pub_addr, self.graphmgr_addr, self.checkpoint_sub_addr),
                    kwargs={'library_paths': self.library_paths, 'hutch': self.hutch},
                    daemon=True
                )
                proc.start()
                logger.info("creating process: %s pid: %d", msg.name, proc.pid)
                async with self.lock:
                    self.widget_procs[msg.name] = (msg.node_type, proc)

            elif isinstance(msg, fcMsgs.DisplayNode):
                await self.forward_message_to_node(topic, msg)

            elif isinstance(msg, fcMsgs.ReloadLibrary):
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

            elif isinstance(msg, fcMsgs.Library):
                self.library_paths.update(msg.paths)

    async def run(self):
        asyncio.create_task(self.handle_connect())
        asyncio.create_task(self.handle_checkpoint())
        asyncio.create_task(self.process_messages())
        asyncio.create_task(self.monitor_processes())


def run_client(graphmgr_addr, load, prometheus_dir, prometheus_port, hutch, use_opengl, configure):
    use_opengl = use_opengl and "SSH_CONNECTION" not in os.environ
    pg.setConfigOptions(useOpenGL=use_opengl, enableExperimental=use_opengl)

    with tempfile.TemporaryDirectory() as ipcdir:
        mb = MessageBroker(graphmgr_addr, load, ipcdir=ipcdir, prometheus_dir=prometheus_dir,
                           prometheus_port=prometheus_port, hutch=hutch)
        mb.launch_editor_window(configure)
        loop = asyncio.get_event_loop()
        task = asyncio.ensure_future(mb.run())

        # wait for the editor window to exit
        loop.run_until_complete(loop.run_in_executor(None, mb.wait_editor_exit))

        # if the message brokers task is still running cancel it
        if not task.done():
            task.cancel()
