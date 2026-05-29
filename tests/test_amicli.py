"""
Unit tests for AmiCli - graph manipulation API.

Tests node creation, connections, parameters, validation, and state management
without requiring a running AMI backend (no data execution).
"""

import asyncio  # noqa: E402
import os
import shutil
import tempfile
import threading
import time

# Disable MCP server before any AMI imports
os.environ["AMI_DISABLE_MCP"] = "1"

import pytest  # noqa: E402

from ami.client.flowchart import MessageBroker  # noqa: E402


@pytest.fixture(scope="module")
def broker_module(ami_backend):
    """Module-scoped MessageBroker - one for all tests in this file."""
    ipcdir = tempfile.mkdtemp()
    mb = MessageBroker(ami_backend, "", ipcdir=ipcdir, prometheus_port=None, headless=True)

    broker_loop = asyncio.new_event_loop()
    broker_running = threading.Event()

    def run_broker():
        asyncio.set_event_loop(broker_loop)
        broker_running.set()
        try:
            broker_loop.run_until_complete(mb.run())
        except (asyncio.CancelledError, RuntimeError):
            pass

    broker_thread = threading.Thread(target=run_broker, daemon=True)
    broker_thread.start()
    broker_running.wait(timeout=2)
    time.sleep(0.1)

    # Store loop for flowchart_module to use
    mb._test_loop = broker_loop

    yield mb

    # Cleanup
    try:

        async def cancel_all():
            current = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks(broker_loop) if t is not current and not t.done()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        future = asyncio.run_coroutine_threadsafe(cancel_all(), broker_loop)
        future.result(timeout=2)
        broker_thread.join(timeout=2)
    except Exception:
        pass
    finally:
        mb.close()
        if not broker_loop.is_closed():
            broker_loop.close()
        try:
            shutil.rmtree(ipcdir)
        except Exception:
            pass


@pytest.fixture(scope="module")
def flowchart_module(ami_backend, broker_module, dmypy):
    """Module-scoped Flowchart - one for all tests in this file."""
    from ami.flowchart.Flowchart import Flowchart

    os.makedirs(os.path.expanduser("~/.cache/ami/"), exist_ok=True)

    fc = Flowchart(
        broker_addr=broker_module.broker_sub_addr,
        graphmgr_addr=ami_backend,
        checkpoint_addr=broker_module.checkpoint_pub_addr,
    )

    # Run async updateSources in the broker's event loop
    future = asyncio.run_coroutine_threadsafe(fc.updateSources(init=True), broker_module._test_loop)
    future.result(timeout=10)

    yield fc

    fc.close()


@pytest.fixture
def amicli(flowchart_module):
    """Function-scoped AmiCli with fresh graph state per test."""
    import networkx as nx

    ctrl = flowchart_module.widget()
    cli = ctrl.amicli
    # Synchronously clear graph state (no async ZMQ needed for unit tests)
    for name, node in list(cli.chart._graph.nodes(data="node")):
        if node is not None:
            node.close(emit=False)
    cli.chart._graph = nx.MultiDiGraph()
    return cli


@pytest.mark.asyncio
async def test_create_node(amicli):
    """Test creating a node with auto-generated name."""
    node = amicli.create_node("Projection")
    assert node.name() == "Projection.0"
    assert "Projection.0" in amicli.graph.nodes()


@pytest.mark.asyncio
async def test_create_node_with_label(amicli):
    """Test creating a node with a label preserves auto-generated name."""
    node = amicli.create_node("Projection", label="My Projection")
    assert node.name() == "Projection.0"
    assert node._label == "My Projection"


@pytest.mark.asyncio
async def test_ensure_source(amicli):
    """Test ensuring a source node exists."""
    result = amicli.ensure_source("cspad")
    assert result == "cspad"
    assert "cspad" in amicli.graph.nodes()

    node = amicli.graph.nodes["cspad"]["node"]
    assert "Out" in node.terminals


@pytest.mark.asyncio
async def test_ensure_source_idempotent(amicli):
    """Test that calling ensure_source twice doesn't create duplicates."""
    amicli.ensure_source("cspad")
    amicli.ensure_source("cspad")

    cspad_nodes = [n for n in amicli.graph.nodes() if n == "cspad"]
    assert len(cspad_nodes) == 1


@pytest.mark.asyncio
async def test_ensure_source_invalid(amicli):
    """Test that ensure_source raises for non-existent source."""
    with pytest.raises(Exception):
        amicli.ensure_source("nonexistent_source_xyz")


@pytest.mark.asyncio
async def test_connect_nodes(amicli):
    """Test connecting two nodes."""
    amicli.ensure_source("cspad")
    amicli.create_node("Roi2D")

    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")
    await asyncio.sleep(0.1)

    assert amicli.graph.has_edge("cspad", "Roi2D.0")


@pytest.mark.asyncio
async def test_connect_nodes_invalid_terminal(amicli):
    """Test that connecting with invalid terminal raises."""
    amicli.ensure_source("cspad")
    amicli.create_node("Roi2D")

    with pytest.raises(Exception):
        amicli.connect_nodes("cspad", "NonExistent", "Roi2D.0", "In")


@pytest.mark.asyncio
async def test_disconnect_nodes(amicli):
    """Test disconnecting two nodes."""
    amicli.ensure_source("cspad")
    amicli.create_node("Roi2D")
    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")
    await asyncio.sleep(0.1)

    assert amicli.graph.has_edge("cspad", "Roi2D.0")

    amicli.disconnect_nodes("cspad", "Out", "Roi2D.0", "In")
    await asyncio.sleep(0.1)

    assert not amicli.graph.has_edge("cspad", "Roi2D.0")


@pytest.mark.asyncio
async def test_get_node_parameters(amicli):
    """Test getting node parameters."""
    amicli.create_node("GaussianFilter1D")

    params = amicli.get_node_parameters("GaussianFilter1D.0")
    assert "sigma" in params
    assert "axis" in params
    assert "mode" in params
    assert params["axis"] == -1
    assert params["mode"] == "reflect"


@pytest.mark.asyncio
async def test_set_node_parameters(amicli):
    """Test setting node parameters."""
    amicli.create_node("GaussianFilter1D")

    result = amicli.set_node_parameters("GaussianFilter1D.0", {"sigma": 3.5})
    assert result["sigma"] == 3.5

    node = amicli.graph.nodes["GaussianFilter1D.0"]["node"]
    assert node.values["sigma"] == 3.5


@pytest.mark.asyncio
async def test_set_node_parameters_combo(amicli):
    """Test setting a combo parameter value (regression for combo default bug)."""
    amicli.create_node("PeakFit")

    # Verify combo default is set correctly (not None)
    params = amicli.get_node_parameters("PeakFit.0")
    assert params["Model"] == "Gaussian"

    # Change to Lorentzian
    result = amicli.set_node_parameters("PeakFit.0", {"Model": "Lorentzian"})
    assert result["Model"] == "Lorentzian"

    node = amicli.graph.nodes["PeakFit.0"]["node"]
    assert node.values["Model"] == "Lorentzian"


@pytest.mark.asyncio
async def test_node_info(amicli):
    """Test getting node info including inputs/outputs."""
    amicli.create_node("Roi2D")

    info = amicli.node_info("Roi2D.0")
    assert info["type"] == "Roi2D"
    assert "In" in info["inputs"]
    assert "Out" in info["outputs"]
    assert "state" in info


@pytest.mark.asyncio
async def test_get_graph_state(amicli):
    """Test getting full graph state."""
    amicli.ensure_source("cspad")
    amicli.create_node("Roi2D")
    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")
    await asyncio.sleep(0.1)

    state = amicli.get_graph_state()
    assert "nodes" in state
    assert "connections" in state
    assert "sources" in state

    node_names = [n["name"] for n in state["nodes"]]
    assert "cspad" in node_names
    assert "Roi2D.0" in node_names

    assert len(state["connections"]) == 1
    conn = state["connections"][0]
    assert conn["from"] == "cspad"
    assert conn["to"] == "Roi2D.0"


@pytest.mark.asyncio
async def test_get_graph_errors_no_errors(amicli):
    """Test that get_graph_errors returns empty list when no errors."""
    errors = amicli.get_graph_errors()
    assert errors == []


@pytest.mark.asyncio
async def test_get_graph_errors_with_exception(amicli):
    """Test that get_graph_errors returns errors when nodes have exceptions."""
    amicli.create_node("Roi2D")

    node = amicli.graph.nodes["Roi2D.0"]["node"]
    node.setException("test error message")

    errors = amicli.get_graph_errors()
    assert len(errors) == 1
    assert errors[0]["node"] == "Roi2D.0"
    assert errors[0]["error"] == "test error message"
    assert errors[0]["exception_type"] == "str"


@pytest.mark.asyncio
async def test_validate_graph_ok(amicli):
    """Test validation passes for fully connected graph."""
    amicli.ensure_source("cspad")
    amicli.create_node("Roi2D")
    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")
    await asyncio.sleep(0.1)

    issues = amicli.validate_graph()
    assert issues == []


@pytest.mark.asyncio
async def test_validate_graph_disconnected(amicli):
    """Test validation reports disconnected required inputs."""
    amicli.create_node("Roi2D")

    issues = amicli.validate_graph()
    assert len(issues) > 0
    # Should mention the disconnected terminal
    assert any("Roi2D.0" in issue for issue in issues)


@pytest.mark.asyncio
async def test_save_load_graph(amicli, tmp_path):
    """Test saving and loading a graph preserves state."""
    amicli.ensure_source("cspad")
    amicli.create_node("Roi2D")
    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")
    await asyncio.sleep(0.1)

    filepath = str(tmp_path / "test_graph.fc")
    amicli.save_graph(filepath)
    assert os.path.exists(filepath)

    import networkx as nx

    for name, node in list(amicli.chart._graph.nodes(data="node")):
        if node is not None:
            node.close(emit=False)
    amicli.chart._graph = nx.MultiDiGraph()
    assert amicli.get_graph_state()["nodes"] == []

    amicli.load_graph(filepath)

    state = amicli.get_graph_state()
    node_names = [n["name"] for n in state["nodes"]]
    assert "cspad" in node_names
    assert "Roi2D.0" in node_names
    assert len(state["connections"]) == 1


@pytest.mark.asyncio
async def test_list_node_types(amicli):
    """Test listing available node types."""
    types = amicli.list_node_types()
    assert len(types) > 0

    type_names = [t["type"] for t in types]
    assert "Roi2D" in type_names
    assert "Projection" in type_names
    assert "Binning" in type_names


@pytest.mark.asyncio
async def test_list_sources(amicli):
    """Test listing available data sources."""
    sources = amicli.list_sources()
    assert len(sources) > 0
    assert "cspad" in sources
    assert "laser" in sources
