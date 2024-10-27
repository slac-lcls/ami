import time
import dill
import numpy as np
import collections
from p4p import Type, Value
from p4p.nt import alarm, timeStamp, NTScalar
from caproto import ChannelType


def _generate_schema(graph=True):
    if graph:
        fields = collections.OrderedDict([
            ('names', 'as'),
            ('sources', 'aB'),
            ('version', 'l'),
            ('dill', 'aB'),
        ])
        schema = [(k, v) for k, v in fields.items()]
        byte_fields = {'dill'}
        object_fields = {'sources'}
        flat_names = {
            'names':    'names',
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


class ntbool(int):
    """
    Augmented boolean with additional attributes
    * .severity
    * .status
    * .timestamp - Seconds since 1 Jan 1970 UTC as a float
    * .raw_stamp - A tuple (seconds, nanoseconds)
    * .raw - The underlying :py:class:`p4p.Value`.
    """
    raw = timestamp = None

    def __new__(cls, value):
        return int.__new__(cls, bool(value))

    def _store(self, value):
        assert isinstance(value, Value), value
        self.raw = value
        self.severity = value.get('alarm.severity', 0)
        self.status = value.get('alarm.status', 0)
        S, NS = value.get('timeStamp.secondsPastEpoch', 0), value.get('timeStamp.nanoseconds', 0)
        self.raw_stamp = S, NS
        self.timestamp = S + NS * 1e-9
        # TODO: unpack display/control
        return self

    def __repr__(self):
        return bool(self).__repr__()

    def __str__(self):
        return '%s %s' % (time.ctime(self.timestamp), self.__repr__())

    tostr = __str__


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

    def wrap(self, value, timestamp=None):
        """Wrap dictionary as Value
        """
        S, NS = divmod(float(timestamp or time.time()), 1.0)
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

    def wrap(self, value, timestamp=None):
        """Wrap dictionary as Value
        """
        S, NS = divmod(float(timestamp or time.time()), 1.0)
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

    def wrap(self, value, timestamp=None):
        """Wrap dictionary as Value
        """
        S, NS = divmod(float(timestamp or time.time()), 1.0)
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

    def wrap(self, value, timestamp=None):
        """Wrap dictionary as Value
        """
        S, NS = divmod(float(timestamp or time.time()), 1.0)
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


if bool not in NTScalar.typeMap:
    NTScalar.typeMap[bool] = ntbool


def _generate_schema_caproto(graph=True):
    if graph:
        fields = collections.OrderedDict([
            ('names', ChannelType.STRING),
            # ('sources', ChannelType.CHAR),
            ('version', ChannelType.INT),
            ('dill', ChannelType.LONG),
        ])
        schema = [(k, v) for k, v in fields.items()]
        byte_fields = {'dill'}
        object_fields = {'sources'}
        flat_names = {
            'names':    'names',
            # 'sources':  'sources',
            'version':  'version',
            'dill':     'dill',
        }
    else:
        fields = collections.OrderedDict([
            ('version', ChannelType.INT),
            # ('features', ChannelType.CHAR),
        ])
        schema = [(k, v) for k, v in fields.items()]
        byte_fields = set()
        object_fields = {'features'}
        flat_names = {
            'version':  'store:version',
            # 'features': 'store:features',
        }

    def get_type(key, value):
        if key in byte_fields:
            return ChannelType.LONG
        elif key in object_fields:
            return ChannelType.CHAR
        else:
            return fields[key]

    flat_schema = {
        k: (flat_names[k], get_type(k, v)) for k, v in fields.items()
    }
    return schema, flat_schema, byte_fields, object_fields

class CAGraph:
    schema, flat_schema, byte_fields, object_fields = _generate_schema_caproto()

class CAStore:
    schema, flat_schema, byte_fields, object_fields = _generate_schema_caproto(False)
