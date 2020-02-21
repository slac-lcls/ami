import os
import functools
import asyncio
import qtpy
from qtpy.QtCore import Slot
try:
    from asyncqt import * # noqa
except ImportError:
    # using a version of asyncqt that doesn't handle valid values of QT_API
    os.environ['QT_API'] = qtpy.API_NAME
    from asyncqt import * # noqa
    os.environ['QT_API'] = qtpy.API


def asyncSlot(*args):
    """Make a Qt async slot run on asyncio loop."""

    def outer_decorator(fn):
        @Slot(*args)
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # There is a bug in the original asyncqt where this future
            # never gets returned. This means we can't await asyncSlots.
            return asyncio.ensure_future(fn(*args, **kwargs))

        return wrapper

    return outer_decorator
