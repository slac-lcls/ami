try:
    import psana
except ImportError:
    psana = None

if hasattr(psana, '_psana'):
    from .datasource import *
    from .detector import *
    from .interfaces import *
else:
    import sys
    sys.modules[__name__] = psana
