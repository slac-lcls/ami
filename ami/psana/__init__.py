try:
    import psana
except ImportError:
    psana = None

if hasattr(psana, '_psana'):
    from .datasource import *   # noqa ignore=F405
    from .detector import *     # noqa ignore=F405
    from .interfaces import *   # noqa ignore=F405
    from .bld import *          # noqa ignore=F405
    from .epics import *        # noqa ignore=F405
    from .scan import *         # noqa ignore=F405
    from . import event         # noqa ignore=F401
else:
    import sys
    sys.modules[__name__] = psana
