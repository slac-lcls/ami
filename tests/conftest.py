import pytest
import os
import sys
import dill
import json
import shutil
import pathlib
import asyncio
import tempfile
import itertools
import subprocess
import signal
import numpy as np
import ami.multiproc as mp
try:
    import psana
except ImportError:
    psana = None
try:
    import p4p
except ImportError:
    p4p = None
try:
    import pyarrow as pa
except ImportError:
    pa = None
try:
    import h5py
except ImportError:
    h5py = None

from ami.multiproc import check_mp_start_method
from ami.asyncqt import QEventLoop
from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, PickN
from ami.flowchart.library.Operators import MeanVsScan
from ami.local import build_parser, run_ami
from ami.comm import Ports, GraphCommHandler


psanatest = pytest.mark.skipif(psana is None or hasattr(psana, "_psana"), reason="psana not avaliable")


psana1test = pytest.mark.skipif(psana is None or not hasattr(psana, "_psana"), reason="psana1 not avaliable")


epicstest = pytest.mark.skipif(p4p is None, reason="p4p not avaliable")


pyarrowtest = pytest.mark.skipif(pa is None, reason="pyarrow not avaliable")


hdf5test = pytest.mark.skipif(h5py is None, reason="h5py not avaliable")


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


@pytest.fixture(scope='function')
def complex_graph_file(tmpdir, qtbot):
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

    def filter_on(laser, sum0):
        if laser:
            return sum0

    graph.add(Map(name='FilterOn',
                  inputs=['laser', 'sum'],
                  outputs=['laseron'],
                  func=filter_on))

    binningOn = MeanVsScan('BinningOn')
    nodes = binningOn.to_operation(inputs={"Bin": "delta_t", "Value": "laseron"},
                                   outputs=['laseron_bin', 'laseron_value'])
    graph.add(nodes)

    def filter_off(laser, sum0):
        if not laser:
            return sum0

    graph.add(Map(name='FilterOff',
                  inputs=['laser', 'sum'],
                  outputs=['laseroff'],
                  func=filter_off))

    binningOff = MeanVsScan('BinningOff')
    nodes = binningOff.to_operation({"Bin": "delta_t", "Value": "laseroff"},
                                    outputs=['laseroff_bin', 'laseroff_value'])
    graph.add(nodes)

    fname = tmpdir.mkdir("complex_graph").join("complex_graph.dill")

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
        p = subprocess.run(['xtcwriter', '-f', fname, '-n', '25'], stdout=subprocess.PIPE)
        if p.returncode == 0:
            return fname


@pytest.fixture(scope='session')
def hdf5writer(tmpdir_factory):
    fname = tmpdir_factory.mktemp("h5s", False).join('data.h5')
    with h5py.File(fname, 'w') as f:
        f.create_dataset("gasdet", data=np.linspace(0.0, 5.0, 10))
        f.create_dataset("ec", data=np.arange(10))
        f.create_dataset("camera/image", data=np.arange(160).reshape((10, 4, 4)))
        f.create_dataset("camera/raw", data=np.arange(160).reshape((10, 4, 2, 2)))
    return fname


@pytest.fixture(scope='session')
def psana1_testdata():
    return pathlib.Path("/sdf/data/lcls/ds")


@pytest.fixture(scope='function')
def psana1_xtc(request, psana1_testdata):
    directory, filename = request.param
    #calibDir = psana1_testdata / 'multifile' / directory / 'calib' # do we want to keep a special dir or use the xpptut15?
    calibDir = psana1_testdata / directory / 'calib'
    psana.setOption('psana.calib-dir', calibDir)
    return psana1_testdata / directory / 'xtc' / filename


@pytest.fixture(scope='session')
def workerjson(tmpdir_factory, xtcwriter):

    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": 100,
        "repeat": True,
        "files": "data.xtc2" if xtcwriter is None else str(xtcwriter),
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
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    parser = build_parser()
    args = parser.parse_args(["-n", "1", '--headless', '--tcp',
                              '%s://%s' %
                              (request.param, workerjson)])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    try:
        host = "127.0.0.1"
        comm_addr = "tcp://%s:%d" % (host, Ports.BasePort + Ports.Comm)
        with GraphCommHandler(args.graph_name, comm_addr) as comm_handler:
            yield comm_handler
    except Exception as e:
        # let the fixture exit 'gracefully' if it fails
        print(e)
        yield None
    finally:
        queue.put(None)
        ami.join(1)
        # if ami still hasn't exitted then kill it
        if ami.is_alive():
            ami.terminate()
            ami.join(1)

        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print('AMI exited with non-zero status code: %d' % ami.exitcode)
            return 1


@pytest.fixture(scope='session')
def qevent_loop_gbl(qapp):
    with QEventLoop(qapp) as loop:
        yield loop


@pytest.fixture(scope='function')
def qevent_loop(qevent_loop_gbl):
    loop = qevent_loop_gbl
    asyncio.set_event_loop(loop)
    yield loop
    # clean out the old socket notifiers - not necessary if zmq sockets are explicitly closed
    for notifier in itertools.chain(loop._read_notifiers.values() if loop._read_notifiers is not None else [],
                                    loop._write_notifiers.values() if loop._write_notifiers is not None else []):
        notifier.setEnabled(False)


# fix the mp start method for platforms that need it
check_mp_start_method()
