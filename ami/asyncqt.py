import os
import qtpy
try:
    from asyncqt import * # noqa
except ImportError:
    # using a version of asyncqt that doesn't handle valid values of QT_API
    os.environ['QT_API'] = qtpy.API_NAME
    from asyncqt import * # noqa
    os.environ['QT_API'] = qtpy.API
