# ref: http://stackoverflow.com/questions/4716533/how-to-attach-debugger-to-a-python-subproccess
import sys
import pdb
import PyQt5


class ForkedPdb(pdb.Pdb):
    """A Pdb subclass that may be used
    from a forked multiprocessing child
    """
    def interaction(self, *args, **kwargs):
        _stdin = sys.stdin
        try:
            sys.stdin = open('/dev/stdin')
            PyQt5.QtCore.pyqtRemoveInputHook()
            pdb.Pdb.interaction(self, *args, **kwargs)
        finally:
            sys.stdin = _stdin
            PyQt5.QtCore.pyqtRestoreInputHook()

# Use it the same way you might use the classic Pdb:
# ForkedPdb().set_trace()
