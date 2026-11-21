import threading
import time

import pytest
import zmq

import ami.client.flowchart_messages as fcMsgs
from ami.comm import GraphCommHandler
from ami.flowchart.broker_send import send_to_broker
from ami.flowchart.manager_client import InlineManagerClient, ManagerClient


class FakeHandler:
    """Stands in for GraphCommHandler; records which thread each call ran on."""

    def __init__(self):
        self.calls = []
        self.threads = set()
        self.closed = False

    def close(self):
        self.closed = True

    def work(self, n):
        self.threads.add(threading.current_thread())
        self.calls.append(n)
        return n * 2


@pytest.fixture
def made():
    """Handlers created by the client's factory (the factory runs in the worker thread)."""
    return []


@pytest.fixture
def client(qtbot, made):
    def factory():
        h = FakeHandler()
        h.created_in = threading.current_thread()
        made.append(h)
        return h

    c = ManagerClient(factory)
    yield c
    c.close()


def wait_done(qtbot, future, timeout=5000):
    qtbot.waitUntil(future.done, timeout=timeout)


def test_requests_run_in_submit_order(qtbot, client, made):
    results = []
    futures = [client.submit(lambda h, i=i: h.work(i), on_done=results.append) for i in range(25)]
    wait_done(qtbot, futures[-1])
    assert results == [i * 2 for i in range(25)]
    assert made[0].calls == list(range(25))
    assert [f.result() for f in futures] == results


def test_handler_lives_in_worker_thread_and_callbacks_in_gui_thread(qtbot, client, made):
    where = {}
    f = client.submit(lambda h: h.work(1), on_done=lambda r: where.setdefault("done", threading.current_thread()))
    wait_done(qtbot, f)
    main = threading.current_thread()
    assert where["done"] is main
    assert len(made) == 1
    assert made[0].created_in is not main
    assert made[0].threads == {made[0].created_in}


def test_future_is_resolved_after_the_callback(qtbot, client):
    seen = []
    f = client.submit(lambda h: h.work(3), on_done=lambda r: seen.append(("cb", f.done())))
    wait_done(qtbot, f)
    assert seen == [("cb", False)]
    assert f.result() == 6


def test_error_goes_to_on_error_and_worker_survives(qtbot, client):
    errors, results = [], []

    def boom(h):
        raise ValueError("bad request")

    f1 = client.submit(boom, on_done=results.append, on_error=errors.append)
    f2 = client.submit(lambda h: h.work(5), on_done=results.append)
    wait_done(qtbot, f2)
    assert len(errors) == 1 and isinstance(errors[0], ValueError)
    assert results == [10]
    with pytest.raises(ValueError):
        f1.result()


def test_error_without_on_error_only_fails_the_future(qtbot, client):
    def boom(h):
        raise KeyError("x")

    f = client.submit(boom)
    wait_done(qtbot, f)
    assert isinstance(f.exception(), KeyError)
    f2 = client.submit(lambda h: h.work(1))  # still accepting work
    wait_done(qtbot, f2)
    assert f2.result() == 2


def test_exception_in_callback_does_not_stop_later_callbacks(qtbot, client):
    got = []

    def bad_cb(result):
        raise RuntimeError("callback bug")

    client.submit(lambda h: h.work(1), on_done=bad_cb)
    f = client.submit(lambda h: h.work(2), on_done=got.append)
    wait_done(qtbot, f)
    assert got == [4]


def test_close_cancels_pending_and_stops_thread(qtbot, made):
    c = ManagerClient(lambda: FakeHandler())
    started = threading.Event()
    release = threading.Event()
    called = []

    def slow(h):
        started.set()
        release.wait(5)
        return "slow"

    running = c.submit(slow, on_done=called.append)
    pending = [c.submit(lambda h: h.work(1), on_done=called.append) for _ in range(3)]
    assert started.wait(5)
    threading.Timer(0.2, release.set).start()
    c.close()  # waits for the running request, drops the pending ones
    assert not c._worker.isRunning()
    assert all(p.cancelled() for p in pending)
    qtbot.waitUntil(running.done, timeout=5000)
    assert running.result() == "slow"
    assert called == ["slow"]
    # after close: nothing is accepted, nothing raised
    late = c.submit(lambda h: h.work(1), on_done=called.append)
    assert late.cancelled()
    c.close()  # idempotent


def test_failing_handler_factory_is_reported_per_request(qtbot):
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("no manager")
        return FakeHandler()

    c = ManagerClient(factory)
    try:
        errors = []
        f1 = c.submit(lambda h: h.work(1), on_error=errors.append)
        wait_done(qtbot, f1)
        assert isinstance(errors[0], OSError)
        f2 = c.submit(lambda h: h.work(2))
        wait_done(qtbot, f2)
        assert f2.result() == 4
    finally:
        c.close()


class FakeManager(threading.Thread):
    """A REP socket that ignores its first request, then answers every one with version 7."""

    def __init__(self, addr, ignore_first=True):
        super().__init__(daemon=True)
        self.addr = addr
        self.ignore_first = ignore_first
        self.seen = 0
        self.stop = threading.Event()
        self.ready = threading.Event()

    def run(self):
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REP)
        sock.setsockopt(zmq.LINGER, 0)
        sock.bind(self.addr)
        self.ready.set()
        while not self.stop.is_set():
            if not sock.poll(50):
                continue
            sock.recv_multipart()
            self.seen += 1
            if self.ignore_first and self.seen == 1:
                # REP must answer before it takes another request; rebind to forget this one
                sock.close()
                sock = ctx.socket(zmq.REP)
                sock.setsockopt(zmq.LINGER, 0)
                sock.bind(self.addr)
                continue
            sock.send_pyobj(7)
        sock.close()
        ctx.term()


def test_timeout_is_reported_and_the_worker_recovers(qtbot, tmp_path):
    addr = "ipc://%s/mgr" % tmp_path
    mgr = FakeManager(addr)
    mgr.start()
    assert mgr.ready.wait(5)
    c = ManagerClient(lambda: GraphCommHandler("g", addr), timeout=0.5)
    try:
        errors = []
        f1 = c.submit(lambda h: h.graphVersion, on_error=errors.append)
        wait_done(qtbot, f1)
        assert len(errors) == 1 and isinstance(errors[0], TimeoutError)
        # the REQ socket was rebuilt, so the next request works
        f2 = c.submit(lambda h: h.graphVersion)
        wait_done(qtbot, f2)
        assert f2.result() == 7
    finally:
        c.close()
        mgr.stop.set()
        mgr.join(5)


def test_inline_client_runs_immediately_with_same_api():
    h = FakeHandler()
    c = InlineManagerClient(h)
    got, errs = [], []
    f = c.submit(lambda m: m.work(4), on_done=got.append, on_error=errs.append)
    assert f.done() and f.result() == 8 and got == [8] and errs == []

    def boom(m):
        raise ValueError("x")

    f = c.submit(boom, on_done=got.append, on_error=errs.append)
    assert isinstance(f.exception(), ValueError) and len(errs) == 1 and got == [8]
    c.close()
    assert c.submit(lambda m: m.work(1)).cancelled()


@pytest.fixture
def pubsub():
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    sub.bind("inproc://broker_send")
    pub = ctx.socket(zmq.PUB)
    pub.connect("inproc://broker_send")
    yield pub, sub
    pub.close(linger=0)
    sub.close(linger=0)
    ctx.term()


def test_send_to_broker_frames_match_send_string_send_pyobj(pubsub):
    pub, sub = pubsub
    msg = fcMsgs.CreateNode("Projection", "Projection")
    deadline = time.time() + 5
    while not sub.poll(20):  # the first sends can be lost while the subscription propagates
        send_to_broker(pub, "Projection", msg)
        assert time.time() < deadline
    # receive the way MessageBroker does
    assert sub.recv_string() == "Projection"
    got = sub.recv_pyobj()
    assert isinstance(got, fcMsgs.CreateNode)
    assert (got.name, got.node_type) == ("Projection", "Projection")


def test_send_to_broker_sends_two_frames_in_one_message(pubsub):
    pub, sub = pubsub
    deadline = time.time() + 5
    while not sub.poll(20):
        send_to_broker(pub, "n1", fcMsgs.CloseNode())
        assert time.time() < deadline
    frames = sub.recv_multipart()
    assert len(frames) == 2 and frames[0] == b"n1"
