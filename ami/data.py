import sys
import abc
import zmq
import time
import dill
import typing
import inspect
import logging
import pickle
try:
    import h5py
except ImportError:
    h5py = None
try:
    import psana
except ImportError:
    psana = None
try:
    import pyarrow as pa
except ImportError:
    pa = None
import numpy as np
import amitypes as at
from enum import Enum
from dataclasses import dataclass, asdict, field


logger = logging.getLogger(__name__)


class MsgTypes(Enum):
    Transition = 0
    Heartbeat = 1
    Datagram = 2
    Graph = 3

    def _serialize(msgType):
        return {'type': msgType.value}

    def _deserialize(data):
        return MsgTypes(data['type'])


class Transitions(Enum):
    Allocate = 0
    Configure = 1
    Unconfigure = 2
    Enable = 3
    Disable = 4

    def _serialize(transitionType):
        return {'type': transitionType.value}

    def _deserialize(data):
        return Transitions(data['type'])


@dataclass
class Transition:
    ttype: Transitions
    payload: dict

    def _serialize(self):
        return asdict(self)

    @classmethod
    def _deserialize(cls, data):
        return cls(**data)


@dataclass
class Datagram:
    name: str
    dtype: type
    data: dict = field(default_factory=dict)

    def _serialize(self):
        return self.__dict__

    @classmethod
    def _deserialize(cls, data):
        return cls(**data)


@dataclass
class Message:
    """
    Message container

    Args:
        mtype (MsgTypes): Message type

        identity (int): Message id number

        payload (dict): Message payload
    """
    mtype: MsgTypes
    identity: int
    payload: dict
    timestamp: int = 0

    def _serialize(self):
        return asdict(self)

    def _deserialize(data):
        if data['mtype'] == MsgTypes.Transition:
            data['payload'] = Transition(**data['payload'])
        return Message(**data)


@dataclass
class CollectorMessage(Message):
    """
    Collector message

    Args:
        heartbeat (int): heartbeat

        name (str): name

        version (int): version
    """
    heartbeat: int = 0
    name: str = ""
    version: int = 0

    def _serialize(self):
        return self.__dict__

    @classmethod
    def _deserialize(cls, data):
        return cls(**data)


def build_serialization_context():
    def register(ctx, cls):
        ctx.register_type(cls, cls.__name__,
                          custom_serializer=cls._serialize,
                          custom_deserializer=cls._deserialize)

    context = pa.SerializationContext()
    for cls in [MsgTypes, Transitions, Message, CollectorMessage, Transition, Datagram]:
        register(context, cls)
    for cls in at.PyArrowTypes:
        register(context, cls)

    return context


class ModuleSerializer:

    def __init__(self, module):
        self.module = module

    def __call__(self, msg):
        return [self.module.dumps(msg)]


class ModuleDeserializer:

    def __init__(self, module):
        self.module = module

    def __call__(self, data):
        msg = [self.module.loads(d) for d in data]
        if len(msg) == 0:
            return None
        elif len(msg) == 1:
            return msg[0]
        else:
            return msg


class ArrowSerializer:

    def __init__(self):
        self.context = build_serialization_context()

    def __call__(self, msg):
        serialized_msg = []
        ser = pa.serialize(msg, context=self.context)
        comp = ser.to_components()
        metadata = {k: comp[k] for k in ['num_tensors', 'num_ndarrays', 'num_buffers', 'num_sparse_tensors']}
        serialized_msg.append(pickle.dumps(metadata))
        views = list(map(memoryview, comp['data']))
        serialized_msg.extend(views)
        return serialized_msg


class ArrowDeserializer:

    def __init__(self):
        self.context = build_serialization_context()

    def __call__(self, data):
        components = pickle.loads(data[0])
        data = list(map(pa.py_buffer, data[1:]))
        components['data'] = data
        return pa.deserialize_components(components, context=self.context)


SerializationProtocols = {
    'pickle': (ModuleSerializer, ModuleDeserializer, {'module': pickle}),
    'dill': (ModuleSerializer, ModuleDeserializer, {'module': dill}),
    'arrow': (ArrowSerializer, ArrowDeserializer, {}),
    None:
        (ArrowSerializer, ArrowDeserializer, {})
        if pa is not None else
        (ModuleSerializer, ModuleDeserializer, {'module': dill}),
}


def Serializer(protocol=None):
    if protocol in SerializationProtocols:
        cls, _, kwargs = SerializationProtocols[protocol]
        return cls(**kwargs)
    else:
        raise NotImplementedError("%s protocol is not avaliable!" % protocol)


def Deserializer(protocol=None):
    if protocol in SerializationProtocols:
        _, cls, kwargs = SerializationProtocols[protocol]
        return cls(**kwargs)
    else:
        raise NotImplementedError("%s protocol is not avaliable!" % protocol)


class TimestampConverter:
    def __init__(self, shift=32, heartbeat=1000):
        self.shift = shift
        self.mask = (1 << self.shift) - 1
        self.heartbeat = heartbeat

    def decode(self, raw_ts, as_float=False):
        sec = (raw_ts >> self.shift) & self.mask
        nsec = raw_ts & self.mask
        if as_float:
            return sec + nsec * 1.e-9
        else:
            return sec, nsec

    def encode(self, sec, nsec):
        return ((sec & self.mask) << self.shift) | (nsec & self.mask)

    def __call__(self, raw_ts):
        timestamp = self.decode(raw_ts, as_float=True)
        return timestamp, int(timestamp * self.heartbeat)


class Source(abc.ABC):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        """
        Args:
            idnum (int): Id number

            num_workers (int): Number of workers

            src_cfg (dict): Source configuration loaded from JSON file
        """

        self.idnum = idnum
        self.num_workers = num_workers
        self.heartbeat_period = heartbeat_period
        self.heartbeat = None
        self.old_heartbeat = None
        self.special_names = {}
        self.requested_names = set()
        self.requested_data = set()
        self.requested_special = {}
        self.config = src_cfg
        self.flags = flags or {}
        self.source = at.DataSource(self.config)
        self._base_types = {
            'timestamp': int,
            'heartbeat': int,
            'source': type(self.source),
        }
        self._base_names = set(self._base_types)
        self._flag_types = {
            'interval': float,
            'init_time': float,
            'bound': int,
            'repeat': lambda s: s.lower() == 'true',
            'counting': lambda s: s.lower() == 'true',
            'files': lambda f: f.split(','),
        }
        # Apply flags to the config dictionary
        for flag, value in self.flags.items():
            # if there is type info for a flag cast before adding it
            if flag in self._flag_types:
                self.config[flag] = self._flag_types[flag](value)
            else:
                self.config[flag] = value

    @property
    def interval(self):
        """
        Getter for the interval value set in the source configuration. This is
        used as interval to wait (in seconds) before fetching the next event.

        Returns:
            The interval value set in the source configuration.
        """
        return self.config.get('interval', 0)

    @property
    def init_time(self):
        """
        Getter for the init_time value set in the source configuration. This is
        used as to tell the source how long to wait (in seconds) before sending
        event data after coming online.

        Returns:
            The init_time value set in the source configuration.
        """
        return self.config.get('init_time', 0)

    def reset_heartbeat(self):
        """
        Resets the heartbeat to its initial state.
        """
        self.heartbeat = None
        self.old_heartbeat = None

    def check_heartbeat_boundary(self, timestamp):
        """
        Checks if the timestamp given has crossed into another heartbeat
        period than the current one.

        Args:
            timestamp (int): The timestamp to use for the check

        Returns:
            If a heartbeat boundary has been crossed a value of `True` is
            returned.
        """
        if self.heartbeat is None:
            self.heartbeat = (timestamp // self.heartbeat_period)
            return False
        elif (timestamp // self.heartbeat_period) > (self.heartbeat):
            self.old_heartbeat = self.heartbeat
            self.heartbeat = (timestamp // self.heartbeat_period)
            return True
        else:
            return False

    @classmethod
    def find_source(cls, name):
        """
        Finds the a subclass of `Source` matching the passed name. The matching
        is either exact or it takes a lower case version of the prefix.

        As an example 'psana' or 'PsanaSource' will map to `PsanaSource`.

        Args:
            name (str): The name of the subclass to search for

        Returns:
            The matching subclass of `Source` if found otherwise None
        """
        cls_list = inspect.getmembers(sys.modules[__name__],
                                      lambda x:
                                      inspect.isclass(x) and not inspect.isabstract(x) and issubclass(x, cls))
        for clsname, clsobj in cls_list:
            if (clsname == name) or (clsname == name.capitalize() + 'Source'):
                return clsobj

    @abc.abstractmethod
    def _names(self):
        """
        An abstract method that subclasses of `Source` need to implement.

        It should return a list of names of all data currently available from
        the source.

        Returns:
            A list of names of all the currently available data from the
            source.
        """
        pass

    @property
    def names(self):
        """
        Getter for the list of names of all data currently available from the
        source.

        Returns:
            A list of names of all the currently available data from the
            source.
        """
        subclass_names = self._names()
        subclass_names.update(self._base_types)
        return subclass_names

    @abc.abstractmethod
    def _types(self):
        """
        An abstract method that subclasses of `Source` need to implement.

        It should return a dictionary of all data currently available from the
        source where the key is the name of the data source and the value is
        the type of the source.

        Returns:
            A dictionary with the types of all the currently available data
            from the source.
        """
        pass

    @property
    def types(self):
        """
        Getter for the dictionary of all data currently available from the
        source where the key is the name of the data source and the value is
        the type of the source.

        Returns:
            A dictionary with the types of all the currently available data
            from the source.
        """
        subclass_types = self._types()
        subclass_types.update(self._base_types)
        return subclass_types

    def configure(self):
        """
        Constructs a properly formatted configure message

        Returns:
            An object of type `Message` which includes a dict of
            names:types of the currently available detectors/data.
        """
        self.reset_heartbeat()
        self.request(self.requested_names)
        flatten_types = {name: at.dumps(dtype) for name, dtype in self.types.items()}
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.Configure, flatten_types))

    def unconfigure(self):
        """
        Constructs a properly formatted unconfigure message

        Returns:
            An object of type `Message` which includes an empty dict.
        """
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.Unconfigure, {}))

    def heartbeat_msg(self):
        """
        Constructs a properly formatted heartbeat message

        Returns:
            An object of type `Message` which includes a the most recently
            completed heartbeat.
        """
        return Message(MsgTypes.Heartbeat, self.idnum, self.old_heartbeat)

    def event(self, timestamp, data):
        """
        Constructs a properly formatted event message

        Args:
            timestamp (int): timestamp of the event

            data (dict): the data of the event

        Returns:
            An object of type `Message` which includes the data for the event.
        """
        base = [('timestamp', timestamp), ('heartbeat', self.heartbeat), ('source', self.source)]
        data.update({k: v for k, v in base if k in self.requested_names})
        msg = Message(mtype=MsgTypes.Datagram, identity=self.idnum, payload=data, timestamp=timestamp)
        yield msg

    def request(self, names):
        """
        Request that the source includes the specified data from its list of
        available data when it emits event messages.

        Args:
            names (list): names of the data being requested
        """
        self.requested_names = set(names)
        self.requested_data = set()
        self.requested_special = {}
        for name in self.requested_names:
            if name in self.special_names:
                sub_name, info = self.special_names[name]
                if sub_name not in self.requested_special:
                    self.requested_special[sub_name] = {}
                self.requested_special[sub_name][name] = info
            elif name not in self._base_names:
                if name in self.names:
                    self.requested_data.add(name)
                else:
                    logger.debug("DataSrc: requested source \'%s\' is not available", name)

    @abc.abstractmethod
    def events(self):
        """
        Generator which yields `Message` containing dictionary of data as payload.
        """
        pass


class HierarchicalDataSource(Source):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self._counter = None
        self.loop_count = 0
        self.delimiter = ":"
        self.data_types = {}
        self.special_types = {}
        self.grouped_types = {}

    def _names(self):
        return set(self.data_types)

    def _types(self):
        return self.data_types

    @abc.abstractmethod
    def _runs(self):
        pass

    @abc.abstractmethod
    def _events(self, run):
        pass

    @abc.abstractmethod
    def _update(self, run):
        pass

    @abc.abstractmethod
    def _process(self, run):
        pass

    @abc.abstractmethod
    def _timestamp(self, evt):
        pass

    def timestamp(self, evt):
        counter = self.counter
        timestamp, heartbeat = self._timestamp(evt)
        if timestamp is None:
            # If the source does not provide timestamps use the counter
            return counter, counter
        elif self.counting_mode:
            # If in counting mode then force use the counter for heartbeats
            return timestamp, counter
        elif heartbeat is None:
            # If no heartbeat adjusted timestamp is provided just use the raw timestamp
            return timestamp, timestamp
        else:
            return timestamp, heartbeat

    @property
    def repeat_mode(self):
        return self.config.get('repeat', False)

    @property
    def counting_mode(self):
        return self.config.get('counting', True)

    @property
    def repeat(self):
        if self.loop_count and not self.repeat_mode:
            return False
        else:
            self.loop_count += 1
            return True

    @property
    def counter(self):
        if self._counter is None:
            self._counter = self.idnum
        else:
            self._counter += self.num_workers

        return self._counter

    def events(self):
        self._counter = None
        time.sleep(self.init_time)

        while self.repeat:
            for run in self._runs():
                self.source.run = run
                self.source.key += 1
                # clear type info from previous runs
                self.data_types = {}
                self.special_types = {}
                self.grouped_types = {}
                # call the subclasses update function then emit the configure message
                self._update(run)
                yield self.configure()

                for evt in self._events(run):
                    self.source.evt = evt
                    # get the subclasses timestamp implementation
                    timestamp, heartbeat = self.timestamp(evt)
                    # check the heartbeat
                    if self.check_heartbeat_boundary(heartbeat):
                        yield self.heartbeat_msg()

                    # emit the processed event data
                    yield from self.event(timestamp, self._process(evt))
                    time.sleep(self.interval)
                    # remove reference to evt object
                    self.source.evt = None

                # signal that the run has ended
                yield self.unconfigure()
                # remove reference to run object
                self.source.run = None


class PsanaSource(HierarchicalDataSource):

    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.ts_converter = TimestampConverter()
        self.ds_keys = {
            'exp', 'dir', 'files', 'shmem', 'filter', 'batch_size', 'max_events', 'sel_det_ids', 'det_name', 'run'
        }
        # special attributes that are per run instead of per event from a detectors interface, e.g. calib constants
        self.special_attrs = {
            'calibconst': typing.Dict,
        }
        if psana is None:
            raise NotImplementedError("psana is not available!")

    def _timestamp(self, evt):
        return self.ts_converter(evt.timestamp)

    @property
    def ds(self):
        ps_kwargs = {k: self.config[k] for k in self.ds_keys if k in self.config}
        return psana.DataSource(**ps_kwargs)

    @property
    def repeat_mode(self):
        return self.config.get('repeat', self.config.get('shmem', False))

    @property
    def counting_mode(self):
        return self.config.get('counting', not self.config.get('shmem', False))

    def _runs(self):
        yield from self.ds.runs()

    def _events(self, run):
        yield from run.events()

    def _get_attr_name(self, detname, det_xface_name, attr, is_env_det):
        if is_env_det:
            return detname
        else:
            return self.delimiter.join((detname, det_xface_name, attr))

    def _detinfo(self, run):
        for (detname, det_xface_name), det_attr_list in run.detinfo.items():
            yield detname, det_xface_name, det_attr_list, False
        for (detname, det_xface_name), det_attr in run.epicsinfo.items():
            yield detname, det_xface_name, [det_attr], True

    def _update_special_attrs(self, detname, det_interface):
        for attr, attr_type in self.special_attrs.items():
            if hasattr(det_interface, attr):
                attr_name = self.delimiter.join((detname, attr))
                self.data_types[attr_name] = attr_type
                self.special_types[attr_name] = getattr(det_interface, attr)

    def _update_dets(self, run, detname, is_env_det):
        if detname not in self.detectors:
            self.detectors[detname] = run.Detector(detname)

        det_xface = self.detectors[detname]

        if not is_env_det:
            self.data_types[detname] = at.Detector
            self.grouped_types[detname] = at.Detector(detname, 'psana', det_xface._dettype, det_xface)

        return det_xface

    def _update_hsd_segment(self, seg_name, seg_type, seg_chans):
        for seg_key, chanlist in seg_chans.items():
            seg_key_name = str(seg_key)
            seg_key_type, seg_value_type = seg_type.__args__
            for chan_key_name, chan_type in typing.get_type_hints(seg_value_type).items():
                chan_name = self.delimiter.join((seg_name, seg_key_name, chan_key_name))
                # for the HSD cast the channel ids to expected type
                try:
                    chan_key = seg_key_type(chan_key_name)
                except ValueError:
                    chan_key = chan_key_name
                if not isinstance(chan_key, seg_key_type) or chan_key in chanlist:
                    accessor = (lambda o, s, c: o.get(s, {}).get(c), (seg_key, chan_key), {})
                    self.data_types[chan_name] = chan_type
                    self.special_names[chan_name] = (seg_name, accessor)

    def _update(self, run):
        self.detectors = {}
        self.env_detectors = set()
        self.special_names = {}
        for detname, det_xface_name, det_attr_list, is_env_det in self._detinfo(run):
            # make & cache the psana Detector object
            det_interface = self._update_dets(run, detname, is_env_det)

            # check if the detector has calibconstants
            self._update_special_attrs(detname, det_interface)

            for attr in det_attr_list:
                attr_name = self._get_attr_name(detname, det_xface_name, attr, is_env_det)
                if is_env_det:
                    self.env_detectors.add(attr_name)
                try:
                    if is_env_det:
                        attr_type = det_interface.dtype
                    else:
                        attr_sig = inspect.signature(getattr(getattr(det_interface, det_xface_name), attr))
                        if attr_sig.return_annotation is attr_sig.empty:
                            attr_type = typing.Any
                        else:
                            attr_type = attr_sig.return_annotation
                except ValueError:
                    attr_type = typing.Any
                if attr_type in at.HSDTypes:
                    # ignore things which are not derived from typing.Dict
                    if str(attr_type).startswith('typing.Dict'):
                        seg_chans = getattr(det_interface, det_xface_name)._seg_chans()
                        self._update_hsd_segment(attr_name, attr_type, seg_chans)
                    else:
                        logger.debug("DataSrc: unsupported HSDType: %s", attr_type)
                else:
                    self.data_types[attr_name] = attr_type

    def _process(self, evt):
        event = {}

        for name in self.requested_data:
            # check if it is a special type like calibconst
            if name in self.special_types:
                event[name] = self.special_types[name]
            else:
                if name in self.env_detectors:
                    namesplit = []
                    detname = name
                else:
                    # each name is like "detname:drp_class_name:attrN"
                    namesplit = name.split(':')
                    detname = namesplit[0]

                if name in self.grouped_types:
                    event[name] = self.grouped_types[name]
                else:
                    # loop to the bottom level of the Det obj and get data
                    obj = self.detectors[detname]
                    for token in namesplit[1:]:
                        obj = getattr(obj, token)
                    event[name] = obj(evt)

        for name, sub_names in self.requested_special.items():
            namesplit = name.split(':')
            detname = namesplit[0]

            # loop to the bottom level of the Det obj and get data
            obj = self.detectors[detname]
            for token in namesplit[1:]:
                obj = getattr(obj, token)
            data = obj(evt)
            # access the requested methods of the object returned by the det interface
            for sub_name, (meth, args, kwargs) in sub_names.items():
                if data is None:
                    event[sub_name] = None
                else:
                    event[sub_name] = meth(data, *args, **kwargs)

        return event


class Hdf5Source(HierarchicalDataSource):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.hdf5_delim = "/"
        self.files = self.config.get('files', [])
        self.hdf5_ts = self.config.get('timestamp')
        self.hdf5_idx = None
        self.hdf5_max_idx = self.hdf5_idx
        self.ts_converter = TimestampConverter()
        if h5py is None:
            raise NotImplementedError("h5py is not available!")

    @property
    def index(self):
        if self.hdf5_idx is None:
            self.hdf5_idx = self.idnum
        else:
            self.hdf5_idx += self.num_workers

        if self.hdf5_max_idx is not None and self.hdf5_idx < self.hdf5_max_idx:
            return self.hdf5_idx
        else:
            raise IndexError("index outside hdf5 dataset range")

    def check_max_index(self, idx):
        if self.hdf5_max_idx is None:
            self.hdf5_max_idx = idx
        else:
            self.hdf5_max_idx = min(self.hdf5_max_idx, idx)

    def encode(self, name):
        return name.replace(self.hdf5_delim, self.delimiter)

    def decode(self, name):
        return name.replace(self.delimiter, self.hdf5_delim)

    @property
    def repeat_mode(self):
        return self.config.get('repeat', False)

    def _timestamp(self, evt):
        if self.hdf5_ts is None:
            return None, None
        else:
            index, run = evt
            return self.ts_converter(run[self.hdf5_ts][index])

    def _runs(self):
        for filename in self.files:
            with h5py.File(filename, 'r') as hdf5_file:
                yield hdf5_file

    def _events(self, run):
        while True:
            try:
                yield (self.index, run)
            except IndexError:
                self.hdf5_idx = None
                self.hdf5_max_idx = self.hdf5_idx
                break

    def _update_data_names(self, name, obj):
        if isinstance(obj, h5py.Dataset):
            ndims = len(obj.shape) - 1
            if ndims < 0:
                logger.debug("DataSrc: ignoring empty dataset %s", name)
            else:
                self.check_max_index(obj.shape[0])
                # pytables bool needs special handling when using h5py
                h5_native_type = obj.id.get_type()
                if isinstance(h5_native_type, h5py.h5t.TypeBitfieldID):
                    self.special_types[self.encode(name)] = np.bool
                # assign type based on the dimensions of the dataset
                if ndims == 2:
                    self.data_types[self.encode(name)] = at.Array2d
                elif ndims == 1:
                    self.data_types[self.encode(name)] = at.Array1d
                elif ndims == 0:
                    if isinstance(h5_native_type, h5py.h5t.TypeBitfieldID):
                        self.data_types[self.encode(name)] = bool
                    else:
                        self.data_types[self.encode(name)] = at.NumPyTypeDict.get(obj.dtype.type, typing.Any)
                else:
                    self.data_types[self.encode(name)] = typing.Any

    def _update(self, run):
        groups = [run]
        while groups:
            grp = groups.pop()
            for obj in grp.values():
                if isinstance(obj, h5py.Group):
                    groups.append(obj)
                elif isinstance(obj, h5py.Dataset):
                    self._update_data_names(obj.name.strip('/'), obj)
                else:
                    logger.warn("DataSrc: hdf5 node %s has unsupported type: %s", obj.name, type(obj))

    def _process(self, evt):
        index, run = evt

        event = {}

        for name in self.requested_data:
            if name in self.special_types:
                dset = run[self.decode(name)]
                with dset.astype(self.special_types[name]):
                    event[name] = dset[index]
            else:
                event[name] = run[self.decode(name)][index]

        return event


class SimSource(Source):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.count = 0
        self.synced = False
        if 'sync' in self.config:
            self.ctx = zmq.Context()
            self.ts_src = self.ctx.socket(zmq.REQ)
            self.ts_src.connect(self.config['sync'])
            self.synced = True

    def _map_dtype(self, config):
        if config['dtype'] == 'Scalar':
            if config.get('integer', False):
                return int
            else:
                return float
        elif config['dtype'] == 'Waveform':
            return at.Array1d
        elif config['dtype'] == 'Image':
            return at.Array2d
        else:
            return None

    def _names(self):
        return set(self.simulated.keys())

    def _types(self):
        return {name: self._map_dtype(config) for name, config in self.simulated.items()}

    @property
    def simulated(self):
        return self.config.get('config', {})

    @property
    def timestamp(self):
        if self.synced:
            self.ts_src.send_string("ts")
            return self.ts_src.recv_pyobj()
        else:
            self.count += 1
            return self.num_workers * self.count + self.idnum


class RandomSource(SimSource):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        np.random.seed([idnum])

    def events(self):
        time.sleep(self.init_time)
        yield self.configure()
        while True:
            event = {}
            # get the timestamp and check heartbeat
            timestamp = self.timestamp
            if self.check_heartbeat_boundary(timestamp):
                yield self.heartbeat_msg()
            for name, config in self.simulated.items():
                if name in self.requested_data:
                    if config['dtype'] == 'Scalar':
                        value = config['range'][0] + (config['range'][1] - config['range'][0]) * np.random.rand(1)[0]
                        if config.get('integer', False):
                            event[name] = int(value)
                        else:
                            event[name] = value
                    elif config['dtype'] == 'Waveform' or config['dtype'] == 'Image':
                        event[name] = np.random.normal(config['pedestal'], config['width'], config['shape'])
                    else:
                        logger.warn("DataSrc: %s has unknown type %s", name, config['dtype'])
            yield from self.event(timestamp, event)
            time.sleep(self.interval)
        # signal source has finished
        yield self.unconfigure()


class StaticSource(SimSource):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.bound = self.config.get('bound', np.inf)

    def events(self):
        count = 0
        time.sleep(self.init_time)
        yield self.configure()
        while True:
            event = {}
            # get the timestamp and check heartbeat
            timestamp = self.timestamp
            if self.check_heartbeat_boundary(timestamp):
                yield self.heartbeat_msg()
            for name, config in self.simulated.items():
                if name in self.requested_data:
                    if config['dtype'] == 'Scalar':
                        event[name] = 1
                    elif config['dtype'] == 'Waveform' or config['dtype'] == 'Image':
                        event[name] = np.ones(config['shape'])
                    else:
                        logger.warn("DataSrc: %s has unknown type %s", name, config['dtype'])
            count += 1
            yield from self.event(timestamp, event)
            if count >= self.bound:
                break
            time.sleep(self.interval)
        # signal source has finished
        yield self.unconfigure()
