import pytest
import dill
import json
import shutil
import subprocess
import signal
import multiprocessing as mp
import numpy as np
try:
    import psana
except ImportError:
    psana = None

from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, FilterOn, FilterOff, Binning, PickN, Var
from ami.local import build_parser, run_ami
from ami.comm import Ports, GraphCommHandler


@pytest.fixture(scope='session')
def use_psana():
    return psana is not None


@pytest.fixture(scope='session')
def ipc_dir(tmpdir_factory):
    return tmpdir_factory.mktemp("ipc_tests", False)


@pytest.fixture(scope='session')
def complex_graph_file(tmpdir_factory):
    graph = Graph(name='graph')

    def roi(cspad):
        return cspad[:100, :100]

    graph.add(Map(name='Roi',
                  inputs=[Var(name='cspad', type=np.ndarray)],
                  outputs=[Var(name='roi', type=np.ndarray)],
                  func=roi))

    graph.add(Map(name='Sum',
                  inputs=[Var(name='roi', type=np.ndarray)],
                  outputs=[Var(name='sum', type=np.float64)],
                  func=np.sum))

    graph.add(FilterOn(name='FilterOn',
                       condition_needs=['laser'],
                       outputs=['laseron']))

    graph.add(Binning(name='BinningOn',
                      condition_needs=['laseron'],
                      inputs=[Var(name='delta_t', type=int), Var(name='sum', type=np.float64)],
                      outputs=[Var(name='signal', type=dict)]))

    graph.add(FilterOff(name='FilterOff',
                        condition_needs=['laser'],
                        outputs=['laseroff']))

    graph.add(Binning(name='BinningOff',
                      condition_needs=['laseroff'],
                      inputs=[Var('delta_t', type=int), Var(name='sum', type=np.float64)],
                      outputs=[Var(name='reference', type=dict)]))

    fname = tmpdir_factory.mktemp("complex_graph", False).join("complex_graph.dill")

    with open(fname, 'wb') as fd:
        dill.dump(graph, fd)
    return fname


@pytest.fixture(scope='session')
def psana_graph(tmpdir_factory):
    graph = Graph(name='graph')
    graph.add(PickN(name='picker',
                    inputs=[Var(name='xppcspad:raw:image', type=np.ndarray)],
                    outputs=[Var(name='picked', type=np.ndarray)]))
    fname = tmpdir_factory.mktemp("psana_graph", False).join("psana_graph.dill")
    with open(fname, 'wb') as fd:
        dill.dump(graph, fd)
    return fname


@pytest.fixture(scope='session')
def xtcwriter(tmpdir_factory):
    if shutil.which('xtcwriter') is not None:
        fname = tmpdir_factory.mktemp("xtcs", False).join('data.xtc2')
        p = subprocess.run(['xtcwriter', '-f', fname], stdout=subprocess.PIPE)
        if p.returncode == 0:
            return fname


@pytest.fixture(scope='session')
def workerjson(tmpdir_factory, xtcwriter):

    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": 100,
        "filename": "data.xtc2" if xtcwriter is None else str(xtcwriter),
        "config": {
            "delta_t": {"dtype": "Scalar", "range": [0, 10], "integer": True},
            "cspad": {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]},
            "laser": {"dtype": "Scalar", "range": [0, 2], "integer": True},
        },
    }

    fname = tmpdir_factory.mktemp("worker_config", False).join('worker.json')
    with open(fname, 'w') as fd:
        json.dump(cfg, fd)
    return fname


@pytest.fixture(scope='function')
def complex_graph(complex_graph_file):
    with open(complex_graph_file, 'rb') as fd:
        return dill.load(fd)


@pytest.fixture(scope='function')
def start_ami(request, workerjson, use_psana):

    # don't run the fixture if psana is not installed
    if not use_psana and request.param == "psana":
        yield None
        return

    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-t', '--headless',
                              '%s://%s' %
                              (request.param, workerjson)])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    host = "127.0.0.1"
    comm_addr = "tcp://%s:%d" % (host, Ports.Comm)
    comm_handler = GraphCommHandler(comm_addr)

    yield comm_handler

    queue.put(None)
    ami.join()

    if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
        print('AMI exited successfully')
    else:
        print('AMI exited with non-zero status code: %d' % ami.exitcode)
        return 1

    return 0
