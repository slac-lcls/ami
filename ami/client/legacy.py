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
                            QVBoxLayout, QListWidget, QLCDNumber
from PyQt5.QtCore import pyqtSlot, pyqtSignal, QTimer, QRect

import pyqtgraph as pg

from ami import LogConfig
from ami.data import DataTypes
from ami.comm import AsyncGraphCommHandler


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
        self.comm_handler = AsyncGraphCommHandler(addr)
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
        self.comm_handler = AsyncGraphCommHandler(addr)
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
        self.comm_handler = AsyncGraphCommHandler(addr)
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
            self.plot = self.plot_view.plot(x=x, y=y, pen=None, symbol='o')
        else:
            self.plot.setData(x=x, y=y)


class AreaDetWidget(pg.ImageView):
    def __init__(self, name, topic, addr, parent=None):
        super(AreaDetWidget, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.comm_handler = AsyncGraphCommHandler(addr)
        self.timer = QTimer()
        self.timer.timeout.connect(self.get_image)
        self.timer.start(1000)
        self.roi.sigRegionChangeFinished.connect(self.roi_updated)

    @asyncqt.asyncSlot()
    async def get_image(self):
        reply = await self.comm_handler.fetch(self.topic)
        if reply is not None:
            self.image_updated(reply)
        else:
            logger.warn("failed to fetch %s from manager!", self.topic)

    def image_updated(self, data):
        self.setImage(data)

    # @pyqtSlot(pg.ROI)
    def roi_updated(self, roi):
        shape, vector, origin = roi.getAffineSliceParams(self.image, self.getImageItem())

        def roi_func(image):
            return pg.affineSlice(image, shape, origin, vector, (0, 1))

        self.comm_handler.map("map_%s_roi" % self.name,
                              inputs=[self.name],
                              outputs=["%s_roi" % self.name],
                              func=roi_func)


class Calculator(QWidget):
    def __init__(self, comm, parent=None):
        super(Calculator, self).__init__(parent)
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

        self.comm.map(name="map_%s_calc" % name,
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
        self.calc_id = "calculator"
        self.calc = None
        self.timer.timeout.connect(self.get_names)
        self.timer.start(1000)
        self.itemClicked.connect(self.item_clicked)
        return

    def spawn_window(self, data_type, name, topic):
        if data_type == DataTypes.Image:
            self._spawn_window('AreaDetector', name, topic)
            logger.info('create area detector window for: %s', name)
        elif data_type == DataTypes.Waveform:
            self._spawn_window('WaveformDetector', name, topic)
            logger.info('create waveform window for: %s', name)
        elif data_type == DataTypes.Histogram:
            self._spawn_window('HistogramDetector', name, topic)
            logger.info('create histogram window for: %s', name)
        elif data_type == DataTypes.Scalar:
            self._spawn_window('ScalarDetector', name, topic)
            logger.info('create waveform window for: %s', name)
        else:
            logger.error('Feature type %s is not supported', self.features[topic])

    @asyncqt.asyncSlot()
    async def get_names(self):
        # detectors = dict, maps name --> type
        self.names = sorted(await self.comm_handler.names)
        self.features = await self.comm_handler.features
        self.clear()
        self.addItem(self.calc_id)
        for k in self.names:
            if not k.startswith("_"):
                self.addItem(k)
        with self.pending_lock:
            done = []
            for topic, name in self.pending.items():
                if topic in self.features:
                    self.spawn_window(self.features[topic], name, topic)
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
            topic = name
        else:
            topic = self.comm_handler.auto(name)

        if name == self.calc_id:
            if self.calc is None:
                logger.info('create calculator widget')
                self.calc = Calculator(self.comm_handler)
            self.calc.show()
        elif topic in self.features:
            self.spawn_window(self.features[topic], name, topic)
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


class AmiGui(QWidget):

    loadfile = pyqtSignal(str)
    savefile = pyqtSignal(str)

    def __init__(self, queue, addr, ami_save, parent=None):
        super(__class__, self).__init__(parent)
        self.setWindowTitle("AMI Client")
        self.comm_handler = AsyncGraphCommHandler(addr)

        self.setupLabel = QLabel('Setup:', self)
        self.save_button = QPushButton('Save', self)
        self.save_button.clicked.connect(self.save)
        self.load_button = QPushButton('Load', self)
        self.load_button.clicked.connect(self.load)
        self.clear_button = QPushButton('Clear', self)
        self.clear_button.clicked.connect(self.clear)
        self.reset_button = QPushButton('Reset Plots', self)
        self.reset_button.clicked.connect(self.reset)
        self.dataLabel = QLabel('Data:', self)
        self.amilist = DetectorList(queue, self.comm_handler)
        if ami_save is not None:
            self.comm_handler.update(ami_save)

        self.setup = QWidget(self)
        self.setup_layout = QHBoxLayout(self.setup)
        self.setup_layout.addWidget(self.save_button)
        self.setup_layout.addWidget(self.load_button)
        self.setup_layout.addWidget(self.clear_button)

        self.ami_layout = QVBoxLayout(self)
        self.ami_layout.addWidget(self.setupLabel)
        self.ami_layout.addWidget(self.setup)
        self.ami_layout.addWidget(self.dataLabel)
        self.ami_layout.addWidget(self.reset_button)
        self.ami_layout.addWidget(self.amilist)

        self.loadfile.connect(self.load_async)
        self.savefile.connect(self.save_async)

    @pyqtSlot()
    def load(self):
        load_file = QFileDialog.getOpenFileName(
            self, "Open file", "", "AMI Autosave files (*.ami);;All Files (*)")
        if load_file[0]:
            logger.info("Loading graph configuration from file (%s)", load_file[0])
            self.loadfile.emit(load_file[0])

    @pyqtSlot()
    def save(self):
        save_file = QFileDialog.getSaveFileName(
            self, "Save file", "autosave.ami", "AMI Autosave files (*.ami);;All Files (*)")
        if save_file[0]:
            logger.info("Saving graph configuration to file (%s)", save_file[0])
            self.savefile.emit(save_file[0])

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


def run_main_window(queue, addr, ami_save):
    app = QApplication(sys.argv)
    loop = asyncqt.QEventLoop(app)
    asyncio.set_event_loop(loop)
    gui = AmiGui(queue, addr, ami_save)
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


def run_client(addr, load):
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
            queue, addr, saved_cfg))
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
                queue, window_type, name, topic, addr))
        proc.start()
        widget_procs.append(proc)
