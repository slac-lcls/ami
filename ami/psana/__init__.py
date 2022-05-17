try:
    import psana
except ImportError:
    psana = None

if hasattr(psana, '_psana'):
    from .datasource import *   # noqa ignore=F405
    from .detector import *     # noqa ignore=F405
    from .interfaces import *   # noqa ignore=F405
    from .bld import *          # noqa ignore=F405
else:
    import sys
    sys.modules[__name__] = psana
