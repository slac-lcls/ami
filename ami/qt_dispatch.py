"""Qt thread dispatcher for MCP server."""

import concurrent.futures
import logging

from qtpy.QtCore import QCoreApplication, QObject, Qt, Signal, Slot

logger = logging.getLogger(__name__)


class QtDispatcher(QObject):
    """Dispatch callables from background threads to Qt main thread."""

    _execute = Signal(object, object)  # (callable, future)

    def __init__(self):
        super().__init__()
        # Connect signal to slot in main thread
        self._execute.connect(self._run, type=Qt.QueuedConnection)
        # Ensure this QObject lives in main thread
        self.moveToThread(QCoreApplication.instance().thread())

    @Slot(object, object)
    def _run(self, fn, future):
        """Execute callable in Qt main thread, set future result."""
        try:
            result = fn()
            future.set_result(result)
        except Exception as e:
            logger.exception("Qt dispatcher exception")
            future.set_exception(e)

    def dispatch(self, fn, timeout=10):
        """
        Call fn() in Qt main thread. Blocks until complete.

        Args:
            fn: Callable with no arguments that returns a result
            timeout: Max seconds to wait for result

        Returns:
            Result from fn()

        Raises:
            TimeoutError: If fn() doesn't complete in time
            Exception: Whatever fn() raised
        """
        future = concurrent.futures.Future()
        self._execute.emit(fn, future)
        return future.result(timeout=timeout)
