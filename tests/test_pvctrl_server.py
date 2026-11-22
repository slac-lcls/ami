"""Tests for ami.flowchart.PvCtrlServer (thread-based p4p SharedPV, GUI work posted to the Qt thread)."""

import threading

import networkx as nx
import pytest

pytest.importorskip("p4p")

from p4p.client.thread import Context  # noqa: E402
from p4p.server import Server  # noqa: E402

import ami.flowchart.PvCtrlServer as pvmod  # noqa: E402
from ami.client import flowchart_messages as fcMsgs  # noqa: E402
from ami.flowchart.PvCtrlServer import PvCtrlServer, _ApplyHandler, _CtrlPutHandler  # noqa: E402
from ami.qt_dispatch import QtDispatcher  # noqa: E402


class FakeDispatcher:
    """Runs posted callables immediately (the real one queues them to the Qt thread)."""

    def __init__(self):
        self.posted = 0

    def post(self, fn):
        self.posted += 1
        fn()


class FakePV:
    def __init__(self):
        self.posts = []

    def post(self, val):
        self.posts.append(val)


class FakeOp:
    def __init__(self, value):
        self._value = value
        self.done_calls = []

    def value(self):
        return self._value

    def done(self, **kws):
        self.done_calls.append(kws)


class FakeStateGroup:
    def __init__(self, node):
        self.node = node
        self.states = []
        self.threads = []

    def setState(self, state):
        self.states.append(state)
        self.threads.append(threading.current_thread())
        for k, v in state.items():
            if isinstance(v, dict):
                self.node.values.setdefault(k, {}).update(v)
            else:
                self.node.values[k] = v


class FakeNode:
    uiTemplate = [
        ("n", "intSpin", {"min": 0, "max": 10}),
        ("x", "doubleSpin"),
        ("on", "check", {"group": "grp"}),
        ("path", "file_in"),  # skipped: not exposable
    ]

    def __init__(self, name):
        self._name = name
        self.values = {"n": 1, "x": 0.5, "grp": {"on": False}}
        self.changed = False
        self.stateGroup = FakeStateGroup(self)

    def name(self):
        return self._name

    def isChanged(self, *args):
        return True


class FakeSignal:
    def __init__(self):
        self.emitted = []

    def emit(self, node):
        self.emitted.append(node)


class FakeChart:
    def __init__(self):
        self._graph = nx.MultiDiGraph()
        self.sigNodeChanged = FakeSignal()
        self.sent = []

    def add(self, node):
        self._graph.add_node(node.name(), node=node)

    def sendToBroker(self, name, msg):
        self.sent.append((name, msg))


class FakeCtrlWidget:
    def __init__(self, chart):
        self.chart = chart
        self.applied = []

    def applyClicked(self):
        self.applied.append(threading.current_thread())


def _handler(chart, name="Node.0", param="n", group=None, ptype="intSpin", opts=None, dispatcher=None):
    return _CtrlPutHandler(
        name, param, group, ptype, opts or {"min": 0, "max": 10}, chart, dispatcher or FakeDispatcher()
    )


def test_put_sets_state_marks_changed_and_notifies_node_process():
    chart = FakeChart()
    node = FakeNode("Node.0")
    chart.add(node)
    pv, op = FakePV(), FakeOp(5)

    _handler(chart).put(pv, op)

    assert pv.posts == [5]
    assert op.done_calls == [{}]
    assert node.stateGroup.states == [{"n": 5}]
    assert node.changed
    assert chart.sigNodeChanged.emitted == [node]
    assert len(chart.sent) == 1
    name, msg = chart.sent[0]
    assert name == "Node.0"
    assert isinstance(msg, fcMsgs.NodeCtrlUpdate)


def test_put_grouped_param_uses_nested_state():
    chart = FakeChart()
    node = FakeNode("Node.0")
    chart.add(node)

    _handler(chart, param="on", group="grp", ptype="check", opts={}).put(FakePV(), FakeOp(True))

    assert node.stateGroup.states == [{"grp": {"on": True}}]


def test_put_clamps_to_limits():
    chart = FakeChart()
    node = FakeNode("Node.0")
    chart.add(node)
    pv = FakePV()

    _handler(chart).put(pv, FakeOp(99))
    _handler(chart).put(pv, FakeOp(-3))

    assert pv.posts == [10, 0]


def test_put_with_invalid_value_reports_error_and_does_nothing_in_gui():
    chart = FakeChart()
    node = FakeNode("Node.0")
    chart.add(node)
    op = FakeOp("not a number")

    _handler(chart).put(FakePV(), op)

    assert len(op.done_calls) == 1 and "error" in op.done_calls[0]
    assert node.stateGroup.states == []
    assert chart.sent == []


def test_put_for_a_node_that_no_longer_exists_is_ignored(caplog):
    chart = FakeChart()  # empty graph
    op = FakeOp(5)

    _handler(chart).put(FakePV(), op)

    assert op.done_calls == [{}]  # the client was still answered
    assert chart.sigNodeChanged.emitted == []
    assert chart.sent == []
    assert "no longer exists" in caplog.text


def test_put_after_reload_reaches_the_new_node_not_the_old_one():
    """KB-07: File > Open of a graph with the same node names replaced the node object."""
    chart = FakeChart()
    old = FakeNode("Node.0")
    chart.add(old)
    handler = _handler(chart)  # created while `old` was in the graph

    chart._graph.remove_node("Node.0")
    new = FakeNode("Node.0")
    chart.add(new)

    handler.put(FakePV(), FakeOp(7))

    assert old.stateGroup.states == []
    assert new.stateGroup.states == [{"n": 7}]
    assert chart.sigNodeChanged.emitted == [new]


def test_gui_update_is_posted_not_run_in_the_putting_thread():
    chart = FakeChart()
    chart.add(FakeNode("Node.0"))
    posted = []

    class Deferring:
        def post(self, fn):
            posted.append(fn)

    pv, op = FakePV(), FakeOp(4)
    _handler(chart, dispatcher=Deferring()).put(pv, op)

    # the client is answered before the GUI has done anything
    assert pv.posts == [4] and op.done_calls == [{}]
    assert chart.sigNodeChanged.emitted == [] and len(posted) == 1
    posted[0]()
    assert len(chart.sigNodeChanged.emitted) == 1


def test_apply_put_and_rpc_post_apply_clicked():
    widget = FakeCtrlWidget(FakeChart())
    handler = _ApplyHandler(widget, FakeDispatcher())
    pv, op1, op2 = FakePV(), FakeOp(1), FakeOp(None)

    handler.put(pv, op1)
    handler.rpc(pv, op2)

    assert pv.posts == [0]
    assert op1.done_calls == [{}] and op2.done_calls == [{}]
    assert len(widget.applied) == 2


def test_apply_error_is_reported_to_the_client():
    class Broken:
        def post(self, fn):
            raise RuntimeError("boom")

    op = FakeOp(1)
    _ApplyHandler(FakeCtrlWidget(FakeChart()), Broken()).put(FakePV(), op)

    assert op.done_calls[0] == {} and "boom" in op.done_calls[1]["error"]


def test_qt_dispatcher_post_runs_on_gui_thread_and_does_not_wait(qtbot):
    dispatcher = QtDispatcher()
    seen = []
    gate = threading.Event()

    def from_worker():
        # post() must return even though the GUI thread is busy waiting on this thread
        dispatcher.post(lambda: seen.append(threading.current_thread()))
        gate.set()

    t = threading.Thread(target=from_worker)
    t.start()
    assert gate.wait(5)
    t.join()
    qtbot.waitUntil(lambda: len(seen) == 1, timeout=5000)
    assert seen[0] is threading.main_thread()


def test_qt_dispatcher_post_logs_exceptions(qtbot, caplog):
    dispatcher = QtDispatcher()

    def bad():
        raise ValueError("oops")

    dispatcher.post(bad)
    qtbot.waitUntil(lambda: "Qt dispatcher exception" in caplog.text, timeout=5000)


# ---------------------------------------------------------------------------
# Real p4p server and client (isolated: nothing goes on the network)
# ---------------------------------------------------------------------------


@pytest.fixture
def pva(qtbot, monkeypatch):
    chart = FakeChart()
    node = FakeNode("Node.0")
    chart.add(node)
    widget = FakeCtrlWidget(chart)

    monkeypatch.setattr(pvmod, "Server", lambda providers: Server(providers=providers, isolate=True))
    server = PvCtrlServer(None, "g", widget)  # real QtDispatcher
    server.start()
    server.update_pvs(chart)
    ctx = Context("pva", conf=server.server.conf(), useenv=False)
    try:
        yield server, ctx, chart, node, widget
    finally:
        ctx.close()
        server.stop()


def test_pvput_reaches_the_node_in_the_gui_thread(pva, qtbot):
    server, ctx, chart, node, widget = pva
    name = "ami:ctrl:g:Node.0:n"

    assert ctx.get(name) == 1
    ctx.put(name, 5, timeout=5)

    qtbot.waitUntil(lambda: node.stateGroup.states == [{"n": 5}], timeout=5000)
    assert node.stateGroup.threads == [threading.main_thread()]
    assert chart.sigNodeChanged.emitted == [node]
    assert ctx.get(name) == 5


def test_pvput_on_apply_pv_calls_apply_clicked_in_the_gui_thread(pva, qtbot):
    server, ctx, chart, node, widget = pva

    ctx.put("ami:ctrl:g:apply", 1, timeout=5)

    qtbot.waitUntil(lambda: len(widget.applied) == 1, timeout=5000)
    assert widget.applied == [threading.main_thread()]


def test_pvput_after_the_node_was_replaced_reaches_the_new_node(pva, qtbot):
    server, ctx, chart, old, widget = pva
    chart._graph.remove_node("Node.0")
    new = FakeNode("Node.0")
    chart.add(new)

    ctx.put("ami:ctrl:g:Node.0:n", 8, timeout=5)

    qtbot.waitUntil(lambda: new.stateGroup.states == [{"n": 8}], timeout=5000)
    assert old.stateGroup.states == []
