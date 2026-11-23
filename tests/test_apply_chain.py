"""
Apply / load / clear run as a chain of manager requests that each start when the one before has been
answered.  These tests replace the editor's ManagerClient with an InlineManagerClient around a fake
manager that records every request, so the order of the requests can be checked.
"""

import pytest


class FakeManager:
    def __init__(self):
        self.calls = []
        self.version = 1
        self.fail_on = None

    def _record(self, name, *args):
        self.calls.append(name)
        if self.fail_on == name:
            raise RuntimeError(f"fake manager failed {name}")

    @property
    def graphVersion(self):
        self._record("graphVersion")
        return self.version

    @property
    def metadata(self):
        self._record("metadata")
        return {}

    def remove(self, nodes):
        self._record("remove")

    def add(self, nodes):
        self._record("add")

    def view(self, views):
        self._record("view")

    def export(self, *args, **kwargs):
        self._record("export")

    def unview(self, views):
        self._record("unview")

    def updatePlots(self, plots):
        self._record("updatePlots")

    def destroy(self):
        self._record("destroy")

    def updatePath(self, dirs):
        self._record("updatePath")

    def update_requested_data(self, requested_data):
        self._record("update_requested_data")


@pytest.fixture
def chain(qtbot, flowchart):
    """The flowchart with cspad -> Roi2D.0, and a recording fake manager."""
    # imported here, not at module level, like the other tests do (nothing Qt is loaded at collection)
    from ami.flowchart.library.common import SourceNode
    from ami.flowchart.manager_client import InlineManagerClient

    fc, _ = flowchart
    ctrl = fc.widget()
    qtbot.addWidget(ctrl)

    ctrl.manager.close()
    fake = FakeManager()
    ctrl.manager = InlineManagerClient(fake)

    node_type = fc.source_library.getSourceType("cspad")
    source = SourceNode(name="cspad", terminals={"Out": {"io": "out", "ttype": node_type}})
    fc.addNode(node=source)
    fc.createNode("Roi2D")
    nodes = fc.nodes(data="node")
    nodes["cspad"]._outputs["Out"]().connectTo(nodes["Roi2D.0"]._inputs["In"]())
    return fc, ctrl, fake


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_apply_request_order(chain):
    fc, ctrl, fake = chain
    fc.deleted_nodes = ["Gone.0"]

    future = ctrl.applyClicked()

    assert future.done() and future.result() is None
    assert fake.calls == ["remove", "graphVersion", "add", "metadata", "graphVersion"]
    assert fc.deleted_nodes == []
    assert not any(node.changed for _, node in fc.nodes(data="node"))


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_apply_redisplays_viewed_nodes_before_reading_metadata(chain):
    fc, ctrl, fake = chain
    fc.nodes(data="node")["cspad"].viewed = True

    future = ctrl.applyClicked()

    assert future.done() and future.exception() is None
    assert fake.calls == ["graphVersion", "add", "view", "updatePlots", "metadata", "graphVersion"]


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_apply_after_manager_lost_graph_resubmits_everything(chain):
    fc, ctrl, fake = chain
    ctrl.applyClicked()
    for _, node in fc.nodes(data="node"):
        assert not node.changed

    fake.version = 0
    fake.calls.clear()
    ctrl.applyClicked()

    assert fake.calls == ["graphVersion", "add", "metadata", "graphVersion"]


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_apply_with_disconnected_node_submits_nothing(chain, monkeypatch):
    fc, ctrl, fake = chain
    fc.createNode("Roi2D")  # Roi2D.1 has no input
    from qtpy import QtWidgets

    monkeypatch.setattr(QtWidgets.QMessageBox, "show", lambda self: None)

    future = ctrl.applyClicked()

    assert future.done() and future.result() is None
    assert fake.calls == ["graphVersion"]
    assert fc.nodes(data="node")["Roi2D.0"].changed  # still waiting for an apply


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_apply_stops_when_the_manager_fails(qtbot, chain):
    fc, ctrl, fake = chain
    fake.fail_on = "add"

    with qtbot.capture_exceptions() as exceptions:
        future = ctrl.applyClicked()

    assert len(exceptions) == 1  # printed once, like an exception in a slot
    assert isinstance(future.exception(), RuntimeError)
    assert fake.calls == ["graphVersion", "add"]  # no metadata request
    assert fc.nodes(data="node")["Roi2D.0"].changed
    with pytest.raises(RuntimeError):
        future.result()


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_apply_action_redisplays_views(chain, monkeypatch):
    """The toolbar action emits triggered(checked=False); that must not reach build_views."""
    fc, ctrl, fake = chain
    fc.nodes(data="node")["cspad"].viewed = True

    ctrl.ui.actionApply.trigger()

    assert fake.calls == ["graphVersion", "add", "view", "updatePlots", "metadata", "graphVersion"]


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_load_file_order_and_future(chain, tmp_path):
    fc, ctrl, fake = chain
    path = str(tmp_path / "g.fc")
    fc.saveFile(path)
    fake.calls.clear()

    future = fc.loadFile(path)

    assert future.done() and future.exception() is None
    assert fake.calls == [
        "destroy",
        "updatePlots",
        "updatePath",
        "update_requested_data",
        "graphVersion",
        "add",
        "metadata",
        "graphVersion",
        "updatePlots",
    ], fake.calls
    assert "Roi2D.0" in fc.nodes(data="node")


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_load_missing_file_resolves_and_asks_nothing(chain, monkeypatch):
    fc, ctrl, fake = chain
    from qtpy import QtWidgets

    monkeypatch.setattr(QtWidgets.QMessageBox, "show", lambda self: None)

    future = fc.loadFile("/nonexistent/none.fc")

    assert future.done() and future.result() is None
    assert fake.calls == []


@pytest.mark.parametrize("flowchart", ["static"], indirect=True)
def test_clear_empties_the_editor_at_once(chain):
    fc, ctrl, fake = chain
    assert len(fc.nodes()) == 2

    future = ctrl.clear()

    assert len(fc.nodes()) == 0
    assert future.done() and future.exception() is None
    assert fake.calls == ["destroy", "updatePlots"]
