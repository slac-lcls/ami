#!/usr/bin/env python
import re
import zmq
import sys
import dill
import json
import argparse
import importlib
import threading
import numpy as np
import multiprocessing as mp

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QFileDialog, \
                            QApplication, QMainWindow, QPushButton, \
                            QLabel, QListWidgetItem, QLineEdit, \
                            QVBoxLayout, QListWidget, QLCDNumber
from PyQt5.QtCore import pyqtSlot, QTimer, QRect

import pyqtgraph as pg

from ami.graphkit_wrapper import Map, PickN
from ami.data import DataTypes
from ami.comm import Ports


class CommunicationHandler(object):

    def __init__(self, addr):
        self.ctx = zmq.Context()
        self.addr = addr
        self.sock = self.ctx.socket(zmq.REQ)
        self.sock.connect(self.addr)

    @property
    def graph(self):
        self.sock.send_string('get_graph')
        return self.sock.recv_pyobj()

    @property
    def features(self):
        self.sock.send_string('get_features')
        return self.sock.recv_pyobj()

    @property
    def types(self):
        self.sock.send_string('get_types')
        return self.sock.recv_pyobj()

    def edit(self, cmd, node):
        self.sock.send_string('%s_graph' % cmd, zmq.SNDMORE)
        self.sock.send(dill.dumps(node))
        return self.sock.recv_string() == 'ok'

    def pickN(self, name, inputs, outputs):
        node = PickN(name=name, inputs=inputs, outputs=outputs)
        return self.edit("add", node)

    def clear(self):
        self.sock.send_string('clear_graph')
        return self.sock.recv_string() == 'ok'

    def reset(self):
        self.sock.send_string('reset_features')
        return self.sock.recv_string() == 'ok'

    def update(self, graph):
        self.sock.send_string('set_graph', zmq.SNDMORE)
        self.sock.send(dill.dumps(graph))
        return self.sock.recv_string() == 'ok'


class ScalarWidget(QLCDNumber):
    def __init__(self, name, topic, addr, parent=None):
        super(__class__, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.timer = QTimer()
        self.setGeometry(QRect(320, 180, 191, 81))
        self.setDigitCount(10)
        self.setObjectName(topic)
        self.comm_handler = CommunicationHandler(addr)
        self.timer.timeout.connect(self.get_scalar)
        self.timer.start(1000)

    @pyqtSlot()
    def get_scalar(self):
        self.comm_handler.sock.send_string("feature:%s" % self.topic)
        reply = self.comm_handler.sock.recv_string()
        if reply == 'ok':
            self.scalar_updated(self.comm_handler.sock.recv_pyobj())
        else:
            print("failed to fetch %s from manager!" % self.topic)

    def scalar_updated(self, data):
        self.display(data)


class WaveformWidget(pg.GraphicsLayoutWidget):
    def __init__(self, name, topic, addr, parent=None):
        super(__class__, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.timer = QTimer()
        self.comm_handler = CommunicationHandler(addr)
        self.plot_view = self.addPlot()
        self.plot = None
        self.timer.timeout.connect(self.get_waveform)
        self.timer.start(1000)

    @pyqtSlot()
    def get_waveform(self):
        self.comm_handler.sock.send_string("feature:%s" % self.topic)
        reply = self.comm_handler.sock.recv_string()
        if reply == 'ok':
            self.waveform_updated(self.comm_handler.sock.recv_pyobj())
        else:
            print("failed to fetch %s from manager!" % self.topic)

    def waveform_updated(self, data):
        if self.plot is None:
            self.plot = self.plot_view.plot(np.arange(data.size), data)
        else:
            self.plot.setData(y=data)


class AreaDetWidget(pg.ImageView):
    def __init__(self, name, topic, addr, parent=None):
        super(AreaDetWidget, self).__init__(parent)
        self.name = name
        self.topic = topic
        self.comm_handler = CommunicationHandler(addr)
        self.timer = QTimer()
        self.timer.timeout.connect(self.get_image)
        self.timer.start(1000)
        self.roi.sigRegionChangeFinished.connect(self.roi_updated)

    @pyqtSlot()
    def get_image(self):
        self.comm_handler.sock.send_string("feature:%s" % self.topic)
        reply = self.comm_handler.sock.recv_string()
        if reply == 'ok':
            self.image_updated(self.comm_handler.sock.recv_pyobj())
        else:
            print("failed to fetch %s from manager!" % self.topic)

    def image_updated(self, data):
        self.setImage(data)

    # @pyqtSlot(pg.ROI)
    def roi_updated(self, roi):
        shape, vector, origin = roi.getAffineSliceParams(self.image, self.getImageItem())

        def roi_func(image):
            return pg.affineSlice(image, shape, origin, vector, (0, 1))

        roi_map = Map(name="map_%s_roi" % self.name, inputs=[self.name], outputs=["%s_roi" % self.name], func=roi_func)
        self.comm_handler.edit("add", roi_map)


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

        calc_map = Map(name="map_%s_calc" % name,
                       inputs=inputs,
                       outputs=[name],
                       func=calc_func)
        self.comm.edit("add", calc_map)


class DetectorList(QListWidget):

    def __init__(self, queue, comm_handler, parent=None):
        super(__class__, self).__init__(parent)
        self.queue = queue
        self.comm_handler = comm_handler
        self.features = []
        self.pending = {}
        self.pending_lock = threading.Lock()
        self.types = {}
        self.timer = QTimer()
        self.calc_id = "calculator"
        self.calc = None
        self.timer.timeout.connect(self.get_features)
        self.timer.start(1000)
        self.itemClicked.connect(self.item_clicked)
        return

    def load(self, graph_cfg):
        self.comm_handler.update(graph_cfg)

    def spawn_window(self, data_type, name, topic):
        if data_type == DataTypes.Image:
            self._spawn_window('AreaDetector', name, topic)
            print('create area detector window for:', name)
        elif data_type == DataTypes.Waveform:
            self._spawn_window('WaveformDetector', name, topic)
            print('create waveform window for:', name)
        elif data_type == DataTypes.Scalar:
            self._spawn_window('ScalarDetector', name, topic)
            print('create waveform window for:', name)
        else:
            print('Type %s not valid' % self.types[topic])

    @pyqtSlot()
    def get_features(self):
        # detectors = dict, maps name --> type
        self.features = self.comm_handler.features
        self.types = self.comm_handler.types
        self.clear()
        self.addItem(self.calc_id)
        for k in self.features:
            if not k.startswith("_"):
                self.addItem(k)
        with self.pending_lock:
            done = []
            for topic, name in self.pending.items():
                if topic in self.types:
                    self.spawn_window(self.types[topic], name, topic)
                    # append to list of done entries to delete after iterating
                    done.append(topic)
            for key in done:
                del self.pending[key]
        return

    @pyqtSlot(QListWidgetItem)
    def item_clicked(self, item):

        name = item.text()
        topic = '_auto_%s' % name

        if name == self.calc_id:
            if self.calc is None:
                print('create calculator widget')
                self.calc = Calculator(self.comm_handler)
            self.calc.show()
        elif topic in self.types:
            self.spawn_window(self.types[topic], name, topic)
        else:
            request_pickn = False
            with self.pending_lock:
                if topic not in self.pending:
                    self.pending[topic] = name
                    request_pickn = True
            if request_pickn:
                self.comm_handler.pickN(name='%s_pick1' % name,
                                        inputs=[name],
                                        outputs=[topic])

        return

    def _spawn_window(self, window_type, name, topic):
        self.queue.put((window_type, name, topic))


class AmiGui(QWidget):
    def __init__(self, queue, addr, ami_save, parent=None):
        super(__class__, self).__init__(parent)
        self.setWindowTitle("AMI Client")
        self.comm_handler = CommunicationHandler(addr)

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
            self.amilist.load(ami_save)

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

    @pyqtSlot()
    def load(self):
        load_file = QFileDialog.getOpenFileName(
            self, "Open file", "", "AMI Autosave files (*.ami);;All Files (*)")
        if load_file[0]:
            try:
                with open(load_file[0], 'rb') as cnf:
                    self.amilist.load(dill.load(cnf))
            except OSError as os_exp:
                print(
                    "ami-client: problem opening saved graph configuration file:",
                    os_exp)
            except dill.UnpicklingError as dill_exp:
                print(
                    "ami-client: problem parsing saved graph configuration file (%s):" %
                    load_file[0], dill_exp)

    @pyqtSlot()
    def save(self):
        save_file = QFileDialog.getSaveFileName(
            self, "Save file", "autosave.ami", "AMI Autosave files (*.ami);;All Files (*)")
        if save_file[0]:
            print(
                "ami-client: saving graph configuration to file (%s)" %
                save_file[0])
            try:
                with open(save_file[0], 'wb') as cnf:
                    dill.dump(self.comm_handler.graph, cnf)
            except OSError as os_exp:
                print(
                    "ami-client: problem opening saved graph configuration file:",
                    os_exp)

    @pyqtSlot()
    def reset(self):
        if not self.comm_handler.reset():
            print("ami-client: unable to reset feature store of the manager!")

    @pyqtSlot()
    def clear(self):
        if not self.comm_handler.clear():
            print("ami-client: unable to clear the graph configuration of the manager!")


def run_main_window(queue, addr, ami_save):
    app = QApplication(sys.argv)
    gui = AmiGui(queue, addr, ami_save)
    gui.show()

    # wait for the qt app to exit
    retval = app.exec_()

    # send exit signal to master process
    queue.put(("exit", None, None))

    return retval


def run_widget(queue, window_type, name, topic, addr):

    app = QApplication(sys.argv)
    win = QMainWindow()

    if window_type == 'AreaDetector':
        widget = AreaDetWidget(name, topic, addr, win)

    elif window_type == 'WaveformDetector':
        widget = WaveformWidget(name, topic, addr, win)

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
            with open(load, 'r') as cnf:
                saved_cfg = json.load(cnf)
        except OSError as os_exp:
            print(
                "ami-client: problem opening saved graph configuration file:",
                os_exp)
            return 1
        except json.decoder.JSONDecodeError as json_exp:
            print(
                "ami-client: problem parsing saved graph configuration file (%s):" %
                load, json_exp)
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
            print("received exit signal - exiting!")
            break
        print("opening new widget:", window_type, name, topic)
        proc = mp.Process(
            target=run_widget, args=(
                queue, window_type, name, topic, addr))
        proc.start()
        widget_procs.append(proc)


def main():
    parser = argparse.ArgumentParser(description='AMII GUI Client')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: localhost)'
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.Comm,
        help='port for manager/client (GUI) communication (default: %d)' % Ports.Comm
    )

    parser.add_argument(
        '-l',
        '--load',
        help='saved AMII configuration to load'
    )

    args = parser.parse_args()
    addr = "tcp://%s:%d" % (args.host, args.port)

    try:
        return run_client(addr, args.load)
    except KeyboardInterrupt:
        print("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
