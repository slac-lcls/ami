import psana

if hasattr(psana, '_psana'):
    from pyimgalgos.HPolar import *            # noqa ignore=F405
else:
    from psana.pyalgos.generic.HPolar import * # noqa ignore=F405
