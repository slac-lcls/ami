import asyncio
import itertools
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile

import dill
import numpy as np
import pytest

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

from ami.asyncqt import QEventLoop
from ami.comm import GraphCommHandler, Ports
from ami.flowchart.library.Operators import MeanVsScan
from ami.graph_nodes import Map, PickN
from ami.graphkit_wrapper import Graph
from ami.local import build_parser, run_ami
from ami.multiproc import check_mp_start_method
from ami.client import GraphMgrAddress
import time


psanatest = pytest.mark.skipif(psana is None or hasattr(psana, "_psana"), reason="psana not avaliable")


psana1test = pytest.mark.skipif(psana is None or not hasattr(psana, "_psana"), reason="psana1 not avaliable")


epicstest = pytest.mark.skipif(p4p is None, reason="p4p not avaliable")


pyarrowtest = pytest.mark.skipif(pa is None, reason="pyarrow not avaliable")


hdf5test = pytest.mark.skipif(h5py is None, reason="h5py not avaliable")


@pytest.fixture(scope="session")
def ipc_dir(tmpdir_factory):
    if sys.platform == "darwin":
        src_path = tmpdir_factory.mktemp("ipc", False)
        with tempfile.TemporaryDirectory(dir="/tmp") as short_tmp:
            dst_path = os.path.join(short_tmp, "ipc")
            os.symlink(src_path, dst_path)
            yield dst_path
    else:
        yield tmpdir_factory.mktemp("ipc", False)


@pytest.fixture(scope="function")
def complex_graph_file(tmpdir, qtbot):
    graph = Graph(name="graph")

    def roi(cspad):
        return cspad[:100, :100]

    graph.add(Map(name="Roi", inputs=["cspad"], outputs=["roi"], func=roi))

    graph.add(Map(name="Sum", inputs=["roi"], outputs=["sum"], func=np.sum))

    def filter_on(laser, sum0):
        if laser:
            return sum0

    graph.add(Map(name="FilterOn", inputs=["laser", "sum"], outputs=["laseron"], func=filter_on))

    binningOn = MeanVsScan("BinningOn")
    nodes = binningOn.to_operation(
        inputs={"Bin": "delta_t", "Value": "laseron"}, outputs=["laseron_bin", "laseron_value"]
    )
    graph.add(nodes)

    def filter_off(laser, sum0):
        if not laser:
            return sum0

    graph.add(Map(name="FilterOff", inputs=["laser", "sum"], outputs=["laseroff"], func=filter_off))

    binningOff = MeanVsScan("BinningOff")
    nodes = binningOff.to_operation({"Bin": "delta_t", "Value": "laseroff"}, outputs=["laseroff_bin", "laseroff_value"])
    graph.add(nodes)

    fname = tmpdir.mkdir("complex_graph").join("complex_graph.dill")

    with open(fname, "wb") as fd:
        dill.dump(graph, fd)
    return fname


@pytest.fixture(scope="session")
def psana_graph(tmpdir_factory):
    graph = Graph(name="graph")
    graph.add(PickN(name="picker", inputs=["xppcspad:raw:image"], outputs=["picked"]))
    fname = tmpdir_factory.mktemp("psana_graph", False).join("psana_graph.dill")
    with open(fname, "wb") as fd:
        dill.dump(graph, fd)
    return fname


@pytest.fixture(scope="session")
def xtcwriter(tmpdir_factory):
    if shutil.which("xtcwriter") is not None:
        fname = tmpdir_factory.mktemp("xtcs", False).join("data.xtc2")
        p = subprocess.run(["xtcwriter", "-f", fname, "-n", "25"], stdout=subprocess.PIPE)
        if p.returncode == 0:
            return fname


@pytest.fixture(scope="session")
def hdf5writer(tmpdir_factory):
    fname = tmpdir_factory.mktemp("h5s", False).join("data.h5")
    with h5py.File(fname, "w") as f:
        f.create_dataset("gasdet", data=np.linspace(0.0, 5.0, 10))
        f.create_dataset("ec", data=np.arange(10))
        f.create_dataset("camera/image", data=np.arange(160).reshape((10, 4, 4)))
        f.create_dataset("camera/raw", data=np.arange(160).reshape((10, 4, 2, 2)))
    return fname


@pytest.fixture(scope="session")
def psana1_testdata():
    return pathlib.Path("/sdf/data/lcls/ds")


@pytest.fixture(scope="function")
def psana1_xtc(request, psana1_testdata):
    directory, filename = request.param
    # calibDir = psana1_testdata / 'multifile' / directory / 'calib' # do we want to keep a special dir or use the xpptut15?
    calibDir = psana1_testdata / directory / "calib"
    psana.setOption("psana.calib-dir", calibDir)
    return psana1_testdata / directory / "xtc" / filename


@pytest.fixture(scope="session")
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

    fname = tmpdir_factory.mktemp("worker_config", False).join("worker.json")
    with open(fname, "w") as fd:
        json.dump(cfg, fd)
    return fname


@pytest.fixture(scope="function")
def complex_graph(complex_graph_file):
    with open(complex_graph_file, "rb") as fd:
        return dill.load(fd)


@pytest.fixture(scope='session')
def ami_backend(request, workerjson, ipc_dir):
    """
    Start a single, session-scoped AMI backend (worker, collector, manager)
    for all GUI tests to share. This runs once at the beginning of the test
    session and is torn down at the end.
    """

    try:
        from pytest_cov.embed import cleanup_on_sigterm

        cleanup_on_sigterm()
    except ImportError:
        pass

    parser = build_parser()
    args = parser.parse_args([
        "-n", "1",
        '-i', str(ipc_dir),
        '--headless',
        f'static://{workerjson}'
    ])

    queue = mp.Queue()
    ami_proc = mp.Process(name='ami_backend', target=run_ami, args=(args, queue))
    ami_proc.start()

    # Create the graphmgr address object
    comm_addr = "ipc://%s/comm" % ipc_dir
    view_addr = "ipc://%s/view" % ipc_dir
    graphinfo_addr = "ipc://%s/info" % ipc_dir
    export_addr = "ipc://%s/export" % ipc_dir
    graphmgr = GraphMgrAddress("graph", comm_addr, view_addr, graphinfo_addr, export_addr)

    # Wait for the backend to be ready
    try:
        with GraphCommHandler(graphmgr.name, graphmgr.comm) as comm:
            for _ in range(50):  # 5 second timeout
                if comm.sources:
                    break
                time.sleep(0.1)
            else:
                pytest.fail("Timeout waiting for AMI backend to start.")
    except Exception as e:
        # Clean up if startup fails
        queue.put(None)
        ami_proc.join(2)
        if ami_proc.is_alive():
            ami_proc.terminate()
            ami_proc.join()
        pytest.fail(f"Failed to start AMI backend: {e}")

    # Finalizer to clean up the process at the end of the session
    def finalizer():
        queue.put(None)
        ami_proc.join(2)
        if ami_proc.is_alive():
            ami_proc.terminate()
            ami_proc.join()

    request.addfinalizer(finalizer)

    yield graphmgr


@pytest.fixture(scope='function')
def start_ami(request, workerjson, ami_backend, ipc_dir):
    """
    Smart routing fixture for AMI backend.
    - 'static' param: Uses session-scoped ami_backend (fast, shared)
    - 'psana' param: Creates function-scoped backend (slower, isolated)
    """
    data_source = request.param if hasattr(request, 'param') else 'static'

    if data_source == 'static':
        # Use existing session-scoped backend (IPC)
        with GraphCommHandler(ami_backend.name, ami_backend.comm) as comm_handler:
            yield comm_handler
        return

    elif data_source == 'psana':
        # Create function-scoped psana backend (IPC)
        try:
            from pytest_cov.embed import cleanup_on_sigterm
            cleanup_on_sigterm()
        except ImportError:
            pass

        # Create temporary IPC directory for this test
        psana_ipc_dir = tempfile.mkdtemp(prefix='ami_psana_')

        parser = build_parser()
        args = parser.parse_args([
            "-n", "1",
            '-i', psana_ipc_dir,
            '--headless',
            f'psana://{workerjson}'
        ])

        queue = mp.Queue()
        ami = mp.Process(name='ami_psana',
                         target=run_ami,
                         args=(args, queue))
        ami.start()

        try:
            comm_addr = "ipc://%s/comm" % psana_ipc_dir
            with GraphCommHandler(args.graph_name, comm_addr) as comm_handler:
                # Wait for backend to be ready
                for _ in range(50):  # 5 second timeout
                    if comm_handler.sources:
                        break
                    time.sleep(0.1)
                else:
                    pytest.fail("Timeout waiting for psana backend to start.")

                yield comm_handler
        except Exception as e:
            print(f"Psana backend failed: {e}")
            yield None
        finally:
            queue.put(None)
            ami.join(2)
            if ami.is_alive():
                ami.terminate()
                ami.join(1)

            # Clean up IPC directory
            try:
                shutil.rmtree(psana_ipc_dir)
            except Exception:
                pass

            if ami.exitcode not in (0, -signal.SIGTERM, None):
                print('AMI psana backend exited with non-zero status code: %d' % ami.exitcode)
    else:
        pytest.fail(f"Unknown data source: {data_source}")


class QEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Custom event loop policy that creates QEventLoop instances."""

    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp

    def new_event_loop(self):
        return QEventLoop(self.qapp)


@pytest.fixture(scope='session')
def event_loop_policy(qapp):
    """
    Provide a custom event loop policy that creates QEventLoop instances.
    This is the recommended way to integrate qasync with pytest-asyncio.
    """
    return QEventLoopPolicy(qapp)


@pytest.fixture(scope='function')
def qevent_loop(qapp):
    """
    Create a fresh QEventLoop for each test function.
    For backward compatibility with tests that explicitly request qevent_loop.
    """
    loop = QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    yield loop

    # Clean up: disable socket notifiers
    try:
        for notifier in itertools.chain(
            loop._read_notifiers.values() if loop._read_notifiers is not None else [],
            loop._write_notifiers.values() if loop._write_notifiers is not None else []
        ):
            notifier.setEnabled(False)
    except Exception:
        pass


# fix the mp start method for platforms that need it
check_mp_start_method()
