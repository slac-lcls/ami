import re
import sys
import numpy
import psana
import inspect
import amitypes


__all__ = ['export']


def export(obj):
    mod = sys.modules[obj.__module__]
    if hasattr(mod, '__all__'):
        mod.__all__.append(obj.__name__)
    else:
        mod.__all__ = [obj.__name__]
    return obj


def is_boost(obj, name):
    otype = type(obj)
    return otype.__module__ == 'Boost.Python' and otype.__name__ == name


def is_boost_class(obj):
    return is_boost(obj, 'class')


def is_boost_function(obj):
    return is_boost(obj, 'function')


def is_hidden(obj):
    return obj.__name__.startswith('_')


def is_valid(obj):
    return not is_hidden(obj) and obj.__doc__ is not None


def get_methods(obj):
    return inspect.getmembers(obj, lambda x: inspect.ismethod(x) and not is_hidden(x))


def get_boost_methods(obj):
    return inspect.getmembers(obj, lambda x: is_boost_function(x) and is_valid(x))


def get_boost_annotations(obj):
    annotations = {}

    for name, meth in get_boost_methods(obj):
        match = re.search(fr'{name}\(.*\)\s+->\s+(?P<rtype>\S+)\s?', meth.__doc__)
        if match:
            rtype = eval(match.group('rtype'))
            if issubclass(rtype, numpy.ndarray):
                rtype = amitypes.Array1d
            annotations[name] = rtype

    return annotations


@export
def parse_cls(cls):
    if isinstance(cls, list) and cls and is_boost_class(cls[-1]):
        return cls[-1]
    else:
        return cls


@export
def parse_methods(methods):
    if methods is None:
        return []
    elif is_boost_class(parse_cls(methods)):
        return [n for n, _ in get_boost_methods(parse_cls(methods))]
    else:
        return methods


@export
def parse_annotations(annotations, overrides):
    if annotations is None:
        return {}
    elif is_boost_class(parse_cls(annotations)):
        annotations = get_boost_annotations(parse_cls(annotations))
        if overrides is not None:
            annotations.update(overrides)
        return annotations
    else:
        return annotations


@export
def make_method(name, func):
    def new_method(self, evt):
        return func(self, name, evt)

    return new_method


@export
def make_config(cfgmods):
    def new_config(self):
        cfgst = self.env.configStore()
        for cfgmod in cfgmods:
            for cfgcls in cfgmod:
                cfg = cfgst.get(cfgcls, psana.Source(self.src))
                if cfg is not None:
                    return cfg

    return property(new_config)


@export
class Extender:
    def __init__(self, base):
        self._base = base

    def __getattr__(self, attr):
        return getattr(self._base, attr)
