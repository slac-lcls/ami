import sys


def export(obj):
    mod = sys.modules[obj.__module__]
    if hasattr(mod, '__all__'):
        mod.__all__.append(obj.__name__)
    else:
        mod.__all__ = [obj.__name__]
    return obj


class Extender:
    def __init__(self, base):
        self._base = base

    def __getattr__(self, attr):
        return getattr(self._base, attr)
