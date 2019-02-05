#!/usr/bin/env python
import logging
import argparse
import sys
import multiprocessing as mp
import time

from pyqtgraph.Qt import QtGui
from ami.flowchart.Flowchart import Flowchart

from ami import LogConfig
from ami.comm import Ports, GraphCommHandler


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


def main():
    parser = argparse.ArgumentParser(description='AMII GUI Client')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: 127.0.0.1)'
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.Comm,
        help='port for manager/client (GUI) communication (default: %d)' % Ports.Comm
    )

    # parser.add_argument(
    #     '-l',
    #     '--load',
    #     help='saved AMII configuration to load'
    # )

    parser.add_argument(
        '--log-level',
        default=LogConfig.Level,
        help='the logging level of the application (default %s)' % LogConfig.Level
    )

    parser.add_argument(
        '--log-file',
        help='an optional file to write the log output to'
    )

    args = parser.parse_args()
    addr = "tcp://%s:%d" % (args.host, args.port)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        return run_client(addr, args.load)
    except KeyboardInterrupt:
        logger.info("Client killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
