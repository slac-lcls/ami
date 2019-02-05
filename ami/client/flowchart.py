#!/usr/bin/env python
import logging
import multiprocessing as mp
import time

from pyqtgraph.Qt import QtGui
from ami.flowchart.Flowchart import Flowchart

from ami.comm import GraphCommHandler


logger = logging.getLogger(__name__)


def run_main_window(queue, addr):
    app = QtGui.QApplication([])

    # Create main window with grid layout
    win = QtGui.QMainWindow()
    win.setWindowTitle('AMI Client')
    cw = QtGui.QWidget()
    win.setCentralWidget(cw)
    layout = QtGui.QGridLayout()
    cw.setLayout(layout)

    # TODO fix this
    time.sleep(2)
    comm = GraphCommHandler(addr)
    terminals = {}

    for name in comm.names:
        terminals[name] = {'io': 'in'}

    # Create flowchart, define input/output terminals
    fc = Flowchart(terminals=terminals, addr=addr)
    w = fc.widget()
    fw = w.chartWidget

    # Add flowchart control panel to the main window
    layout.addWidget(w, 0, 0, 2, 1)
    layout.addWidget(fw, 0, 1)

    win.show()
    retval = app.exec_()

    queue.put(("exit", None, None))
    return retval


def run_client(addr, load):

    queue = mp.Queue()
    list_proc = mp.Process(
        target=run_main_window, args=(queue, addr))
    list_proc.start()
