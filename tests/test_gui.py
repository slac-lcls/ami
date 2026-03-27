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
import time
import os
import amitypes as at
import ami.client.flowchart_messages as fcMsgs
from ami.flowchart.library.common import SourceNode
from collections import OrderedDict


# Fixtures (broker, dmypy, flowchart) are now in conftest.py


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

    assert sources == set(["delta", "cspad", "laser", "eventid", "timestamp", "heartbeat", "source", "xppcspad"])

    # Check that core sources are present (not an exact match since config is auto-scanned)
    label_tree = source_library.getLabelTree()
    assert "cspad" in label_tree
    assert "laser" in label_tree
    assert "delta" in label_tree
    assert "eventid" in label_tree
    assert "timestamp" in label_tree
    assert "heartbeat" in label_tree
    assert "source" in label_tree

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

    # Create a source node (cspad is an Array2d)
    node_name = 'cspad'
    node_type = fc.source_library.getSourceType(node_name)
    source_node = SourceNode(name=node_name, terminals={'Out': {'io': 'out', 'ttype': node_type}})
    fc.addNode(node=source_node)

    # Create a processing node (Roi2D accepts Array2d)
    fc.createNode('Roi2D')

    # Get nodes
    cspad_node = fc.nodes(data='node')['cspad']
    # Find the Roi2D node (might be Roi2D.0 or Roi2D.1 depending on previous tests)
    all_nodes = dict(fc.nodes(data='node'))
    roi_nodes = [n for n in all_nodes.keys() if n.startswith('Roi2D.')]
    roi_node = all_nodes[roi_nodes[-1]]  # Get the last one created

    # Connect them
    cspad_out = cspad_node._outputs['Out']
    roi_in = roi_node._inputs['In']
    cspad_out().connectTo(roi_in())

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
