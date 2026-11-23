"""Run graph manager requests off the GUI thread without asyncio.

The editor talks to the graph manager over a REQ/REP socket.  Doing that on the GUI thread blocks the
editor for as long as the manager takes to answer, so requests are run on one worker thread instead and
their results are handed back to the GUI thread through a queued Qt signal.

``ManagerClient.submit(fn, on_done, on_error)`` is the whole API::

    client.submit(lambda mgr: mgr.graphVersion, on_done=self.versionKnown)

``fn`` runs on the worker thread with the (synchronous) ``GraphCommHandler``; ``on_done(result)`` or
``on_error(exc)`` run later on the GUI thread.  Requests run strictly in submit order.  The returned
``concurrent.futures.Future`` resolves on the GUI thread right after the callback, so a thread other
than the GUI thread (an MCP tool, for instance) can wait on it.  NEVER wait on it from the GUI thread:
the result is delivered by the GUI thread's event loop, so that would deadlock.

``InlineManagerClient`` has the same API but runs everything immediately on the calling thread; it is
for tests that use a fake manager handler.
"""

import concurrent.futures
import logging
import queue
import sys

import zmq
from qtpy import QtCore

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0  # seconds a single manager request may take

_STOP = object()


def _report(on_done, on_error, result=None, exc=None):
    """Call the user callback, never letting an exception in it escape."""
    try:
        if exc is not None:
            if on_error is not None:
                on_error(exc)
        elif on_done is not None:
            on_done(result)
    except Exception:
        logger.exception("Exception in ManagerClient callback")


def report_failure(exc):
    """Print a traceback for ``exc`` the way an unhandled exception in a Qt slot is printed
    (``sys.excepthook``).  For callers that do not wait for a request and so have nobody to raise to."""
    sys.excepthook(type(exc), exc, exc.__traceback__)


def report_failed(future):
    """Done-callback for a future nobody waits on: print its exception, if it has one."""
    if not future.cancelled() and future.exception() is not None:
        report_failure(future.exception())


def done_future(result=None):
    """An already resolved ``concurrent.futures.Future``.  (The Futures this module hands out resolve on the
    GUI thread; never wait for one there with ``result()``.)"""
    future = concurrent.futures.Future()
    future.set_result(result)
    return future


class _Request:
    __slots__ = ("fn", "on_done", "on_error", "future")

    def __init__(self, fn, on_done, on_error, future):
        self.fn = fn
        self.on_done = on_done
        self.on_error = on_error
        self.future = future


class _Worker(QtCore.QThread):
    """The thread that owns the handler.  ZMQ sockets are not thread-safe, so the handler is created,
    used and closed only in here."""

    # (request, result, exception)
    finished_request = QtCore.Signal(object, object, object)

    def __init__(self, handler_factory, timeout, parent=None):
        super().__init__(parent)
        self._factory = handler_factory
        self._timeout = timeout
        self._queue = queue.Queue()
        self._handler = None

    def put(self, item):
        self._queue.put(item)

    def drain(self):
        """Remove and return the requests that have not started yet."""
        pending = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return pending
            if item is not _STOP:
                pending.append(item)

    def _open(self):
        handler = self._factory()
        sock = getattr(handler, "_sock", None)
        if sock is not None and self._timeout is not None:
            ms = int(self._timeout * 1000)
            sock.setsockopt(zmq.RCVTIMEO, ms)
            sock.setsockopt(zmq.SNDTIMEO, ms)
        self._handler = handler

    def _discard(self):
        handler, self._handler = self._handler, None
        if handler is None:
            return
        sock = getattr(handler, "_sock", None)
        try:
            if sock is not None:
                sock.setsockopt(zmq.LINGER, 0)
            handler.close()
        except Exception:
            logger.exception("Error closing graph manager handler")

    def run(self):
        # The handler is created by the first request, so a failure to create it is reported there.
        while True:
            req = self._queue.get()
            if req is _STOP:
                break
            if req.future.cancelled():
                continue
            result, exc = None, None
            try:
                if self._handler is None:
                    self._open()
                result = req.fn(self._handler)
            except zmq.Again:
                # A REQ socket that missed its reply can not be used again: start over.
                exc = TimeoutError("graph manager did not answer within %s s" % self._timeout)
                self._discard()
            except zmq.ZMQError as e:
                exc = e
                self._discard()
            except Exception as e:
                exc = e
            self.finished_request.emit(req, result, exc)
        self._discard()


class ManagerClient(QtCore.QObject):
    """Runs requests to the graph manager on a worker thread; see the module docstring.

    Must be created on the GUI thread (callbacks are delivered there).

    Args:
        handler_factory: zero-argument callable returning a synchronous ``GraphCommHandler``.  It is
            called inside the worker thread, and again after a timeout.
        timeout: seconds one request may wait for the manager; ``None`` waits forever.
    """

    def __init__(self, handler_factory, timeout=DEFAULT_TIMEOUT, parent=None):
        super().__init__(parent)
        self._closed = False
        self._worker = _Worker(handler_factory, timeout)
        self._worker.finished_request.connect(self._deliver, QtCore.Qt.QueuedConnection)
        self._worker.start()

    def submit(self, fn, on_done=None, on_error=None):
        """Queue ``fn(handler)`` for the worker thread; returns a ``concurrent.futures.Future``.

        If the client is closed the returned future is already cancelled and no callback is made.
        """
        future = concurrent.futures.Future()
        if self._closed:
            future.cancel()
            return future
        self._worker.put(_Request(fn, on_done, on_error, future))
        return future

    @QtCore.Slot(object, object, object)
    def _deliver(self, req, result, exc):
        if req.future.cancelled():
            return
        _report(req.on_done, req.on_error, result, exc)
        if exc is not None:
            if not req.future.done():
                req.future.set_exception(exc)
            if req.on_error is None:
                logger.error("Unhandled graph manager error: %r", exc)
        elif not req.future.done():
            req.future.set_result(result)

    def close(self, wait=True, cancel_pending=True):
        """Stop the worker.  Requests that have not started are cancelled, unless ``cancel_pending`` is
        false: then they still run, in order, before the worker stops (each is bounded by the timeout),
        so a final request such as ``destroy`` can be queued behind the ones already waiting.  The running
        request always finishes.  New submits are cancelled either way.  Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        if cancel_pending:
            for req in self._worker.drain():
                req.future.cancel()
        self._worker.put(_STOP)
        if wait:
            self._worker.wait()


class InlineManagerClient:
    """Same API as ``ManagerClient`` but runs ``fn(handler)`` and the callbacks immediately on the
    calling thread.  For tests with a fake handler."""

    def __init__(self, handler):
        self.handler = handler
        self._closed = False

    def submit(self, fn, on_done=None, on_error=None):
        future = concurrent.futures.Future()
        if self._closed:
            future.cancel()
            return future
        try:
            result = fn(self.handler)
        except Exception as e:
            _report(on_done, on_error, exc=e)
            future.set_exception(e)
            if on_error is None:
                logger.error("Unhandled graph manager error: %r", e)
        else:
            _report(on_done, on_error, result)
            future.set_result(result)
        return future

    def close(self, wait=True, cancel_pending=True):
        self._closed = True
