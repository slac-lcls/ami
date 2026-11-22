"""Tests for how the editor's Flowchart receives the manager's (graphinfo) and the node processes'
(checkpoint) messages: blocking first read, then QSocketNotifier handlers that drain the socket.

The peers are plain XPUB sockets, so no backend or broker is needed."""

import logging
import pickle
import shutil
import tempfile
from types import SimpleNamespace

import pytest
import zmq

from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.manager_client import InlineManagerClient


@pytest.fixture
def receiver(qtbot):
    tmp = tempfile.mkdtemp()
    ctx = zmq.Context()
    info = ctx.socket(zmq.XPUB)
    info.bind(f"ipc://{tmp}/info")
    cp = ctx.socket(zmq.XPUB)
    cp.bind(f"ipc://{tmp}/cp")
    addr = SimpleNamespace(name="g", info=f"ipc://{tmp}/info", comm=f"ipc://{tmp}/comm")
    fc = Flowchart(broker_addr=f"ipc://{tmp}/broker", graphmgr_addr=addr, checkpoint_addr=f"ipc://{tmp}/cp")
    # a SUB socket has connected once the peer sees its subscription
    for peer in (info, cp):
        assert peer.poll(5000)
        peer.recv()
    try:
        yield fc, info, cp
    finally:
        fc.close()
        info.close(linger=0)
        cp.close(linger=0)
        ctx.term()
        shutil.rmtree(tmp, ignore_errors=True)


def send_graphinfo(sock, topic, source, payload):
    sock.send_string(topic, zmq.SNDMORE)
    sock.send_string(source, zmq.SNDMORE)
    sock.send(pickle.dumps(payload))


def send_checkpoint(sock, payload, raw=None, multipart=False):
    """The message broker republishes a checkpoint as TWO single-frame messages (topic, then body;
    MessageBroker.handle_checkpoint sends the topic without SNDMORE); ``multipart`` is the other form."""
    sock.send_string("node:", zmq.SNDMORE if multipart else 0)
    sock.send(pickle.dumps(payload) if raw is None else raw)


def wait_readable(qtbot, sock):
    qtbot.waitUntil(lambda: sock.get(zmq.EVENTS) & zmq.POLLIN, timeout=5000)


# ---------------------------------------------------------------------------
# receiveSources
# ---------------------------------------------------------------------------


def test_receive_sources_skips_other_messages_and_builds_the_library(receiver):
    fc, info, cp = receiver
    send_graphinfo(info, "event_rate", "worker0", {"g": [0.1]})
    send_graphinfo(info, "warning", "worker0", "ignored before the window exists")
    send_graphinfo(info, "sources", "manager", {"cspad": "amitypes.array.Array2d"})

    fc.receiveSources(timeout=5)

    import amitypes

    assert fc.source_library.getSourceType("cspad") is amitypes.Array2d


def test_receive_sources_times_out(receiver):
    fc, info, cp = receiver
    with pytest.raises(TimeoutError):
        fc.receiveSources(timeout=0.2)


# ---------------------------------------------------------------------------
# notifiers
# ---------------------------------------------------------------------------


def test_checkpoint_notifier_handles_messages_that_arrived_before_it_was_armed(receiver, qtbot):
    fc, info, cp = receiver
    seen = []
    fc._processCheckpoint = seen.append
    for i in range(5):
        send_checkpoint(cp, i)
    wait_readable(qtbot, fc.checkpoint)

    fc.startCheckpointNotifier()

    assert seen == [0, 1, 2, 3, 4]  # without spinning the event loop: the first drain is done when arming


def test_checkpoint_records_are_read_by_frames_not_by_message(receiver, qtbot):
    fc, info, cp = receiver
    seen = []
    fc._processCheckpoint = seen.append
    fc.startCheckpointNotifier()

    send_checkpoint(cp, "two messages", multipart=False)
    send_checkpoint(cp, "one multipart message", multipart=True)
    send_checkpoint(cp, "two messages again", multipart=False)

    qtbot.waitUntil(lambda: len(seen) == 3, timeout=5000)
    assert seen == ["two messages", "one multipart message", "two messages again"]


def test_a_record_split_across_reads_is_completed_later(receiver, qtbot):
    fc, info, cp = receiver
    seen = []
    fc._processCheckpoint = seen.append
    fc.startCheckpointNotifier()

    cp.send_string("node:")  # only the topic so far
    qtbot.wait(200)
    assert seen == []
    cp.send(pickle.dumps("complete"))

    qtbot.waitUntil(lambda: seen == ["complete"], timeout=5000)


def test_checkpoint_notifier_drains_all_waiting_messages_each_time(receiver, qtbot):
    fc, info, cp = receiver
    seen = []
    fc._processCheckpoint = seen.append
    fc.startCheckpointNotifier()

    for i in range(20):
        send_checkpoint(cp, i)
    qtbot.waitUntil(lambda: len(seen) == 20, timeout=5000)
    for i in range(20, 30):
        send_checkpoint(cp, i)
    qtbot.waitUntil(lambda: len(seen) == 30, timeout=5000)

    assert seen == list(range(30))


def test_a_bad_message_does_not_stop_the_ones_after_it(receiver, qtbot, caplog):
    fc, info, cp = receiver
    seen = []

    def process(msg):
        if msg == "raises":
            raise ValueError("boom")
        seen.append(msg)

    fc._processCheckpoint = process
    fc.startCheckpointNotifier()
    send_checkpoint(cp, "a")
    send_checkpoint(cp, "raises")
    send_checkpoint(cp, None, raw=b"not a pickle")
    send_checkpoint(cp, "b")

    with caplog.at_level(logging.ERROR):
        qtbot.waitUntil(lambda: seen == ["a", "b"], timeout=5000)
    assert caplog.text.count("Failed to handle a checkpoint message") == 2


def test_graphinfo_notifier_decodes_topic_source_and_payload(receiver, qtbot):
    fc, info, cp = receiver
    seen = []
    fc._processGraphinfo = lambda topic, source, msg: seen.append((topic, source, msg))
    fc.startGraphinfoNotifier()

    send_graphinfo(info, "warning", "worker3", {"text": "hi"})
    send_graphinfo(info, "error", "collector1", ["x"])

    qtbot.waitUntil(lambda: len(seen) == 2, timeout=5000)
    assert seen == [("warning", "worker3", {"text": "hi"}), ("error", "collector1", ["x"])]


def test_a_handler_run_inside_a_message_does_not_drain_again(receiver, qtbot):
    fc, info, cp = receiver
    depth = {"now": 0, "max": 0}
    seen = []

    def process(msg):
        depth["now"] += 1
        depth["max"] = max(depth["max"], depth["now"])
        fc._handleCheckpoint()  # what a nested event loop (a dialog) would do
        seen.append(msg)
        depth["now"] -= 1

    fc._processCheckpoint = process
    fc.startCheckpointNotifier()
    for i in range(3):
        send_checkpoint(cp, i)

    qtbot.waitUntil(lambda: len(seen) == 3, timeout=5000)
    assert seen == [0, 1, 2]
    assert depth["max"] == 1


def test_stop_receiving_stops_the_handlers(receiver, qtbot):
    fc, info, cp = receiver
    seen = []
    fc._processCheckpoint = seen.append
    fc.startCheckpointNotifier()
    send_checkpoint(cp, 1)
    qtbot.waitUntil(lambda: seen == [1], timeout=5000)

    fc.stopReceiving()
    send_checkpoint(cp, 2)
    qtbot.wait(200)

    assert seen == [1]


def test_start_receiving_loads_the_file_and_survives_a_file_that_fails(receiver, caplog):
    fc, info, cp = receiver
    loaded = []
    fc.loadFile = loaded.append

    fc.startReceiving("good.fc")

    assert loaded == ["good.fc"] and set(fc._notifiers) == {"checkpoint", "graphinfo"}

    def broken(path):
        raise KeyError("nodes")

    fc.stopReceiving()
    fc.loadFile = broken
    with caplog.at_level(logging.ERROR):
        fc.startReceiving("bad.fc")  # must not raise: the editor keeps running
    assert "Failed to load bad.fc" in caplog.text
    assert set(fc._notifiers) == {"checkpoint", "graphinfo"}


# ---------------------------------------------------------------------------
# event rate
# ---------------------------------------------------------------------------


class FakeRateHandler:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.asked = 0

    @property
    def compilerArgs(self):
        self.asked += 1
        if self.asked <= self.fail_times:
            raise TimeoutError("manager down")
        return {"num_workers": 1}


class FakeLabel:
    def __init__(self):
        self.text = None

    def setText(self, text):
        self.text = text


def rate_widget(fc, handler):
    label = FakeLabel()
    ctrl = SimpleNamespace(manager=InlineManagerClient(handler), graph_name="g", ui=SimpleNamespace(rateLbl=label))
    fc.widget = lambda: ctrl
    return label


def test_event_rate_waits_for_the_number_of_workers(receiver):
    fc, info, cp = receiver
    handler = FakeRateHandler()
    label = rate_widget(fc, handler)

    fc._processGraphinfo("event_rate", "worker0", {"g": [0.1, 0.2], "num_events": 10})  # asks the manager
    assert handler.asked == 1 and label.text is None and fc._num_workers == 1

    fc._processGraphinfo("event_rate", "worker0", {"g": [0.1, 0.2], "num_events": 10})
    assert label.text.startswith("Num Events: 10 Total Events/Sec: ")
    assert handler.asked == 1


def test_event_rate_asks_again_after_a_failed_request(receiver, caplog):
    fc, info, cp = receiver
    handler = FakeRateHandler(fail_times=1)
    label = rate_widget(fc, handler)

    with caplog.at_level(logging.WARNING):
        fc._processGraphinfo("event_rate", "worker0", {"g": [0.1], "num_events": 1})
    assert fc._num_workers is None and not fc._compiler_args_requested
    assert "number of workers" in caplog.text

    fc._processGraphinfo("event_rate", "worker0", {"g": [0.1], "num_events": 1})  # asks again, now works
    assert fc._num_workers == 1 and handler.asked == 2
    fc._processGraphinfo("event_rate", "worker0", {"g": [0.1], "num_events": 7})
    assert label.text.startswith("Num Events: 7")


def test_event_rate_ignores_other_graphs(receiver):
    fc, info, cp = receiver
    label = rate_widget(fc, FakeRateHandler())

    fc._processGraphinfo("event_rate", "worker0", {"other": [0.1], "num_events": 1})
    fc._processGraphinfo("event_rate", "worker0", {"other": [0.1], "num_events": 1})

    assert label.text is None
