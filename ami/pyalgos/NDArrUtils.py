try:
    import psana
    if hasattr(psana, '_psana'):
        from Detector.GlobalUtils import *               # noqa ignore=F405
        from pyimgalgos.GlobalUtils import *             # noqa ignore=F405
        from CalibManager.GlobalUtils import arr_rot_n90 # noqa ignore=F401
    else:
        from psana.pyalgos.generic.NDArrUtils import *   # noqa ignore=F405
except ImportError:
    import numpy as np

    def info_ndarr(nda, name='', first=0, last=5):
        _name = '%s ' % name if name != '' else name
        s = ''
        gap = '\n' if (last-first) > 10 else ' '
        if nda is None:
            s = '%sNone' % _name
        elif isinstance(nda, tuple):
            s += info_ndarr(np.array(nda), 'ndarray from tuple: %s' % name)
        elif isinstance(nda, list):
            s += info_ndarr(np.array(nda), 'ndarray from list: %s' % name)
        elif not isinstance(nda, np.ndarray):
            s = '%s%s' % (_name, type(nda))
        else:
            a = '' if last == 0 else\
                '%s%s' % (str(nda.ravel()[first:last]).rstrip(']'), '...]' if nda.size > last else ']')
            s = '%sshape:%s size:%d dtype:%s%s%s' % (_name, str(nda.shape), nda.size, nda.dtype, gap, a)
        return s
