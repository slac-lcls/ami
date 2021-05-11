import inspect
import numpy
import json
import typing


def _map_numpy_types():
    nptypemap = {}
    for name, dtype in inspect.getmembers(numpy, lambda x: inspect.isclass(x) and issubclass(x, numpy.generic)):
        try:
            ptype = None
            if 'time' in name:
                ptype = type(dtype(0, 'D').item())
            elif 'object' not in name:
                ptype = type(dtype(0).item())

            # if it is still a numpy dtype don't make a mapping
            if not issubclass(ptype, numpy.generic):
                nptypemap[dtype] = ptype
        except TypeError:
            pass

    return nptypemap


NumPyTypeDict = _map_numpy_types()


class TypeEncoder(json.JSONEncoder):

    def default(self, obj):
        nptopy = NumPyTypeDict.get(type(obj))
        if nptopy is not None:
            return nptopy(obj)
        elif isinstance(obj, numpy.ndarray):
            return obj.tolist()
        if inspect.isclass(obj):
            if obj.__module__ in ['builtins']:
                return obj.__name__
            else:
                return "%s.%s" % (obj.__module__, obj.__name__)
        elif isinstance(obj, typing.TypeVar):
            return "%s.%s" % (obj.__module__, obj.__name__)
        elif isinstance(obj, (typing._GenericAlias, typing._SpecialForm)):
            return str(obj)
        else:
            return json.JSONEncoder.default(self, obj)
