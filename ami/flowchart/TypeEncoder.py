import typing
import json
import inspect
import mypy_extensions
from amitypes import DataSource, Array1d, Array2d, Array3d


class TypeEncoder(json.JSONEncoder):

    def default(self, obj):
        if type(obj) is typing.TypeVar or \
           type(obj) is typing._GenericAlias or \
           type(obj) is typing._SpecialForm or \
           type(obj) is mypy_extensions._TypedDictMeta:
            def f():
                pass
            f.__annotations__ = {'return': obj}
            f = str(inspect.signature(f))
            f = f.replace('~', '')
            f = f.split(" ")
            f = "".join(f[2:])
            return f
        elif obj == DataSource:
            return "amitypes.DataSource"
        elif obj == Array1d:
            return "amitypes.Array1d"
        elif obj == Array2d:
            return "amitypes.Array2d"
        elif obj == Array3d:
            return "amitypes.Array3d"
        elif obj == int:
            return "int"
        elif obj == float:
            return "float"
        elif obj == bool:
            return "bool"
        else:
            raise TypeError("Unknown type:", type(obj), "obj:", obj)
