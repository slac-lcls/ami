import time
import dill
import numpy as np
import collections
from p4p import Type, Value
from p4p.nt import alarm, timeStamp, NTScalar


def _generate_schema(graph=True):
    if graph:
        fields = collections.OrderedDict([
            ('names', 'as'),
            ('types', 'aB'),
            ('sources', 'aB'),
            ('version', 'l'),
            ('dill', 'aB'),
        ])
        schema = [(k, v) for k, v in fields.items()]
        byte_fields = {'dill'}
        object_fields = {'sources', 'types'}
        flat_names = {
            'names':    'names',
            'types':    'types',
            'sources':  'sources',
            'version':  'version',
            'dill':     'dill',
        }
    else:
        fields = collections.OrderedDict([
            ('version', 'l'),
            ('features', 'aB'),
        ])
        schema = [(k, v) for k, v in fields.items()]
        byte_fields = set()
        object_fields = {'features'}
        flat_names = {
            'version':  'store:version',
            'features': 'store:features',
        }

    def get_type(key, value):
        if key in byte_fields:
            return NTBytes()
        elif key in object_fields:
            return NTObject()
        else:
            return NTScalar(value)

    flat_schema = {
        k: (flat_names[k], get_type(k, v)) for k, v in fields.items()
    }
    return schema, flat_schema, byte_fields, object_fields


class NTBytes:

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', 'aB'),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTBytes:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        return Value(self.type, {
            'value': np.frombuffer(value, dtype=np.ubyte),
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        V = value.value
        return V.tobytes()

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


class NTObject:

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', 'aB'),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTObject:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        return Value(self.type, {
            'value': np.frombuffer(dill.dumps(value), dtype=np.ubyte),
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        V = value.value
        return dill.loads(V.tobytes())

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


class NTGraph:
    schema, flat_schema, byte_fields, object_fields = _generate_schema()

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', ('S', None, klass.schema)),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTGraph:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        for field in self.byte_fields:
            value[field] = np.frombuffer(value[field], np.ubyte)
        for field in self.object_fields:
            value[field] = np.frombuffer(dill.dumps(value[field]), np.ubyte)
        return Value(self.type, {
            'value': value,
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        result = {}
        V = value.value
        for k in V:
            if k in klass.byte_fields:
                result[k] = V[k].tobytes()
            elif k in klass.object_fields:
                result[k] = dill.loads(V[k].tobytes())
            else:
                result[k] = V[k]
        return result

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


class NTStore:
    schema, flat_schema, byte_fields, object_fields = _generate_schema(False)

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', ('S', None, klass.schema)),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTStore:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        for field in self.byte_fields:
            value[field] = np.frombuffer(value[field], np.ubyte)
        for field in self.object_fields:
            value[field] = np.frombuffer(dill.dumps(value[field]), np.ubyte)
        return Value(self.type, {
            'value': value,
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        result = {}
        V = value.value
        for k in V:
            if k in klass.byte_fields:
                result[k] = V[k].tobytes()
            elif k in klass.object_fields:
                result[k] = dill.loads(V[k].tobytes())
            else:
                result[k] = V[k]
        return result

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


CUSTOM_TYPE_WRAPPERS = {
    'ami:export/NTBytes:1.0': NTBytes,
    'ami:export/NTObject:1.0': NTObject,
    'ami:export/NTGraph:1.0': NTGraph,
    'ami:export/NTStore:1.0': NTStore,
}
