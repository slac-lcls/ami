import asyncio
import pytest
import zmq
import time
import os
import tempfile
import signal
import json
import subprocess
import amitypes as at
import multiprocessing as mp
import ami.client.flowchart_messages as fcMsgs
from ami.client import GraphMgrAddress
from ami.client.flowchart import MessageBroker
from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.library.common import SourceNode
from ami.local import build_parser, run_ami
from ami.comm import GraphCommHandler
from ami.fc_to_worker import extract_sources_from_fc
from collections import OrderedDict


# Helper functions for flowchart_from_file fixture


def resolve_fc_path(fc_file):
    """
    Resolve .fc file path.

    Args:
        fc_file: Filename or relative path

    Returns:
        str: Path to .fc file

    Examples:
        'my_graph.fc' → 'tests/graphs/my_graph.fc'
        'examples/complex.fc' → 'examples/complex.fc'
        '/abs/path/graph.fc' → '/abs/path/graph.fc'
    """
    # Already absolute
    if os.path.isabs(fc_file):
        return fc_file

    # Has directory component - use as-is
    if os.path.dirname(fc_file):
        return fc_file

    # Just filename - default to tests/graphs/
    return os.path.join('tests/graphs', fc_file)


def wait_for_features(comm, qtbot, timeout_ms=5000):
    """
    Wait for features to be available (featuresVersion to update).

    Args:
        comm: GraphCommHandler instance
        qtbot: pytest-qt qtbot fixture
        timeout_ms: Maximum time to wait in milliseconds (default: 5000)

    Returns:
        bool: True if features available, False if timeout

    Example:
        if wait_for_features(comm, qtbot):
            result = comm.fetch('Sum.0')
        else:
            pytest.fail("Timeout waiting for features")
    """
    initial_version = comm.featuresVersion
    elapsed = 0

    while comm.featuresVersion == initial_version and elapsed < timeout_ms:
        qtbot.wait(100)
        elapsed += 100

    return elapsed < timeout_ms


class BrokerHelper:
    def __init__(self, graphmgr_addr, ipcdir, comm):
        # we are in a forked process so create a new event loop (needed in some cases).
        self.loop = asyncio.new_event_loop()
        # set this new event loop as the default one so zmq picks it up
        asyncio.set_event_loop(self.loop)
        self.broker = MessageBroker(graphmgr_addr, "", ipcdir=ipcdir)
        self.comm = comm
        self.task = asyncio.ensure_future(self.broker.run())

        self.loop.run_until_complete(self.loop.run_in_executor(None, self.communicate))

        # if the message brokers task is still running cancel it
        if not self.task.done():
            self.task.cancel()

        # cleanup the broker
        self.broker.close()

    def communicate(self):
        while True:
            request = self.comm.recv()
            if request is None:
                break
            else:
                self.comm.send(getattr(self.broker, request))

    @staticmethod
    def execute(graphmgr_addr, ipcdir, comm):
        return BrokerHelper(graphmgr_addr, ipcdir, comm)


class BrokerProxy:
    def __init__(self, comm):
        self.comm = comm

    def exit(self):
        self.comm.send(None)

    def __getattr__(self, name):
        self.comm.send(name)
        return self.comm.recv()


# event_loop fixture removed - no longer needed after asyncio removal from flowchart


@pytest.fixture(scope='function')
def graphmgr_addr(ipc_dir):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    comm_addr = "ipc://%s/comm" % ipc_dir
    view_addr = "ipc://%s/view" % ipc_dir
    graphinfo_addr = "ipc://%s/info" % ipc_dir
    export_addr = "ipc://%s/export" % ipc_dir

    graphmgr = GraphMgrAddress("graph", comm_addr, view_addr, graphinfo_addr, export_addr)

    yield graphmgr


@pytest.fixture(scope='function')
def broker(ipc_dir, graphmgr_addr):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    parent_comm, child_comm = mp.Pipe()
    # start the manager process
    proc = mp.Process(
        name='broker',
        target=BrokerHelper.execute,
        args=(graphmgr_addr, ipc_dir, child_comm),
        daemon=False
    )
    proc.start()

    broker = BrokerProxy(parent_comm)
    yield broker

    # cleanup the manager process
    broker.exit()
    proc.join(2)
    # if ami still hasn't exitted then kill it
    if proc.is_alive():
        proc.terminate()
        proc.join()
    return proc.exitcode


@pytest.fixture(scope='module')
def dmypy():
    dmypy_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
    os.environ['DMYPY_STATUS_FILE'] = dmypy_file.name
    subprocess.run(["dmypy", "--status-file", dmypy_file.name, "start"])

    yield

    try:
        proc = subprocess.run(["dmypy", "--status-file", dmypy_file.name, "stop"])
        proc.check_returncode()
    except subprocess.CalledProcessError:
        subprocess.run(["dmypy", "--status-file", dmypy_file.name, "kill"])


@pytest.fixture(scope='function')
def flowchart(request, workerjson, broker, ipc_dir, graphmgr_addr, dmypy):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-i', str(ipc_dir), '--headless',
                              '%s://%s' %
                              (request.param, workerjson)])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    try:
        # wait for ami to be fully up before updating the sources
        with GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm) as comm:
            while not comm.sources:
                time.sleep(0.1)

        os.makedirs(os.path.expanduser("~/.cache/ami/"), exist_ok=True)

        with Flowchart(broker_addr=broker.broker_sub_addr,
                       graphmgr_addr=graphmgr_addr,
                       checkpoint_addr=broker.checkpoint_pub_addr) as fc:

            fc.initialize()  # Sync initialization

            yield (fc, broker)

    except Exception as e:
        # let the fixture exit 'gracefully' if it fails
        print("error setting up flowchart fixture:", e)
        yield None
    finally:
        queue.put(None)
        ami.join(2)
        # if ami still hasn't exitted then kill it
        if ami.is_alive():
            ami.terminate()
            ami.join()

        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print('AMI exited with non-zero status code: %d' % ami.exitcode)
            return 1


@pytest.fixture(scope='function')
def flowchart_hdf(request, tmp_path, qtbot, broker, ipc_dir, graphmgr_addr):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": 100,
        "repeat": True,
        "files": [os.path.join('tests/graphs', request.param[0])]
    }

    fname = os.path.join(tmp_path, 'worker.json')
    with open(fname, 'w') as fd:
        json.dump(cfg, fd)

    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-i', str(ipc_dir), '--headless',
                              'hdf5://%s' % fname])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    try:
        # wait for ami to be fully up before updating the sources
        comm = GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm)
        while not comm.sources:
            time.sleep(0.1)

        with Flowchart(broker_addr=broker.broker_sub_addr,
                       graphmgr_addr=graphmgr_addr,
                       checkpoint_addr=broker.checkpoint_pub_addr) as fc:

            fc.initialize()  # Sync initialization

            qtbot.addWidget(fc.widget())
            fc.loadFile(os.path.join('tests/graphs', request.param[1]))

            yield (fc, broker, comm)

    except Exception as e:
        # let the fixture exit 'gracefully' if it fails
        print("error setting up flowchart fixture:", e)
        yield None
    finally:
        queue.put(None)
        ami.join(2)
        # if ami still hasn't exitted then kill it
        if ami.is_alive():
            ami.terminate()
            ami.join()

        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print('AMI exited with non-zero status code: %d' % ami.exitcode)
            return 1


@pytest.fixture(scope='function')
def flowchart_from_file(request, broker, ipc_dir, graphmgr_addr, dmypy, qtbot, tmp_path):
    """
    Create flowchart with auto-mocked sources from .fc file.

    Automatically detects sources in the .fc file and creates matching
    mock static data sources. Supports limiting event count and retrieving
    computed results for verification.

    Usage:
        # Simple: just load .fc file (default 10 events)
        @pytest.mark.parametrize('flowchart_from_file', [
            'my_graph.fc',
        ], indirect=True)
        def test_graph(flowchart_from_file):
            fc, broker, comm = flowchart_from_file
            # Graph already loaded, sources mocked

        # With custom event limit
        @pytest.mark.parametrize('flowchart_from_file', [
            ('my_graph.fc', 5),  # Only 5 events
        ], indirect=True)
        def test_graph_with_limit(flowchart_from_file):
            fc, broker, comm = flowchart_from_file
            # Only 5 events will be processed

    Parameters (via request.param):
        - String: Path to .fc file (default: 10 events)
        - Tuple: (fc_file_path, num_events)
          - fc_file_path: Path to .fc file (relative to project root)
          - num_events: Number of events to generate (default: 10)

    Returns:
        (fc, broker, comm): Tuple of:
            - fc: Flowchart instance with .fc file loaded
            - broker: MessageBroker instance
            - comm: GraphCommHandler for retrieving results

    Example - Verify computation:
        @pytest.mark.parametrize('flowchart_from_file', [
            ('simple_sum.fc', 5),
        ], indirect=True)
        def test_sum_computation(flowchart_from_file, qtbot):
            fc, broker, comm = flowchart_from_file

            ctrl = fc.widget()
            ctrl.applyClicked()

            if wait_for_features(comm, qtbot):
                result = comm.fetch('Sum.0')
                assert result > 0
            else:
                pytest.fail("Timeout waiting for results")
    """
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    # Parse parameters
    if isinstance(request.param, tuple):
        fc_file, num_events = request.param
    else:
        fc_file = request.param
        num_events = 10  # Default: 10 events

    fc_path = resolve_fc_path(fc_file)

    # Extract source configurations from .fc file
    source_config = extract_sources_from_fc(fc_path)

    # Create worker.json with mocked sources
    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": num_events,  # Limit number of events
        "repeat": False,      # Don't loop - stop after bound
        "files": "data.xtc2",
        "config": source_config,  # Auto-generated from .fc file
    }

    workerjson_path = os.path.join(tmp_path, 'worker.json')
    with open(workerjson_path, 'w') as fd:
        json.dump(cfg, fd)

    # Start AMI with static data source
    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-i', str(ipc_dir), '--headless',
                              f'static://{workerjson_path}'])

    queue = mp.Queue()
    ami = mp.Process(name='ami', target=run_ami, args=(args, queue))
    ami.start()

    try:
        # Wait for AMI to be ready and create persistent comm handler
        comm = GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm)
        while not comm.sources:
            time.sleep(0.1)

        os.makedirs(os.path.expanduser("~/.cache/ami/"), exist_ok=True)

        # Create flowchart
        with Flowchart(broker_addr=broker.broker_sub_addr,
                       graphmgr_addr=graphmgr_addr,
                       checkpoint_addr=broker.checkpoint_pub_addr) as fc:

            fc.initialize()

            qtbot.addWidget(fc.widget())

            fc.loadFile(fc_path)

            yield (fc, broker, comm)

    except Exception as e:
        print(f"error setting up flowchart_from_file fixture: {e}")
        import traceback
        traceback.print_exc()
        yield None
    finally:
        # Cleanup
        queue.put(None)
        ami.join(2)
        if ami.is_alive():
            ami.terminate()
            ami.join()

        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print(f'AMI exited with non-zero status code: {ami.exitcode}')
            return 1


def test_broker_sub(broker):
    ctx = zmq.Context()
    socket = ctx.socket(zmq.XPUB)
    socket.connect(broker.broker_sub_addr)
    # wait for the subscriber to connect
    assert socket.recv_string() == '\x01'

    name = "Projection"
    msg = fcMsgs.CreateNode(name, "Projection")
    socket.send_string(name, zmq.SNDMORE)
    socket.send_pyobj(msg)

    # check that broker msgs are empty
    msgs = broker.msgs
    assert not msgs

    # send a node close msg
    msg = fcMsgs.CloseNode()
    socket.send_string(name, zmq.SNDMORE)
    socket.send_pyobj(msg)

    # wait to see if the broker msgs are updated
    start = time.time()
    while not msgs:
        end = time.time()
        if end - start > 10:
            assert False, "Timeout waiting for broker update"
        msgs = broker.msgs
    # check the msg
    assert name in msgs
    assert isinstance(msgs[name], fcMsgs.CloseNode)

    # cleanup the zmq context
    ctx.destroy()


@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
def test_sources(qtbot, flowchart):
    flowchart = flowchart[0]
    source_library = flowchart.source_library

    source_tree = source_library.getSourceTree()
    sources = set(source_tree.keys())
    print(sources)
    assert sources == set(['delta', 'cspad', 'laser', 'eventid', 'timestamp', 'heartbeat', 'source'])

    label_tree = OrderedDict([('cspad', "<class 'amitypes.array.Array2d'>"),
                              ('delta', {'delta_t': "<class 'int'>"}),
                              ('eventid', "<class 'int'>"),
                              ('heartbeat', "<class 'int'>"),
                              ('laser', "<class 'int'>"),
                              ('source', "<class 'amitypes.source.DataSource'>"),
                              ('timestamp', "<class 'float'>")])
    assert source_library.getLabelTree() == label_tree
    # test cached version
    assert source_library.getLabelTree() == label_tree

    assert source_library.getSourceType('cspad') == at.Array2d

    try:
        source_library.getSourceType('')
    except KeyError:
        pass


@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
def test_editor(qtbot, flowchart, tmp_path):
    flowchart, broker = flowchart

    qtbot.addWidget(flowchart.widget())

    flowchart.createNode('Roi2D')
    roi_node = flowchart.nodes(data='node')['Roi2D.0']

    node_name = 'cspad'
    node_type = flowchart.source_library.getSourceType(node_name)
    node = SourceNode(name=node_name, terminals={'Out': {'io': 'out', 'ttype': node_type}})

    flowchart.addNode(node=node)
    cspad_node = flowchart.nodes(data='node')['cspad']

    cspad_out = cspad_node._outputs['Out']
    roi_in = roi_node._inputs['In']

    cspad_out().connectTo(roi_in())
    qtbot.wait(100)  # Wait 100ms for nodeTermConnected slot to execute before we can check edges
    assert len(flowchart._graph.edges()) == 1

    widget = flowchart.widget()

    pth = os.path.join(tmp_path, 'graph.fc')
    widget.setCurrentFile(pth)
    widget.saveClicked()

    widget.clear()
    assert len(flowchart._graph.edges()) == 0

    flowchart.loadFile(pth)
    assert len(flowchart._graph.edges()) == 1


# Tests using flowchart_from_file fixture

# Note: Create simple .fc test files in tests/graphs/ using the GUI, for example:
# - simple_roi_sum.fc: cspad → Roi2D → Sum
# - simple_projection.fc: image → Projection
# Then uncomment and adapt the tests below

# Example test using existing .fc file from project root
# (File path has directory, so resolve_fc_path uses it as-is)


@pytest.mark.parametrize('flowchart_from_file', ['ATM_crix_new.fc'], indirect=True)
def test_load_atm_crix(flowchart_from_file):
    """
    Test loading ATM_crix_new.fc with auto-mocked sources.
    """
    fc, broker, comm = flowchart_from_file

    # Check sources were auto-detected and mocked
    assert 'timing:raw:eventcodes' in fc.nodes(data='node')
    assert 'c_piranha:raw:raw' in fc.nodes(data='node')
    assert 'c_atmopal:raw:image' in fc.nodes(data='node')
    assert 'c_piranha:ttfex:fltpos' in fc.nodes(data='node')

    # Check graph has processing nodes
    nodes = fc.nodes(data='node')
    assert len(nodes) > 4  # More than just sources

    # Check connections exist
    assert len(fc._graph.edges()) > 0

    ctrl = fc.widget()
    ctrl.applyClicked()

@pytest.mark.parametrize('flowchart_from_file', [
    ('ATM_crix_new.fc', 5),   # Test with 5 events
    ('ATM_crix_new.fc', 10),  # Test with 10 events (default)
], indirect=True)
def test_atm_different_event_counts(flowchart_from_file):
    """Test fixture works with different event counts."""
    fc, broker, comm = flowchart_from_file

    # Just verify fixture created flowchart successfully
    assert fc is not None
    assert comm is not None
    assert len(fc.nodes(data='node')) > 0


# Example: Computation verification test
# @pytest.mark.parametrize('flowchart_from_file', [
#     ('simple_roi_sum.fc', 5),
# ], indirect=True)
# def test_roi_sum_computation(flowchart_from_file, qtbot):
#     """Verify ROI + Sum computes correctly."""
#     fc, broker, comm = flowchart_from_file
#
#     # Apply the graph
#     ctrl = fc.widget()
#     ctrl.applyClicked()
#
#     # Wait for results
#     if not wait_for_features(comm, qtbot, timeout_ms=5000):
#         pytest.fail("Timeout waiting for graph to process")
#
#     # Get computed values
#     roi_output = comm.fetch('Roi2D.0')
#     sum_output = comm.fetch('Sum.0')
#
#     # Verify correctness
#     import numpy as np
#     expected_sum = np.sum(roi_output)
#     assert np.isclose(sum_output, expected_sum), \
#         f"Sum computation incorrect: got {sum_output}, expected {expected_sum}"
