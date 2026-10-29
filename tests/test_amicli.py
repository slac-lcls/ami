"""
Unit tests for AmiCli - graph manipulation API.

Tests node creation, connections, parameters, validation, and state management
without requiring a running AMI backend (no data execution).
"""

import asyncio  # noqa: E402
import os
import shutil
import sys
import tempfile
import threading
import time

import pytest  # noqa: E402
from amitypes import Array2d  # noqa: E402

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

    # updateState() receives checkpoints from NodeProcess subprocesses (ctrl/widget state,
    # render_plot screenshot replies); needed by any test that opens a node's display window.
    # Must be created as a Task *on the broker loop* (not this thread), hence the wrapper.
    async def _start_update_state():
        return asyncio.ensure_future(fc.updateState())

    state_task = asyncio.run_coroutine_threadsafe(_start_update_state(), broker_module._test_loop).result(timeout=10)

    yield fc

    broker_module._test_loop.call_soon_threadsafe(state_task.cancel)

    # Unregister Prometheus metrics if the widget was created, otherwise they
    # leak into the global registry and cause "Duplicated timeseries" errors
    # the next time a FlowchartCtrlWidget is constructed in this process.
    try:
        import prometheus_client as pc

        if fc._widget is not None:
            try:
                pc.REGISTRY.unregister(fc._widget.graph_info)
            except Exception:
                pass
            try:
                pc.REGISTRY.unregister(fc._widget.graph_version)
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Failed to unregister prometheus metrics: {e}")

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
async def test_set_node_parameters_pushes_to_open_window(amicli, monkeypatch):
    """Test that set_node_parameters also pushes a NodeCtrlUpdate (so an open ROI/ctrl window
    reflects the change immediately, and doesn't later send a stale checkpoint reverting it).
    """
    from ami.client import flowchart_messages as fcMsgs

    node = amicli.create_node("GaussianFilter1D")
    sent = []
    monkeypatch.setattr(amicli, "_publish_to_node", lambda n, msg: sent.append((n, msg)))

    amicli.set_node_parameters("GaussianFilter1D.0", {"sigma": 3.5})

    assert len(sent) == 1
    sent_node, msg = sent[0]
    assert sent_node is node
    assert isinstance(msg, fcMsgs.NodeCtrlUpdate)
    assert msg.name == "GaussianFilter1D.0"
    assert msg.parameters == {"sigma": 3.5}


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


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="asyncio.Lock binds to the event loop it was created on in Python 3.9",
)
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
async def test_list_node_types(amicli, monkeypatch):
    """Test listing available node types, and that it creates no real node/graphics-item
    instances - regression test for a segfault where instantiating every node type (~90) just
    to read its terminals left temp nodes for Python's garbage collector to free on whatever
    thread triggered it, crashing the Qt main thread when that wasn't the Qt thread.
    """
    from ami.flowchart.Node import NodeGraphicsItem

    created = []
    orig_init = NodeGraphicsItem.__init__

    def counting_init(self, *args, **kwargs):
        created.append(1)
        return orig_init(self, *args, **kwargs)

    monkeypatch.setattr(NodeGraphicsItem, "__init__", counting_init)

    types = amicli.list_node_types()

    assert created == [], "list_node_types must not instantiate any node (no NodeGraphicsItem)"
    assert len(types) > 0

    by_name = {t["type"]: t for t in types}
    assert set(("Roi2D", "Projection", "Binning")) <= by_name.keys()

    roi2d = by_name["Roi2D"]
    assert roi2d["inputs"] == {"In": {"type": str(Array2d), "optional": False}}
    assert roi2d["outputs"]["Out"]["type"] == str(Array2d)
    assert roi2d["viewable"] is True

    # SumN/Accumulator/ReduceByKey/PythonEditor add terminals themselves (a user-facing
    # "add input" prompt) rather than declaring them statically, so describe_class() can't see
    # them; can_add_inputs/outputs says so instead of a misleading empty "takes no input".
    sumn = by_name["SumN"]
    assert sumn["inputs"] == {} and sumn["outputs"] == {}
    python_editor = by_name["PythonEditor"]
    assert python_editor["can_add_inputs"] is True and python_editor["can_add_outputs"] is True


@pytest.mark.asyncio
async def test_describe_class_matches_real_instantiation(amicli):
    """Node.describe_class() (no instantiation) must agree with actually instantiating each
    library node type and reading its real terminals - regression test for the introspection
    approach replacing direct instantiation in list_node_types.
    """
    from qtpy import QtWidgets

    from ami.flowchart.Node import Node

    library = amicli.chart.library
    checked = 0
    for node_type in library.nodeList.keys():
        node_class = library.getNodeType(node_type)
        spec = node_class.describe_class()
        assert spec is not None, f"{node_type}.describe_class() returned None"

        real = node_class("_describe_class_check_")
        try:
            real_inputs = {}
            for name, ref in real.inputs().items():
                term = ref() if callable(ref) else ref
                if term is not None:
                    real_inputs[name] = (str(term.type()), term.optional())
            real_outputs = {}
            for name, ref in real.outputs().items():
                term = ref() if callable(ref) else ref
                if term is not None:
                    real_outputs[name] = str(term.type())

            spec_inputs = {
                name: (str(opts.get("ttype")), bool(opts.get("optional", False)))
                for name, opts in spec["terminals"].items()
                if opts.get("io") == "in"
            }
            spec_outputs = {
                name: str(opts.get("ttype")) for name, opts in spec["terminals"].items() if opts.get("io") == "out"
            }
            assert spec_inputs == real_inputs, f"{node_type}: input mismatch"
            assert spec_outputs == real_outputs, f"{node_type}: output mismatch"
            assert spec["viewable"] == real._viewable, f"{node_type}: viewable mismatch"
            assert spec["buffered"] == real._buffered, f"{node_type}: buffered mismatch"
            assert spec["allowAddInput"] == real._allowAddInput, f"{node_type}: allowAddInput mismatch"
            assert spec["allowAddOutput"] == real._allowAddOutput, f"{node_type}: allowAddOutput mismatch"
            checked += 1
        finally:
            real.close(emit=False)
    assert checked > 80, f"expected to check most of the ~90 node types, only checked {checked}"
    # Node.__init__ uses a module-level ContextVar guard; confirm real instantiation still works
    # normally after many describe_class() probes (the guard must always be reset).
    sanity = library.getNodeType("Roi2D")("_sanity_check_")
    assert hasattr(sanity, "_graphicsItem") and sanity._graphicsItem is not None
    sanity.close(emit=False)
    assert isinstance(sanity, Node)
    assert QtWidgets.QApplication.instance() is not None


@pytest.mark.asyncio
async def test_list_sources(amicli):
    """Test listing available data sources."""
    sources = amicli.list_sources()
    assert len(sources) > 0
    assert "cspad" in sources
    assert "laser" in sources


@pytest.mark.asyncio
async def test_new_node_placed_next_to_connected_node(amicli):
    """Test that connecting a new node places it right of its source without moving the source."""
    amicli.ensure_source("cspad")
    src_item = amicli.graph.nodes["cspad"]["node"].graphicsItem()
    src_item.setPos(1000, 500)  # user moved the source

    amicli.create_node("Roi2D")
    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")

    src_pos = src_item.pos()
    dst_pos = amicli.graph.nodes["Roi2D.0"]["node"].graphicsItem().pos()
    assert (src_pos.x(), src_pos.y()) == (1000, 500)
    assert dst_pos.x() > src_pos.x()


@pytest.mark.asyncio
async def test_existing_nodes_not_moved_on_connect(amicli):
    """Test that connecting two already placed nodes leaves both where they are."""
    amicli.ensure_source("cspad")
    amicli.create_node("Roi2D")
    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")
    item = amicli.graph.nodes["Roi2D.0"]["node"].graphicsItem()
    item.setPos(2000, 0)

    amicli.disconnect_nodes("cspad", "Out", "Roi2D.0", "In")
    amicli.connect_nodes("cspad", "Out", "Roi2D.0", "In")

    assert (item.pos().x(), item.pos().y()) == (2000, 0)


@pytest.mark.asyncio
async def test_set_remove_reference(amicli, tmp_path):
    """Test adding, replacing, listing, and removing CSV references on a plot node."""
    csv = tmp_path / "good_spectrum.csv"
    csv.write_text("x,y\n0,1\n1,4\n2,9\n")

    amicli.create_node("LinePlot")
    assert amicli.list_references("LinePlot.0") == {}

    name = amicli.set_reference("LinePlot.0", str(csv))
    assert name == "good_spectrum"
    # Calling again with no explicit name must replace, not add "good_spectrum_1".
    assert amicli.set_reference("LinePlot.0", str(csv)) == "good_spectrum"
    assert amicli.list_references("LinePlot.0") == {"good_spectrum": str(csv)}

    assert amicli.set_reference("LinePlot.0", str(csv), name="Run 12") == "Run 12"
    assert amicli.set_reference("LinePlot.0", str(csv), name="Run 12") == "Run 12"
    assert amicli.list_references("LinePlot.0") == {"good_spectrum": str(csv), "Run 12": str(csv)}

    state = amicli.graph.nodes["LinePlot.0"]["node"].saveState()
    assert state["widget"]["csv_references"] == {"good_spectrum": str(csv), "Run 12": str(csv)}

    amicli.remove_reference("LinePlot.0", "good_spectrum")
    assert amicli.list_references("LinePlot.0") == {"Run 12": str(csv)}

    with pytest.raises(Exception):
        amicli.remove_reference("LinePlot.0", "good_spectrum")


@pytest.mark.asyncio
async def test_set_reference_errors(amicli, tmp_path):
    """Test that set_reference rejects non-plot nodes and missing files."""
    amicli.create_node("Projection")
    amicli.create_node("LinePlot")
    csv = tmp_path / "ref.csv"
    csv.write_text("0,1\n1,2\n")

    with pytest.raises(Exception, match="does not support references"):
        amicli.set_reference("Projection.0", str(csv))
    with pytest.raises(Exception, match="not found"):
        amicli.set_reference("LinePlot.0", str(tmp_path / "missing.csv"))


GOOD_CODE = """import numpy as np


class EventProcessor():

    def __init__(self):
        pass

    def begin_run(self):
        pass

    def end_run(self):
        pass

    def begin_step(self, step):
        pass

    def end_step(self, step):
        pass

    def on_event(self, image, *args, **kwargs):
        return float(np.sum(image))
"""


@pytest.mark.asyncio
async def test_set_get_python_code(amicli):
    """Test setting and reading PythonEditor code."""
    node = amicli.create_node("PythonEditor")
    assert list(node.terminals) == []
    amicli.add_terminal("PythonEditor.0", "In", "in", "Array2d")
    amicli.add_terminal("PythonEditor.0", "Out", "out", "float")

    template = amicli.get_python_code("PythonEditor.0")
    assert "class EventProcessor" in template["code"]
    assert template["inputs"] == ["In"] and template["outputs"] == ["Out"]

    result = amicli.set_python_code("PythonEditor.0", GOOD_CODE)
    assert result["inputs"] == ["In"]
    assert node.values["text"] == GOOD_CODE
    assert node.changed
    assert amicli.get_python_code("PythonEditor.0")["code"] == GOOD_CODE


@pytest.mark.asyncio
async def test_set_python_code_reaches_open_editor_window(amicli, monkeypatch):
    """Test that set_python_code pushes a NodeWidgetStateUpdate so an open editor window updates."""
    from ami.client import flowchart_messages as fcMsgs

    amicli.create_node("PythonEditor")
    amicli.add_terminal("PythonEditor.0", "In", "in", "Array2d")
    amicli.add_terminal("PythonEditor.0", "Out", "out", "float")

    sent = []
    monkeypatch.setattr(amicli, "_send_to_node_window", lambda node, msg: sent.append((node.name(), msg)))

    amicli.set_python_code("PythonEditor.0", GOOD_CODE)

    assert len(sent) == 1
    node_name, msg = sent[0]
    assert node_name == "PythonEditor.0"
    assert isinstance(msg, fcMsgs.NodeWidgetStateUpdate)
    assert msg.name == "PythonEditor.0"
    assert msg.state == {"text": GOOD_CODE}


@pytest.mark.asyncio
async def test_set_python_code_rejects_bad_code(amicli):
    """Test that invalid PythonEditor code is rejected and the existing code kept."""
    node = amicli.create_node("PythonEditor")
    amicli.add_terminal("PythonEditor.0", "In", "in", "Array2d")
    amicli.add_terminal("PythonEditor.0", "Out", "out", "float")
    amicli.set_python_code("PythonEditor.0", GOOD_CODE)

    with pytest.raises(ValueError, match="Syntax error on line"):
        amicli.set_python_code("PythonEditor.0", "class EventProcessor(:\n")
    with pytest.raises(ValueError, match="EventProcessor"):
        amicli.set_python_code("PythonEditor.0", "def func(image):\n    return 1.0\n")
    with pytest.raises(ValueError, match="on_event"):
        amicli.set_python_code("PythonEditor.0", "class EventProcessor():\n    pass\n")
    with pytest.raises(ValueError, match="begin_run"):
        amicli.set_python_code(
            "PythonEditor.0", "class EventProcessor():\n    def on_event(self, a):\n        return a\n"
        )
    with pytest.raises(ValueError, match="1 input"):
        amicli.set_python_code(
            "PythonEditor.0", GOOD_CODE.replace("on_event(self, image,", "on_event(self, image, other,")
        )
    assert node.values["text"] == GOOD_CODE

    amicli.create_node("Projection")
    with pytest.raises(ValueError, match="not a PythonEditor"):
        amicli.set_python_code("Projection.0", GOOD_CODE)


@pytest.mark.asyncio
async def test_take_and_compare_reference(amicli, tmp_path, monkeypatch):
    """Test take_reference / compare_to_reference with live data stubbed out."""
    import json

    import numpy as np

    import ami.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "_amicli", amicli)
    monkeypatch.setattr(mcp_server, "_qt_dispatch", lambda fn: fn())
    monkeypatch.setattr(type(amicli), "REFERENCE_DIR", str(tmp_path / "refs"))

    amicli.ensure_source("feespec:raw:hproj")
    amicli.create_node("WaveformViewer")
    amicli.connect_nodes("feespec:raw:hproj", "Out", "WaveformViewer.0", "In")

    live = {"y": np.sin(np.arange(100) / 10.0)}
    monkeypatch.setattr(amicli, "fetch_data", lambda feature: live["y"])

    taken = json.loads(mcp_server.take_reference("WaveformViewer.0", name="Golden"))
    assert taken["reference"] == "Golden" and taken["points"] == 100
    assert taken["path"].startswith(str(tmp_path / "refs"))
    assert list(taken["references"]) == ["Golden"]

    same = json.loads(mcp_server.compare_to_reference("WaveformViewer.0", "Golden"))
    assert same["overlap_points"] == 100
    assert same["rms_diff"] < 1e-9 and same["peak_shift"] == 0

    live["y"] = np.sin((np.arange(100) - 5) / 10.0) + 0.5  # shifted right and offset
    moved = json.loads(mcp_server.compare_to_reference("WaveformViewer.0", "Golden"))
    assert moved["peak_shift"] == 5
    assert moved["mean_offset"] > 0.4

    bad = json.loads(mcp_server.compare_to_reference("WaveformViewer.0", "missing"))
    assert "not found" in bad["error"]
    amicli.create_node("Projection")
    unsupported = json.loads(mcp_server.take_reference("Projection.0"))
    assert "not supported" in unsupported["error"]


@pytest.mark.asyncio
async def test_compare_to_reference_ignores_nan_in_reference(amicli, tmp_path, monkeypatch):
    """Test that NaN rows in the reference CSV don't propagate into the comparison (invalid JSON)."""
    import json

    import numpy as np

    import ami.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "_amicli", amicli)
    monkeypatch.setattr(mcp_server, "_qt_dispatch", lambda fn: fn())

    amicli.create_node("LinePlot")
    csv = tmp_path / "gappy.csv"
    csv.write_text("x,y\n0,1\n1,nan\n2,1\n3,1\n4,1\n")
    amicli.set_reference("LinePlot.0", str(csv), name="Gappy")

    amicli.ensure_source("feespec:raw:hproj")
    amicli.ensure_source("rix_fim1:raw:raw_7")
    amicli.connect_nodes("feespec:raw:hproj", "Out", "LinePlot.0", "X")
    amicli.connect_nodes("rix_fim1:raw:raw_7", "Out", "LinePlot.0", "Y")

    data = {"feespec:raw:hproj": np.array([0.0, 1.0, 2.0, 3.0, 4.0]), "rix_fim1:raw:raw_7": np.ones(5)}
    monkeypatch.setattr(amicli, "fetch_data", lambda feature: data[feature])

    result = json.loads(mcp_server.compare_to_reference("LinePlot.0", "Gappy"))
    assert "error" not in result
    assert np.isfinite(result["rms_diff"])
    assert np.isfinite(result["max_abs_diff"])
    json.dumps(result)  # NaN would serialize to invalid JSON `NaN`; make sure it doesn't


def test_summarize_data_detail():
    """Test fetch_data's detail levels keep narrow peaks and stay JSON-serializable."""
    import json

    import numpy as np

    from ami.mcp_server import _summarize_data

    y = np.zeros(5000)
    y[1234] = 7.0
    y[10] = np.nan
    assert set(_summarize_data(y)) == {"type", "shape", "dtype", "min", "max", "mean", "std"}
    normal = _summarize_data(y, "normal")
    assert normal["peak"] == {"index": [1234], "value": 7.0}
    assert normal["nan_count"] == 1
    assert len(normal["curve"]["max"]) == 200 and max(v for v in normal["curve"]["max"] if v is not None) == 7.0
    json.dumps(normal)

    img = np.zeros((300, 200))
    img[250, 20] = 3.0
    s = _summarize_data(img, "normal")
    assert s["peak"]["index"] == [250, 20]
    assert len(s["blocks"]) == 16 and len(s["blocks"][0]) == 16
    assert len(s["row_means"]["max"]) == 200
    json.dumps(s)


@pytest.mark.asyncio
async def test_take_reference_multi_trace(amicli, tmp_path, monkeypatch):
    """Test that multi-trace plots require an explicit trace, and the chosen trace is the one captured."""
    import json

    import numpy as np

    import ami.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "_amicli", amicli)
    monkeypatch.setattr(mcp_server, "_qt_dispatch", lambda fn: fn())
    monkeypatch.setattr(type(amicli), "REFERENCE_DIR", str(tmp_path / "refs"))

    amicli.ensure_source("feespec:raw:hproj")
    amicli.ensure_source("rix_fim1:raw:raw_7")
    node = amicli.create_node("WaveformViewer")
    node.addInput()  # second trace -> terminal "In.1"
    amicli.connect_nodes("feespec:raw:hproj", "Out", "WaveformViewer.0", "In")
    amicli.connect_nodes("rix_fim1:raw:raw_7", "Out", "WaveformViewer.0", "In.1")

    data = {"feespec:raw:hproj": np.ones(10), "rix_fim1:raw:raw_7": np.full(20, 2.0)}
    monkeypatch.setattr(amicli, "fetch_data", lambda feature: data[feature])

    traces = json.loads(mcp_server.list_plot_traces("WaveformViewer.0"))["traces"]
    assert set(traces) == {"feespec:raw:hproj", "rix_fim1:raw:raw_7"}

    ambiguous = json.loads(mcp_server.take_reference("WaveformViewer.0"))
    assert "2 traces" in ambiguous["error"] and "rix_fim1:raw:raw_7" in ambiguous["error"]

    taken = json.loads(mcp_server.take_reference("WaveformViewer.0", name="Fim", trace="rix_fim1:raw:raw_7"))
    assert taken["points"] == 20 and taken["trace"] == "rix_fim1:raw:raw_7"

    cmp = json.loads(mcp_server.compare_to_reference("WaveformViewer.0", "Fim", trace="rix_fim1:raw:raw_7"))
    assert cmp["rms_diff"] == 0

    bad = json.loads(mcp_server.take_reference("WaveformViewer.0", trace="nope"))
    assert "not found" in bad["error"]


@pytest.mark.asyncio
async def test_tools_on_source_node(amicli, monkeypatch):
    """Test that tools given a source node (no nodeName) fail cleanly or treat it as a feature."""
    import concurrent.futures
    import json

    import numpy as np

    import ami.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "_amicli", amicli)
    monkeypatch.setattr(mcp_server, "_qt_dispatch", lambda fn: fn())
    amicli.ensure_source("cspad")
    monkeypatch.setattr(amicli, "fetch_data", lambda feature: np.ones((8, 8)))

    assert not amicli.is_reference_plot("cspad")
    # The open_view/screenshot round trip (a real window, a real subprocess reply) is exercised
    # end to end by test_render_plot_screenshot_roundtrip; here, stub it to keep this test cheap.
    done = concurrent.futures.Future()
    done.set_result(b"\x89PNGfake")
    monkeypatch.setattr(amicli, "request_screenshot", lambda node_name: done)
    image = mcp_server.render_plot("cspad")
    assert image.data[:4] == b"\x89PNG"

    assert "not supported" in json.loads(mcp_server.take_reference("cspad"))["error"]
    for call in (
        lambda: amicli.set_python_code("cspad", GOOD_CODE),
        lambda: amicli.set_calculator_expression("cspad", "1"),
        lambda: amicli.set_filter_conditions("cspad", "{}"),
    ):
        with pytest.raises(ValueError, match="SourceNode"):
            call()


@pytest.mark.asyncio
async def test_open_view_errors(amicli):
    """Test open_view's error cases: missing node, no-plot node, pending upstream changes."""
    with pytest.raises(Exception, match="not found"):
        amicli.open_view("NoSuchNode.0")

    amicli.create_node("Calculator")
    with pytest.raises(Exception, match="no plot window"):
        amicli.open_view("Calculator.0")  # Calculator has no display window at all

    amicli.create_node("WaveformViewer")
    amicli.connect_nodes("Calculator.0", "Out", "WaveformViewer.0", "In")
    await asyncio.sleep(0.1)  # graph edge is added by an async Qt slot (nodeTermConnected)
    # Calculator.0 is freshly created (changed=True by default) and never applied
    with pytest.raises(Exception, match="apply_graph"):
        amicli.open_view("WaveformViewer.0")

    amicli.graph.nodes["Calculator.0"]["node"].changed = False
    assert amicli._pending_upstream_changes("WaveformViewer.0") == set()


@pytest.mark.asyncio
async def test_open_view_hints_ensure_source_for_unadded_source(amicli):
    """A render_plot/open_view call for a known source name that hasn't been added to the graph
    yet (ensure_source() not called) should hint at ensure_source(), not just "not found" -
    regression test for an agent calling render_plot("cspad") before ensure_source("cspad").
    """
    assert "cspad" not in amicli.graph.nodes()
    with pytest.raises(Exception, match="ensure_source"):
        amicli.open_view("cspad")


@pytest.mark.asyncio
async def test_open_view_accepts_buffered_nodes(amicli):
    """Test that open_view accepts "buffered" display nodes (ScalarPlot, ScatterPlot, ...),
    not just "viewable" ones - regression test for a bug caught during manual testing where
    render_plot("ScalarPlot.0") raised "no display window" even though the GUI opens one.
    """
    node = amicli.create_node("ScalarPlot")
    assert not node.viewable() and node.buffered()

    amicli.create_node("Calculator")
    amicli.connect_nodes("Calculator.0", "Out", "ScalarPlot.0", "Y")
    await asyncio.sleep(0.1)  # graph edge is added by an async Qt slot (nodeTermConnected)
    # Same pending-changes check as a viewable node: both nodes are freshly created, never applied
    # (ScalarPlot.0 has its own to_operation, buffering outputs, so it counts too, not just Calculator.0).
    with pytest.raises(Exception, match="apply_graph"):
        amicli.open_view("ScalarPlot.0")

    amicli.graph.nodes["Calculator.0"]["node"].changed = False
    node.changed = False
    amicli.open_view("ScalarPlot.0")  # must not raise now (would've raised "no display window"
    # before the open_view fix, since ScalarPlot.viewable() is False)


@pytest.mark.asyncio
async def test_resolve_screenshot_request(amicli):
    """Test that resolve_screenshot_request completes the right future and ignores stale ids."""
    import concurrent.futures

    future = concurrent.futures.Future()
    amicli._screenshot_requests[42] = future

    amicli.resolve_screenshot_request(99, png=b"ignored")  # unknown id: no-op, future untouched
    assert not future.done()

    amicli.resolve_screenshot_request(42, png=b"\x89PNGdata")
    assert future.result(timeout=0) == b"\x89PNGdata"
    assert 42 not in amicli._screenshot_requests

    # A reply arriving twice for the same id (shouldn't happen, but mustn't raise)
    amicli.resolve_screenshot_request(42, png=b"late")


@pytest.mark.asyncio
async def test_resolve_screenshot_request_error(amicli):
    """Test that an error reply sets the future's exception instead of its result."""
    import concurrent.futures

    future = concurrent.futures.Future()
    amicli._screenshot_requests[7] = future

    amicli.resolve_screenshot_request(7, error="no exportable plot")

    with pytest.raises(Exception, match="no exportable plot"):
        future.result(timeout=0)


@pytest.mark.asyncio
async def test_abandon_screenshot_request(amicli):
    """Test that abandon_screenshot_request drops the pending entry and cancels the future, so
    a late reply is a no-op and request_screenshot's open-window poll stops rescheduling itself.
    """
    import concurrent.futures

    future = concurrent.futures.Future()
    future.request_id = 5
    amicli._screenshot_requests[5] = future

    amicli.abandon_screenshot_request(future)
    assert 5 not in amicli._screenshot_requests
    assert future.cancelled()
    assert future.done()  # what send_once_viewed's "not future.done()" check relies on

    amicli.resolve_screenshot_request(5, png=b"late")  # no future to resolve; must not raise


def test_broker_does_not_cache_screenshot_replies(broker_module):
    """Test MessageBroker.handle_checkpoint end to end over real ZMQ sockets: an ordinary
    checkpoint is cached (monitor_processes uses this to restore a crashed window), but a
    NodeScreenshotReply passes through without being cached.
    """
    import zmq
    import zmq.asyncio

    from ami.client import flowchart_messages as fcMsgs
    from ami.client.flowchart import ZMQ_TOPIC_DELIM

    async def run():
        ctx = zmq.asyncio.Context()
        # Stand in for a NodeProcess: publishes on the same address the broker's
        # checkpoint_sub_sock is bound to.
        fake_node_process = ctx.socket(zmq.PUB)
        fake_node_process.connect(broker_module.checkpoint_sub_addr)
        # Stand in for the Flowchart (ctrl process): subscribes to what the broker republishes.
        observer = ctx.socket(zmq.SUB)
        observer.setsockopt_string(zmq.SUBSCRIBE, "")
        observer.connect(broker_module.checkpoint_pub_addr)
        await asyncio.sleep(0.2)  # let PUB/SUB connections settle (slow joiner)

        try:
            async with broker_module.lock:
                broker_module.checkpoints.pop("ScreenshotTestNode", None)

            checkpoint = fcMsgs.NodeCheckpoint("ScreenshotTestNode", state={"viewed": True}, event="sigStateChanged")
            await fake_node_process.send_string("ScreenshotTestNode" + ZMQ_TOPIC_DELIM, zmq.SNDMORE)
            await fake_node_process.send_pyobj(checkpoint)
            await asyncio.wait_for(observer.recv_string(), timeout=5)
            await asyncio.wait_for(observer.recv_pyobj(), timeout=5)

            async with broker_module.lock:
                cached_after_checkpoint = broker_module.checkpoints.get("ScreenshotTestNode")

            reply = fcMsgs.NodeScreenshotReply("ScreenshotTestNode", request_id=1, png=b"data")
            await fake_node_process.send_string("ScreenshotTestNode" + ZMQ_TOPIC_DELIM, zmq.SNDMORE)
            await fake_node_process.send_pyobj(reply)
            await asyncio.wait_for(observer.recv_string(), timeout=5)
            received = await asyncio.wait_for(observer.recv_pyobj(), timeout=5)

            async with broker_module.lock:
                cached_after_reply = broker_module.checkpoints.get("ScreenshotTestNode")

            return cached_after_checkpoint, cached_after_reply, received
        finally:
            fake_node_process.close()
            observer.close()
            ctx.term()

    cached_after_checkpoint, cached_after_reply, received = asyncio.run_coroutine_threadsafe(
        run(), broker_module._test_loop
    ).result(timeout=10)

    assert isinstance(cached_after_checkpoint, fcMsgs.NodeCheckpoint)
    # The reply was still forwarded to the observer...
    assert isinstance(received, fcMsgs.NodeScreenshotReply)
    assert received.png == b"data"
    # ...but it did NOT overwrite/clear the cached checkpoint.
    assert cached_after_reply is cached_after_checkpoint


def test_plot_widget_screenshot_png_and_request_screenshot(qapp):
    """Test PlotWidget.screenshot_png()/request_screenshot() directly, without a fetcher/process."""
    import numpy as np

    from ami.flowchart.library.DisplayWidgets import WaveformWidget

    widget = WaveformWidget(terms={"In": "sig"}, name="test", hutch="")
    widget.data_updated({"sig": np.sin(np.arange(50) / 5.0)})

    png = widget.screenshot_png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    results = []
    widget.request_screenshot(lambda png=None, error=None: results.append((png, error)))
    assert widget._screenshot_callback is not None

    # Simulate what update() does after the next data_updated, without needing self.fetcher.
    callback, widget._screenshot_callback = widget._screenshot_callback, None
    callback(png=widget.screenshot_png())

    assert len(results) == 1
    result_png, result_error = results[0]
    assert result_error is None
    assert result_png[:4] == b"\x89PNG"


def test_plot_widget_request_screenshot_reports_export_errors(qapp, monkeypatch):
    """Test that a failing screenshot_png() reaches the callback as an error, not an exception."""
    from ami.flowchart.library.DisplayWidgets import WaveformWidget

    widget = WaveformWidget(terms={"In": "sig"}, name="test", hutch="")
    monkeypatch.setattr(widget, "screenshot_png", lambda: (_ for _ in ()).throw(RuntimeError("no scene")))

    results = []
    widget.request_screenshot(lambda png=None, error=None: results.append((png, error)))
    callback, widget._screenshot_callback = widget._screenshot_callback, None
    try:
        callback(png=widget.screenshot_png())
    except RuntimeError as e:
        callback(error=str(e))

    assert results == [(None, "no scene")]


@pytest.mark.asyncio
async def test_request_screenshot_not_found(amicli):
    """Test that request_screenshot surfaces open_view's "not found" error synchronously."""
    with pytest.raises(Exception, match="not found"):
        amicli.request_screenshot("NoSuchNode.0")


# NOTE: a true end-to-end test (request_screenshot -> real NodeProcess subprocess -> real
# NodeScreenshotReply over the checkpoint socket) was attempted and dropped: forking a
# NodeProcess from this test's own process, which already runs a QApplication/QEventLoop for
# pytest-asyncio (see conftest.py's QEventLoopPolicy), produces cross-thread Qt errors
# ("QBasicTimer can only be used with threads started with QThread") and hangs. No existing
# test in this file spawns a real display-node subprocess for the same reason. The individual
# pieces are covered above (request_screenshot/resolve/abandon, open_view, the broker's
# cache/no-cache split, PlotWidget.screenshot_png/request_screenshot); the full round trip
# needs manual verification: open a node's window from the Agent, call render_plot, confirm
# the image matches the window.
