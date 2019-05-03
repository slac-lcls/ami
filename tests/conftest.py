import pytest
import os
import sys
import dill
import json
import shutil
import tempfile
import subprocess
import signal
import multiprocessing as mp
import numpy as np
try:
    import psana
except ImportError:
    psana = None
try:
    import p4p
except ImportError:
    p4p = None

from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, FilterOn, FilterOff, Binning, PickN
from ami.local import build_parser, run_ami
from ami.comm import Ports, GraphCommHandler


psanatest = pytest.mark.skipif(psana is None, reason="psana not avaliable")


epicstest = pytest.mark.skipif(p4p is None, reason="p4p not avaliable")


@pytest.fixture(scope='session')
def ipc_dir(tmpdir_factory):
    if sys.platform == 'darwin':
        src_path = tmpdir_factory.mktemp("ipc", False)
        with tempfile.TemporaryDirectory(dir='/tmp') as short_tmp:
            dst_path = os.path.join(short_tmp, 'ipc')
            os.symlink(src_path, dst_path)
            yield dst_path
    else:
        yield tmpdir_factory.mktemp("ipc", False)


@pytest.fixture(scope='session')
def complex_graph_file(tmpdir_factory):
    graph = Graph(name='graph')

    def roi(cspad):
        return cspad[:100, :100]

    graph.add(Map(name='Roi',
                  inputs=['cspad'],
                  outputs=['roi'],
                  func=roi))

    graph.add(Map(name='Sum',
                  inputs=['roi'],
                  outputs=['sum'],
                  func=np.sum))

    graph.add(FilterOn(name='FilterOn',
                       condition_needs=['laser'],
                       outputs=['laseron']))

    graph.add(Binning(name='BinningOn',
                      condition_needs=['laseron'],
                      inputs=['delta_t', 'sum'],
                      outputs=['signal']))

    graph.add(FilterOff(name='FilterOff',
                        condition_needs=['laser'],
                        outputs=['laseroff']))

    graph.add(Binning(name='BinningOff',
                      condition_needs=['laseroff'],
                      inputs=['delta_t', 'sum'],
                      outputs=['reference']))

    fname = tmpdir_factory.mktemp("complex_graph", False).join("complex_graph.dill")

    with open(fname, 'wb') as fd:
        dill.dump(graph, fd)
    return fname


@pytest.fixture(scope='session')
def psana_graph(tmpdir_factory):
    graph = Graph(name='graph')
    graph.add(PickN(name='picker',
                    inputs=['xppcspad:raw:image'],
                    outputs=['picked']))
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
def start_ami(request, workerjson):

    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-t', '--headless',
                              '%s://%s' %
                              (request.param, workerjson)])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    try:
        host = "127.0.0.1"
        comm_addr = "tcp://%s:%d" % (host, Ports.Comm)
        comm_handler = GraphCommHandler(args.graph_name, comm_addr)
        yield comm_handler
    except Exception:
        # let the fixture exit 'gracefully' if it fails
        yield None
    finally:
        queue.put(None)
        ami.join()

        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print('AMI exited with non-zero status code: %d' % ami.exitcode)
            return 1
