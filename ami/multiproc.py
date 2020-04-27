import os
import sys
import warnings
import multiprocessing as _mp
from multiprocessing import * # noqa
try:
    if 'SPT_NOENV' not in os.environ:
        os.environ['SPT_NOENV'] = '1'
    import setproctitle
except ImportError:
    setproctitle = None


def check_mp_start_method():
    if sys.platform == 'darwin':
        method = _mp.get_start_method(allow_none=True)
        if method is None:
            _mp.set_start_method('spawn')
        elif method != 'spawn':
            warnings.warn("AMI may not work properly on macOS with the %s start method" % _mp.get_start_method())


class Process(_mp.Process):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={},
                 *, daemon=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon)
        self.procname = name

    def run(self):
        if self._target:
            if self.procname is not None:
                setproctitle.setproctitle(self.procname)
            self._target(*self._args, **self._kwargs)
