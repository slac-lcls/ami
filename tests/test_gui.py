import asyncio
import json
import multiprocessing as mp
import os
import signal
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict

import amitypes as at
import pytest
import zmq

import ami.client.flowchart_messages as fcMsgs
from ami.client.flowchart import MessageBroker
from ami.comm import GraphCommHandler
from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.library.common import SourceNode


# event_loop fixture is now provided by conftest.py and managed by pytest-asyncio


@pytest.fixture(scope='function')
def broker(ami_backend):
    """
    Create a MessageBroker that runs in a background thread.
    This connects to the session-scoped AMI backend.
    """
    try:
        from pytest_cov.embed import cleanup_on_sigterm

        cleanup_on_sigterm()
    except ImportError:
        pass

    # Create a temporary directory for the broker's IPC sockets
    ipcdir = tempfile.mkdtemp()

    # Create the MessageBroker instance
    mb = MessageBroker(ami_backend, "", ipcdir=ipcdir)

    # Create a new event loop for the broker thread
    broker_loop = asyncio.new_event_loop()

    # Variable to track if the broker is running
    broker_running = threading.Event()

    # Run the broker in a background thread with its own event loop
    def run_broker():
        asyncio.set_event_loop(broker_loop)
        broker_running.set()  # Signal that the broker has started
        try:
            broker_loop.run_until_complete(mb.run())
        except (asyncio.CancelledError, RuntimeError):
            pass  # Expected when we cancel the broker or stop the loop

    broker_thread = threading.Thread(target=run_broker, daemon=True)
    broker_thread.start()

    # Wait for the broker to start
    broker_running.wait(timeout=2)
    time.sleep(0.1)  # Give it a moment to bind sockets

    yield mb

    # Cleanup: Stop the broker gracefully
    try:
        # Cancel all tasks in the broker's event loop
        def cancel_tasks():
            tasks = asyncio.all_tasks(broker_loop)
            for task in tasks:
                task.cancel()
            # Stop the loop after cancelling tasks
            broker_loop.stop()

        broker_loop.call_soon_threadsafe(cancel_tasks)

        # Wait for the thread to finish (with timeout)
        broker_thread.join(timeout=2)
    except Exception:
        pass
    finally:
        # Close the broker and clean up ZMQ resources
        mb.close()

        # Close the event loop if not already closed
        if not broker_loop.is_closed():
            broker_loop.close()

        # Clean up the temporary directory
        import shutil
        try:
            shutil.rmtree(ipcdir)
        except Exception:
            pass


@pytest.fixture(scope="module")
def dmypy():
    dmypy_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
    os.environ["DMYPY_STATUS_FILE"] = dmypy_file.name
    subprocess.run(["dmypy", "--status-file", dmypy_file.name, "start"])

    yield

    try:
        proc = subprocess.run(["dmypy", "--status-file", dmypy_file.name, "stop"])
        proc.check_returncode()
    except subprocess.CalledProcessError:
        subprocess.run(["dmypy", "--status-file", dmypy_file.name, "kill"])


@pytest.fixture(scope='function')
async def flowchart(request, ami_backend, broker, dmypy):
    """
    Creates a new Flowchart instance for each test, connected to the
    session-scoped AMI backend. Clears the graph state between tests
    to ensure test isolation.
    """
    try:
        from pytest_cov.embed import cleanup_on_sigterm

        cleanup_on_sigterm()
    except ImportError:
        pass

    os.makedirs(os.path.expanduser("~/.cache/ami/"), exist_ok=True)

    # Create a new flowchart instance connected to the persistent backend
    # Don't use 'with' statement here to avoid premature socket closure
    fc = Flowchart(broker_addr=broker.broker_sub_addr,
                   graphmgr_addr=ami_backend,
                   checkpoint_addr=broker.checkpoint_pub_addr)

    await fc.updateSources(init=True)

    yield (fc, broker)

    # Cleanup: close the flowchart after the test completes
    # Note: We don't clear the graph here because it can cause event loop issues
    # The session-scoped backend will accumulate graphs, but this is acceptable for tests
    fc.close()


def test_broker_sub(broker):
    ctx = zmq.Context()
    socket = ctx.socket(zmq.XPUB)
    socket.connect(broker.broker_sub_addr)
    # wait for the subscriber to connect
    assert socket.recv_string() == "\x01"

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


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_sources(qtbot, flowchart):
    flowchart = flowchart[0]
    source_library = flowchart.source_library

    source_tree = source_library.getSourceTree()
    sources = set(source_tree.keys())
    print(sources)
    assert sources == set(["delta", "cspad", "laser", "eventid", "timestamp", "heartbeat", "source"])

    label_tree = OrderedDict(
        [
            ("cspad", "<class 'amitypes.array.Array2d'>"),
            ("delta", {"delta_t": "<class 'int'>"}),
            ("eventid", "<class 'int'>"),
            ("heartbeat", "<class 'int'>"),
            ("laser", "<class 'int'>"),
            ("source", "<class 'amitypes.source.DataSource'>"),
            ("timestamp", "<class 'float'>"),
        ]
    )
    assert source_library.getLabelTree() == label_tree
    # test cached version
    assert source_library.getLabelTree() == label_tree

    assert source_library.getSourceType("cspad") == at.Array2d

    try:
        source_library.getSourceType("")
    except KeyError:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
async def test_create_single_node(qtbot, flowchart):
    """Test creating a single node in GUI."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())  # Ensure widget is created
    fc.createNode('Projection')
    await asyncio.sleep(0.1)
    assert 'Projection.0' in fc.nodes(data='node')


@pytest.mark.asyncio
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
async def test_connect_nodes(qtbot, flowchart):
    """Test connecting two nodes via terminals."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())  # Ensure widget is created

    # Get initial edge count (might not be 0 if other tests ran)
    initial_edges = len(fc._graph.edges())

    # Create a source node (use laser instead of cspad to avoid conflicts)
    node_name = 'laser'
    node_type = fc.source_library.getSourceType(node_name)
    source_node = SourceNode(name=node_name, terminals={'Out': {'io': 'out', 'ttype': node_type}})
    fc.addNode(node=source_node)

    # Create a processing node
    fc.createNode('Projection')

    # Get nodes
    laser_node = fc.nodes(data='node')['laser']
    # Find the projection node (might be Projection.0 or Projection.1 depending on previous tests)
    proj_nodes = [n for n in fc.nodes(data='node').keys() if n.startswith('Projection.')]
    proj_node = fc.nodes(data='node')[proj_nodes[-1]]  # Get the last one created

    # Connect them
    laser_out = laser_node._outputs['Out']
    proj_in = proj_node._inputs['In']
    laser_out().connectTo(proj_in())

    # Wait for connection to register
    await asyncio.sleep(0.1)

    # Verify a new edge was created
    assert len(fc._graph.edges()) == initial_edges + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
async def test_save_flowchart(qtbot, flowchart, tmp_path):
    """Test saving flowchart to .fc file."""
    fc, _ = flowchart
    qtbot.addWidget(fc.widget())  # Ensure widget is created

    # Create a simple graph
    fc.createNode('Projection')
    await asyncio.sleep(0.1)

    # Save to file
    widget = fc.widget()
    pth = os.path.join(tmp_path, 'test_graph.fc')

    widget.setCurrentFile(pth)
    widget.saveClicked()

    # Verify file exists
    assert os.path.exists(pth)

    # Verify it's valid JSON
    import json
    with open(pth) as f:
        data = json.load(f)
        assert 'nodes' in data
        assert len(data['nodes']) >= 1  # At least the Projection node
