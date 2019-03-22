#!/usr/bin/env python
import re
import sys
import dill
import logging
import asyncio
import asyncqt
import importlib
import threading
import numpy as np
import multiprocessing as mp

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QFileDialog, \
                            QApplication, QMainWindow, QPushButton, \
                            QLabel, QListWidgetItem, QLineEdit, \
                            QVBoxLayout, QListWidget, QLCDNumber, \
                            QGroupBox, QTabWidget, QPlainTextEdit
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QTimer, QRect, QThread

import pyqtgraph as pg

from ami import LogConfig
from ami.comm import AsyncGraphCommHandler, GraphInfoReceiver


logger = logging.getLogger(LogConfig.get_package_name(__name__))


class ScalarWidget(QLCDNumber):
    def __init__(self, name, topic, addr, parent=None):
        super(__class__, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.timer = QTimer()
        self.setGeometry(QRect(320, 180, 191, 81))
        self.setDigitCount(10)
        self.setObjectName(topic)
        self.comm_handler = AsyncGraphCommHandler(addr, False)
        self.timer.timeout.connect(self.get_scalar)
        self.timer.start(1000)

    @asyncqt.asyncSlot()
    async def get_scalar(self):
        reply = await self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.scalar_updated(reply)
        else:
            logger.warn("failed to fetch %s from manager!", self.topic)

    def scalar_updated(self, data):
        self.display(data)


class WaveformWidget(pg.GraphicsLayoutWidget):
    def __init__(self, name, topic, addr, parent=None):
        super(__class__, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.timer = QTimer()
        self.comm_handler = AsyncGraphCommHandler(addr, False)
        self.plot_view = self.addPlot()
        self.plot = None
        self.timer.timeout.connect(self.get_waveform)
        self.timer.start(1000)

    @asyncqt.asyncSlot()
    async def get_waveform(self):
        reply = await self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.waveform_updated(reply)
        else:
            logger.warn("failed to fetch %s from manager!", self.topic)

    def waveform_updated(self, data):
        if self.plot is None:
            self.plot = self.plot_view.plot(np.arange(data.size), data)
        else:
            self.plot.setData(y=data)


class HistogramWidget(pg.GraphicsLayoutWidget):
    def __init__(self, name, topic, addr, parent=None):
        super(__class__, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.timer = QTimer()
        self.comm_handler = AsyncGraphCommHandler(addr, False)
        self.plot_view = self.addPlot()
        self.plot = None
        self.timer.timeout.connect(self.get_waveform)
        self.timer.start(1000)

    @asyncqt.asyncSlot()
    async def get_waveform(self):
        reply = await self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.waveform_updated(reply)
        else:
            logger.warn("failed to fetch %s from manager!", self.topic)

    def waveform_updated(self, data):
        x, y = map(list, zip(*sorted(data.items())))
        if self.plot is None:
            self.plot = self.plot_view.plot(x=x, y=y, symbol='o')
        else:
            self.plot.setData(x=x, y=y)


class AreaDetWidget(pg.ImageView):

    roiUpdate = pyqtSignal(object, name='roiUpdate')

    def __init__(self, name, topic, addr, parent=None):
        super(AreaDetWidget, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.comm_handler = AsyncGraphCommHandler(addr, False)
        self.timer = QTimer()
        self.timer.timeout.connect(self.get_image)
        self.timer.start(1000)
        self.roi.sigRegionChangeFinished.connect(self.roi_updated)
        self.roiUpdate.connect(self.roi_updated_async)

    @asyncqt.asyncSlot()
    async def get_image(self):
        reply = await self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.image_updated(reply)
        else:
            logger.warn("failed to fetch %s from manager!", self.topic)

    def image_updated(self, data):
        self.setImage(data)

    @pyqtSlot(object)
    def roi_updated(self, roi):
        shape, vector, origin = roi.getAffineSliceParams(self.image, self.getImageItem())

        def roi_func(image):
            return pg.affineSlice(image, shape, origin, vector, (0, 1))

        self.roiUpdate.emit(roi_func)

    @asyncqt.asyncSlot(object)
    async def roi_updated_async(self, roi_func):
        await self.comm_handler.addMap("map_%s_roi" % self.name,
                                       inputs=[self.name],
                                       outputs=["%s_roi" % self.name],
                                       func=roi_func)


class TabPlot(QWidget):

    def __init__(self, idx, comm, plot_spawner, parent=None):
        super(__class__, self).__init__(parent)
        self.idx = idx
        self.comm = comm
        self.plot_spawner = plot_spawner

    async def make_plot(self, src, post):
        pass

    @asyncqt.asyncSlot(int, object, object)
    async def request_plot(self, idx, src, post):
        if idx == self.idx:
            info = await self.make_plot(src, post)
            if info is not None:
                data_type, name, topic = info
                self.plot_spawner(data_type, name, topic)


class TimePlot(TabPlot):

    def __init__(self, idx, comm, plot_spawner, parent=None):
        super(__class__, self).__init__(idx, comm, plot_spawner, parent)

    async def make_plot(self, src, post):
        if not post:
            name = '%s_vs_time' % src
            post = self.comm.auto(name)
        else:
            name = post
        await self.comm.addBinning(post+'_op', ['heartbeat', src], post)
        return 'HistogramDetector', name, post


class ScanPlot(TabPlot):

    def __init__(self, idx, comm, plot_spawner, parent=None):
        super(__class__, self).__init__(idx, comm, plot_spawner, parent)
        self.plotName = QLabel('Scan var', self)
        self.plotBox = QLineEdit(self)

        self.plot_layout = QHBoxLayout(self)
        self.plot_layout.addWidget(self.plotName)
        self.plot_layout.addWidget(self.plotBox)

    async def make_plot(self, src, post):
        key = self.plotBox.text()

        if key:
            if not post:
                name = '%s_vs_%s' % (src, key)
                post = self.comm.auto(name)
            else:
                name = post
            await self.comm.addBinning(post+'_op', [key, src], post)
            return 'HistogramDetector', name, post


class Env(QWidget):

    makePlot = pyqtSignal(int, object, object, name='makePlot')

    def __init__(self, comm, plot_spawner, parent=None):
        super(__class__, self).__init__(parent)
        self.setWindowTitle("Env")
        self.comm = comm

        self.srcBox = QLineEdit(self)
        self.srcSelect = QPushButton('Select', self)
        self.srcFilter = QPushButton('Filter', self)
        self.postName = QLabel('Entry name', self)
        self.postBox = QLineEdit(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(TimePlot(0, self.comm, plot_spawner, self.tabs), "Mean v Time")
        self.tabs.addTab(ScanPlot(1, self.comm, plot_spawner, self.tabs), "Mean v Scan")
        self.button = QPushButton('Plot', self)
        self.button.clicked.connect(self.on_click)

        self.src = QGroupBox("Source Channel")
        self.src_layout = QHBoxLayout(self.src)
        self.src_layout.addWidget(self.srcBox)
        self.src_layout.addWidget(self.srcSelect)
        self.src_layout.addWidget(self.srcFilter)

        self.post = QHBoxLayout()
        self.post.addWidget(self.postName)
        self.post.addWidget(self.postBox)

        self.plot = QGroupBox("Plot Type")
        self.plot_layout = QVBoxLayout(self.plot)
        self.plot_layout.addWidget(self.tabs)

        self.env_layout = QVBoxLayout(self)
        self.env_layout.addWidget(self.src)
        self.env_layout.addLayout(self.post)
        self.env_layout.addWidget(self.plot)
        self.env_layout.addWidget(self.button)

        for i in range(self.tabs.count()):
            self.makePlot.connect(self.tabs.widget(i).request_plot)

    @pyqtSlot()
    def on_click(self):
        src = self.srcBox.text()
        post = self.postBox.text()

        if src:
            self.makePlot.emit(self.tabs.currentIndex(), src, post)


class Calculator(QWidget):

    calcUpdated = pyqtSignal(str, object, object, name='calcUpdated')

    def __init__(self, comm, parent=None):
        super(__class__, self).__init__(parent)
        self.setWindowTitle("Calculator")
        self.comm = comm
        self.move(280, 80)
        self.resize(280, 40)
        self.field_parse = re.compile(r"\s+")
        self.alias_parse = re.compile(r"(?P<import>\w+),(?P<alias>\w+)")

        self.nameLabel = QLabel('Name:', self)
        self.nameBox = QLineEdit(self)
        self.inputsLabel = QLabel('Inputs:', self)
        self.inputsBox = QLineEdit(self)
        self.importsLabel = QLabel('Imports:', self)
        self.importsBox = QLineEdit(self)
        self.codeLabel = QLabel('Expression:', self)
        self.codeBox = QLineEdit(self)
        self.button = QPushButton('Apply', self)
        self.button.clicked.connect(self.on_click)

        self.calc_layout = QVBoxLayout(self)
        self.calc_layout.addWidget(self.nameLabel)
        self.calc_layout.addWidget(self.nameBox)
        self.calc_layout.addWidget(self.inputsLabel)
        self.calc_layout.addWidget(self.inputsBox)
        self.calc_layout.addWidget(self.importsLabel)
        self.calc_layout.addWidget(self.importsBox)
        self.calc_layout.addWidget(self.codeLabel)
        self.calc_layout.addWidget(self.codeBox)
        self.calc_layout.addWidget(self.button)
        self.setLayout(self.calc_layout)

        self.calcUpdated.connect(self.update_calc)

    def parse_inputs(self):
        if self.inputsBox.text():
            return self.field_parse.split(self.inputsBox.text())
        else:
            return []

    def parse_imports(self):
        imports = []
        if self.importsBox.text():
            for imp in self.field_parse.split(self.importsBox.text()):
                match = self.alias_parse.match(imp)
                if match:
                    imports.append((match.group("import"), match.group("alias")))
                else:
                    imports.append((imp, imp))
        return imports

    @pyqtSlot()
    def on_click(self):
        name = self.nameBox.text()
        inputs = self.parse_inputs()
        imports = self.parse_imports()
        code = self.codeBox.text()

        def calc_func(*args):
            loc = {}
            glb = {name: importlib.import_module(imp) for imp, name in imports}
            for k, v in zip(inputs, args):
                loc[k] = v
            return eval(code, glb, loc)

        self.calcUpdated.emit(name, inputs, calc_func)

    @asyncqt.asyncSlot(str, object, object)
    async def update_calc(self, name, inputs, calc_func):
        await self.comm.addMap(name="map_%s_calc" % name,
                               inputs=inputs,
                               outputs=[name],
                               func=calc_func)


class DetectorList(QListWidget):

    def __init__(self, queue, comm_handler, parent=None):
        super(__class__, self).__init__(parent)
        self.queue = queue
        self.comm_handler = comm_handler
        self.names = []
        self.pending = {}
        self.pending_lock = threading.Lock()
        self.features = {}
        self.timer = QTimer()
        self.calc_id = "Calculator"
        self.calc = None
        self.env_id = "Env"
        self.env = None
        self.timer.timeout.connect(self.get_names)
        self.timer.start(1000)
        self.itemClicked.connect(self.item_clicked)

    def spawn_window(self, window_type, name, topic):
        self.queue.put((window_type, name, topic))

    def window_type(self, data_type):
        if isinstance(data_type, tuple):
            data_type, ndims = data_type
            if issubclass(data_type, np.ndarray):
                if ndims == 1:
                    return 'WaveformDetector'
                elif ndims == 2:
                    return 'AreaDetector'
        elif issubclass(data_type, dict):
            return 'HistogramDetector'
        elif issubclass(data_type, (int, float)):
            return 'ScalarDetector'

    @asyncqt.asyncSlot()
    async def get_names(self):
        # detectors = dict, maps name --> type
        self.names = sorted(await self.comm_handler.names)
        self.features = await self.comm_handler.features
        self.clear()
        self.addItem(self.env_id)
        self.addItem(self.calc_id)
        for k in sorted(self.names):
            if not k.startswith("_"):
                self.addItem(k)
        with self.pending_lock:
            done = []
            for topic, name in self.pending.items():
                if topic in self.features:
                    window_type = self.window_type(self.features[topic])
                    if window_type is not None:
                        self.spawn_window(window_type, name, topic)
                        logger.info('create %s window for: %s', window_type, name)
                    else:
                        logger.error('Feature type %s is not supported', self.features[topic])
                    # append to list of done entries to delete after iterating
                    done.append(topic)
            for key in done:
                del self.pending[key]
        return

    @asyncqt.asyncSlot(QListWidgetItem)
    async def item_clicked(self, item):
        name = item.text()
        # Check if there is already data for the feature in the result store
        if name in self.features:
            need_view = False
            topic = name
        else:
            need_view = True
            topic = self.comm_handler.auto(name)

        if name == self.calc_id:
            if self.calc is None:
                logger.info('create calculator widget')
                self.calc = Calculator(self.comm_handler)
            self.calc.show()
        elif name == self.env_id:
            if self.env is None:
                logger.info('create env widget')
                self.env = Env(self.comm_handler, self.spawn_window)
            self.env.show()
        elif topic in self.features:
            window_type = self.window_type(self.features[topic])
            if window_type is not None:
                self.spawn_window(window_type, name, topic)
                logger.info('create %s window for: %s', window_type, name)
            else:
                logger.error('Feature type %s is not supported', self.features[topic])
            # check if a view needs to be re-added
            if need_view and topic not in self.names:
                await self.comm_handler.view(name)
        else:
            request_view = False
            with self.pending_lock:
                if topic not in self.pending:
                    self.pending[topic] = name
                    request_view = True
            if request_view:
                await self.comm_handler.view(name)

    def _spawn_window(self, window_type, name, topic):
        self.queue.put((window_type, name, topic))


class QtSignalLogHandler(logging.StreamHandler):

    def __init__(self, signal):
        super(__class__, self).__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)


class AmiInfo(QThread):

    sig = pyqtSignal(str, str)

    def __init__(self, addr, slot, parent=None):
        super(__class__, self).__init__(parent)
        self.info = GraphInfoReceiver(addr)
        self.sig.connect(slot)

    def run(self):
        for topic, msg in self.info.messages:
            self.sig.emit(topic, msg)


class AmiGui(QWidget):

    loadFile = pyqtSignal(str, name='loadFile')
    saveFile = pyqtSignal(str, name='saveFile')
    statusUpdate = pyqtSignal(str, name='statusUpdate')

    def __init__(self, queue, comm_addr, info_addr, ami_save, parent=None):
        super(__class__, self).__init__(parent)
        self.setWindowTitle("AMI Client")
        self.comm_handler = AsyncGraphCommHandler(comm_addr, False)

        self.save_button = QPushButton('Save', self)
        self.save_button.clicked.connect(self.save)
        self.load_button = QPushButton('Load', self)
        self.load_button.clicked.connect(self.load)
        self.clear_button = QPushButton('Clear', self)
        self.clear_button.clicked.connect(self.clear)
        self.reset_button = QPushButton('Reset Plots', self)
        self.reset_button.clicked.connect(self.reset)
        self.status_box = QPlainTextEdit(self)
        self.status_box.setReadOnly(True)
        self.amilist = DetectorList(queue, self.comm_handler)
        if ami_save is not None:
            self.comm_handler.update(ami_save)

        self.setup = QGroupBox("Setup")
        self.setup_layout = QHBoxLayout(self.setup)
        self.setup_layout.addWidget(self.save_button)
        self.setup_layout.addWidget(self.load_button)
        self.setup_layout.addWidget(self.clear_button)
        self.setup.setLayout(self.setup_layout)

        self.data = QGroupBox("Data")
        self.data_layout = QVBoxLayout(self)
        self.data_layout.addWidget(self.reset_button)
        self.data_layout.addWidget(self.amilist)
        self.data.setLayout(self.data_layout)

        self.status = QGroupBox("Status")
        self.status_layout = QVBoxLayout(self)
        self.status_layout.addWidget(self.status_box)
        self.status.setLayout(self.status_layout)

        self.ami_layout = QVBoxLayout(self)
        self.ami_layout.addWidget(self.setup, 1)
        self.ami_layout.addWidget(self.data, 4)
        self.ami_layout.addWidget(self.status, 2)

        self.loadFile.connect(self.load_async)
        self.saveFile.connect(self.save_async)
        self.statusUpdate.connect(self.status_box.appendPlainText)

        # the status box to logging
        add_logging_handler(self.statusUpdate)

        # create a qthread that listens for info messages from the cluster to log them.
        self.info_thread = AmiInfo(info_addr, self.log_message)
        self.info_thread.start()

    @pyqtSlot(str, str)
    def log_message(self, topic, msg):
        # see if the topic name is a log level then use that otherwise use info
        log_func = getattr(logger, topic, 'info')
        log_func(msg)

    @pyqtSlot()
    def load(self):
        load_file = QFileDialog.getOpenFileName(
            self, "Open file", "", "AMI Autosave files (*.ami);;All Files (*)")
        if load_file[0]:
            logger.info("Loading graph configuration from file (%s)", load_file[0])
            self.loadFile.emit(load_file[0])

    @pyqtSlot()
    def save(self):
        save_file = QFileDialog.getSaveFileName(
            self, "Save file", "autosave.ami", "AMI Autosave files (*.ami);;All Files (*)")
        if save_file[0]:
            logger.info("Saving graph configuration to file (%s)", save_file[0])
            self.saveFile.emit(save_file[0])

    @asyncqt.asyncSlot()
    async def reset(self):
        if not (await self.comm_handler.reset()):
            logger.error("Unable to reset feature store of the manager!")

    @asyncqt.asyncSlot()
    async def clear(self):
        if not (await self.comm_handler.clear()):
            logger.error("Unable to clear the graph configuration of the manager!")

    @asyncqt.asyncSlot(str)
    async def load_async(self, filename):
        await self.comm_handler.load(filename)

    @asyncqt.asyncSlot(str)
    async def save_async(self, filename):
        await self.comm_handler.save(filename)


def add_logging_handler(signal):
    logger.addHandler(QtSignalLogHandler(signal))


def run_main_window(queue, comm_addr, info_addr, ami_save):
    app = QApplication(sys.argv)
    loop = asyncqt.QEventLoop(app)
    asyncio.set_event_loop(loop)
    gui = AmiGui(queue, comm_addr, info_addr, ami_save)
    gui.show()

    # wait for the qt app to exit
    retval = app.exec_()

    # send exit signal to master process
    queue.put(("exit", None, None))

    return retval


def run_widget(queue, window_type, name, topic, addr):

    app = QApplication(sys.argv)
    loop = asyncqt.QEventLoop(app)
    asyncio.set_event_loop(loop)
    win = QMainWindow()

    if window_type == 'AreaDetector':
        widget = AreaDetWidget(name, topic, addr, win)

    elif window_type == 'WaveformDetector':
        widget = WaveformWidget(name, topic, addr, win)

    elif window_type == 'HistogramDetector':
        widget = HistogramWidget(name, topic, addr, win)

    elif window_type == 'ScalarDetector':
        widget = ScalarWidget(name, topic, addr, win)

    else:
        raise ValueError('%s not valid window_type' % window_type)

    win.setCentralWidget(widget)
    win.setWindowTitle(name)
    win.show()

    return app.exec_()


def run_client(comm_addr, info_addr, load):
    saved_cfg = None
    if load is not None:
        try:
            with open(load, 'rb') as cnf:
                saved_cfg = dill.load(cnf)
        except OSError:
            logger.exception("ami-client: problem opening saved graph configuration file:")
            return 1
        except dill.UnpicklingError:
            logger.exception("ami-client: problem parsing saved graph configuration file (%s):", load)
            return 1

    queue = mp.Queue()
    list_proc = mp.Process(
        target=run_main_window, args=(
            queue, comm_addr, info_addr, saved_cfg))
    list_proc.start()
    widget_procs = []

    while True:
        window_type, name, topic = queue.get()
        if window_type == 'exit':
            logger.info("received exit signal - exiting!")
            break
        logger.debug("opening new widget: %s %s %s", window_type, name, topic)
        proc = mp.Process(
            target=run_widget, args=(
                queue, window_type, name, topic, comm_addr))
        proc.start()
        widget_procs.append(proc)
