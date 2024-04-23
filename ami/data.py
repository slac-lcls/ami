import os
import sys
import abc
import zmq
import time
import dill
import json
import typing
import inspect
import logging
import datetime
import pickle
try:
    import h5py
except ImportError:
    h5py = None
try:
    import warnings
    warnings.simplefilter(action='ignore', category=FutureWarning)
    import pyarrow as pa
except ImportError:
    pa = None
import numpy as np
import amitypes as at
from enum import Enum
from dataclasses import dataclass, asdict, field
from ami import psana, psana_uses_epics_epoch


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
    BeginStep = 3
    EndStep = 4
    Enable = 5
    Disable = 6

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


@dataclass(frozen=True)
class Heartbeat:
    """
    Heartbeat contatiner.

    Comparison/equality operators are implemented so that it can be
    compared to integers.

    Args:
        identity (int): Heartbeat integer id number
        timestamp (float): Unix timestamp associated with heartbeat
        prompt (bool): Flag to indicate the heartbeat prompt (not to be built)
    """
    identity: int = 0
    timestamp: float = 0.0
    prompt: bool = False

    def __hash__(self):
        return hash(self.identity)

    def __eq__(self, other):
        return self.identity == other

    def __lt__(self, other):
        return self.identity < other

    def __le__(self, other):
        return self.identity <= other

    def __gt__(self, other):
        return self.identity > other

    def __ge__(self, other):
        return self.identity >= other

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
    heartbeat: Heartbeat = Heartbeat()
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
    for cls in [MsgTypes, Transitions, Heartbeat, Message,
                CollectorMessage, Transition, Datagram]:
        register(context, cls)
    for cls in at.PyArrowTypes:
        register(context, cls)

    return context


class ModuleSerializer:

    def __init__(self, module):
        self.module = module

        if module == pickle and pickle.HIGHEST_PROTOCOL >= 5:
            def dumps(msg):
                buffers = []
                m = pickle.dumps(msg, protocol=5, buffer_callback=buffers.append)
                buffers.append(m)
                return buffers
        else:
            def dumps(msg):
                return [self.module.dumps(msg)]

        self.dumps = dumps

    def __call__(self, msg):
        return self.dumps(msg)

    def sizeof(self, msg):
        assert type(msg) is list, "Excepts serialized message!"
        size = sys.getsizeof(msg[-1])
        for c in msg[:-1]:
            if hasattr(pickle, 'PickleBuffer') and type(c) is pickle.PickleBuffer:
                size += c.raw().nbytes
            elif type(c) is bytes:
                size += sys.getsizeof(c)
        return size


class ModuleDeserializer:

    def __init__(self, module):
        self.module = module

        if module == pickle and pickle.HIGHEST_PROTOCOL >= 5:
            def loads(data):
                return pickle.loads(data[-1], buffers=data[:-1])
        else:
            def loads(data):
                msg = [self.module.loads(d) for d in data]
                if len(msg) == 0:
                    return None
                elif len(msg) == 1:
                    return msg[0]
                else:
                    return msg

        self.loads = loads

    def __call__(self, data):
        return self.loads(data)


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

    def sizeof(self, msg):
        assert type(msg) is list and type(msg[0]) is bytes, "Excepts serialized message!"
        size = sys.getsizeof(msg[0])
        for c in msg[1:]:
            size += c.nbytes
        return size


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
        if pa is not None and pickle.HIGHEST_PROTOCOL < 5 else
        (ModuleSerializer, ModuleDeserializer, {'module': pickle}),
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
        self.epics_epoch_dt = datetime.datetime(1990, 1, 1, tzinfo=datetime.timezone.utc)

    def decode(self, raw_ts, as_float=False):
        sec = (raw_ts >> self.shift) & self.mask
        nsec = raw_ts & self.mask
        if as_float:
            return sec + nsec * 1.e-9
        else:
            return sec, nsec

    def encode(self, sec, nsec):
        return ((sec & self.mask) << self.shift) | (nsec & self.mask)

    def unix_timestamp(self, epics_timestamp):
        unix_epoch_dt = self.epics_epoch_dt + datetime.timedelta(seconds=epics_timestamp)
        return unix_epoch_dt.timestamp()

    def __call__(self, raw_ts, epics_epoch=True):
        timestamp = self.decode(raw_ts, as_float=True)
        unix_ts = self.unix_timestamp(timestamp) if epics_epoch else timestamp
        return raw_ts, int(timestamp * self.heartbeat), unix_ts


@dataclass
class RequestedData:
    def __init__(self, name=None, kws=None):
        """ 
        Container for the detectors names and their kwargs.
        Any addition / modification of the data sources should be done using this class, as this 
        allow for easy update from one instance to another.
        """
        self.names = set()
        if name:
            self.names.add(name)
        self.kwargs = dict()
        if kws and name:
            self.kwargs = self.kwargs[name] = kws

    def __repr__(self):
        s = str(f"{self.__class__}: ")
        s = ', '.join(self.names)
        if self.kwargs:
            s += '\n'
            s += str(self.kwargs)
        return s

    def add(self, name, kwargs=None):
        self.names.add(name)
        if kwargs:
            self.kwargs[name] = kwargs

    def update(self, requested_data_update):
        self.names.update(requested_data_update.names)
        self.kwargs.update(requested_data_update.kwargs)

    def __iter__(self):
        for name in self.names:
            yield self.__next__(name)
        return

    def __next__(self, name):
        """
        Is that not too weird?
        Iterating over this class return an instance of this class, with
        a single name and its potential kwargs.
        """
        kws = self.kwargs.get(name, None)
        req = RequestedData()
        req.add(name, kwargs=kws)
        return req


class Source(abc.ABC):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None, evtid_type=None):
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
        self.requested_names = RequestedData()
        self.requested_data = RequestedData()
        self.requested_special = {}
        self.config = src_cfg
        self.flags = flags or {}
        self.source = at.DataSource(self.config)
        self._base_types = {
            'eventid': int if evtid_type is None else evtid_type,
            'timestamp': float,
            'heartbeat': int,
            'source': type(self.source),
        }
        self._base_names = set(self._base_types)
        self._cfgkey_types = {
            'interval': float,
            'init_time': float,
            'bound': int,
            'repeat': lambda s: s if isinstance(s, bool) else s.lower() == 'true',
            'counting': lambda s: s if isinstance(s, bool) else s.lower() == 'true',
            'files': lambda n: n if isinstance(n, list) else [os.path.expanduser(f) for f in n.split(',')],
            'config': lambda c: c if isinstance(c, dict) else os.path.expanduser(c),
        }
        # Correct the types of special keys in the dictionary that might have
        # been passed as strings (can happen when specifying config on the
        # command line.
        for key, value in self.config.items():
            if key in self._cfgkey_types:
                self.config[key] = self._cfgkey_types[key](value)
        # Apply flags to the config dictionary
        for flag, value in self.flags.items():
            # if there is type info for a flag cast before adding it
            if flag in self._cfgkey_types:
                self.config[flag] = self._cfgkey_types[flag](value)
            else:
                self.config[flag] = value
        # If 'type' has not been passed in the config dictionary then set it
        if 'type' not in self.config:
            base_name = __class__.__name__
            type_name = type(self).__name__
            if type_name.endswith(base_name):
                type_name = type_name[:-len(base_name)]
            self.config['type'] = type_name.lower()

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

    @property
    def src_type(self):

        """
        Getter for the type value set in the source configuration. This tells
        which type of source it is. e.g. sim, psana, hdf5.

        Returns:
            The type value set in the source configuration.
        """
        return self.config.get('type', 'generic')

    @property
    def prompt_mode(self):
        """
        Getter for the prompt mode state. This is based on the heartbeat period.
        A heartbeat period of 0 will yield True otherwise False.

        Returns:
            Boolean value of whether prompt mode is active
        """
        return self.heartbeat_period == 0

    def reset_heartbeat(self):
        """
        Resets the heartbeat to its initial state.
        """
        self.heartbeat = None
        self.old_heartbeat = None

    def check_heartbeat_boundary(self, value, timestamp=None):
        """
        Checks if the value given has crossed into another heartbeat
        period than the current one.

        Args:
            value (int): The value to use for the check
            timestamp (float): optional timestamp to associate with
                heartbeat. Defaults to the current time if not specified

        Returns:
            If a heartbeat boundary has been crossed a value of `True` is
            returned.
        """
        if timestamp is None:
            timestamp = time.time()
        if self.prompt_mode:
            self.old_heartbeat = Heartbeat(value, timestamp, True)
            return True
        elif self.heartbeat is None:
            self.heartbeat = Heartbeat(value // self.heartbeat_period, timestamp)
            return False
        elif (value // self.heartbeat_period) > self.heartbeat:
            self.old_heartbeat = self.heartbeat
            self.heartbeat = Heartbeat(value // self.heartbeat_period, timestamp)
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
            if (clsname == name) or (clsname == name.capitalize() + cls.__name__):
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

    def begin_step(self):
        """
        Constructs a properly formatted beginstep message

        Returns:
            An object of type `Message` which includes info on the step.
        """
        if self.stepid is None:
            self.stepid = 0
        else:
            self.stepid += 1
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.BeginStep, self.stepid))

    def end_step(self):
        """
        Constructs a properly formatted endstep message

        Returns:
            An object of type `Message` which includes info on the step.
        """
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.EndStep, self.stepid))

    def heartbeat_msg(self):
        """
        Constructs a properly formatted heartbeat message

        Returns:
            An object of type `Message` which includes a the most recently
            completed heartbeat.
        """
        return Message(MsgTypes.Heartbeat, self.idnum, self.old_heartbeat)

    def event(self, eventid, timestamp, data):
        """
        Constructs a properly formatted event message

        Args:
            eventid: the unique id of the event

            timestamp (float): timestamp of the event

            data (dict): the data of the event

        Returns:
            An object of type `Message` which includes the data for the event.
        """
        base = [
            ('eventid', eventid),
            ('timestamp', timestamp),
            ('heartbeat', self.heartbeat.identity if self.heartbeat is not None else None),
            ('source', self.source)
        ]
        data.update({k: v for k, v in base if k in self.requested_names})
        msg = Message(mtype=MsgTypes.Datagram, identity=self.idnum, payload=data, timestamp=eventid)
        yield msg

    def request(self, requested_data, is_kws_update=False):
        """
        Request that the source includes the specified data from its list of
        available data when it emits event messages.

        Args:
            requested_data (RequestedData): names of the data being requested
        """
        print(f"Data: requested_data before: {self.requested_data}")
        print(f"Data: requested_data: {requested_data}")
        if not is_kws_update:
            self.requested_data = RequestedData()
        self.requested_special = {}

        for name, req in zip(requested_data.names, requested_data):
            if name in self.special_names:
                sub_name, info = self.special_names[name]
                if sub_name not in self.requested_special:
                    self.requested_special[sub_name] = {}
                self.requested_special[sub_name][name] = info
            elif name not in self._base_names:
                if name in self.names:
                    self.requested_data.update(req)
                    # self.requested_data.add(name, kwargs=req.kwargs.get(name, None))
                    if is_kws_update: # super ugly way to clear kwargs...
                        if name not in requested_data.kwargs and name in self.requested_data.kwargs:
                            self.requested_data.kwargs.pop(name)
                else:
                    logger.debug("DataSrc: requested source \'%s\' is not available", name)
        print(f"Data: requested_data after: {self.requested_data}\n")

    @abc.abstractmethod
    def events(self):
        """
        Generator which yields `Message` containing dictionary of data as payload.
        """
        pass


class HierarchicalDataSource(Source):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None, evtid_type=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags, evtid_type)
        self._counter = None
        self.loop_count = 0
        self.step_count = 0
        self.delimiter = ":"
        self.data_types = {}
        self.special_types = {}
        self.grouped_types = {}

    def _names(self):
        return set(self.data_types)

    def _types(self):
        return self.data_types

    def _steps(self, run):
        yield run

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
    def _process(self, evt):
        pass

    @abc.abstractmethod
    def _cleanup(self):
        pass

    @abc.abstractmethod
    def _timestamp(self, evt):
        pass

    def timestamp(self, evt):
        """
        A function for the getting the timestamp information from an event
        object. There are three parts to the timestamp. A monotonic timestamp
        (if the event does not have one a counter is used here),
        the timestamp to use for heartbeat calculations (must be an integer),
        and the unix timestamp to associate with the event.

        Args:
            evt: a reference to the event object

        Returns:
            A tuple of three timestamp components
        """
        counter = self.counter
        timestamp, heartbeat, unix_timestamp = self._timestamp(evt)
        if unix_timestamp is None:
            unix_timestamp = time.time()
        if timestamp is None:
            # If the source does not provide timestamps use the counter
            return counter, counter, unix_timestamp
        elif self.counting_mode:
            # If in counting mode then force use the counter for heartbeats
            return timestamp, counter, unix_timestamp
        elif heartbeat is None:
            # If no heartbeat adjusted timestamp is provided just use the raw timestamp
            return timestamp, timestamp, unix_timestamp
        else:
            return timestamp, heartbeat, unix_timestamp

    def begin_step(self):
        """
        Constructs a properly formatted beginstep message

        Returns:
            An object of type `Message` which includes the step number.
        """
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.BeginStep, self.step_count))

    def end_step(self):
        """
        Constructs a properly formatted endstep message

        Returns:
            An object of type `Message` which includes the step number.
        """
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.EndStep, self.step_count))

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

        for run in self._runs():
            self.source.run = run
            self.source.key += 1
            # reset the step count to zero
            self.step_count = 0
            # clear type info from previous runs
            self.data_types = {}
            self.special_types = {}
            self.grouped_types = {}
            # call the subclasses update function then emit the configure message
            self._update(run)
            yield self.configure()

            # loop over the steps in the run (if any)
            for step in self._steps(run):
                # add the step to the source
                self.source.step = step
                # if the run has more than one step increase the source key
                if self.step_count > 0:
                    self.source.key += 1
                # emit the beginstep message
                yield self.begin_step()

                # loop over the events in the step
                for evt in self._events(step):
                    self.source.evt = evt
                    # get the subclasses timestamp implementation
                    eventid, heartbeat, unix_ts = self.timestamp(evt)
                    # check the heartbeat if not in prompt mode
                    if not self.prompt_mode and self.check_heartbeat_boundary(heartbeat, timestamp=unix_ts):
                        yield self.heartbeat_msg()
                    # emit the processed event data
                    yield from self.event(eventid, unix_ts, self._process(evt))
                    # check the heartbeat if in prompt mode
                    if self.prompt_mode and self.check_heartbeat_boundary(heartbeat, timestamp=unix_ts):
                        yield self.heartbeat_msg()
                    # sleep for the requested event interval
                    time.sleep(self.interval)
                    # remove reference to evt object
                    self.source.evt = None

                # emit the endstep message
                yield self.end_step()
                # remove reference to step object
                self.source.step = None
                # increase the step count
                self.step_count += 1

            # signal that the run has ended
            yield self.unconfigure()
            # remove reference to run object
            self.source.run = None
            # call the subclass cleanup method
            self._cleanup()


class PsanaSource(HierarchicalDataSource):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.ts_converter = TimestampConverter()
        self.epics_epoch = psana_uses_epics_epoch()
        self.ds_keys = {
            'exp',
            'dir',
            'files',
            'shmem',
            'filter',
            'batch_size',
            'max_events',
            'sel_det_ids',
            'det_name',
            'run',
            'live',
            'smd',
            'calibdir',
        }
        # special attributes that are per run instead of per event from a detectors interface, e.g. calib constants
        self.special_attrs = {
            'calibconst': dict,
        }
        self.evt_attrs = {
            'keepraw': int,
        }
        if psana is None:
            raise NotImplementedError("psana is not available!")

    def _timestamp(self, evt):
        return self.ts_converter(evt.timestamp, epics_epoch=self.epics_epoch)

    @property
    def ds(self):
        ps_kwargs = {k: self.config[k] for k in self.ds_keys if k in self.config}

        convert_kwargs = {
            'run': lambda s: s if isinstance(s, int) else int(s),
            'live': lambda s: s if isinstance(s, bool) else s.lower() == 'true',
            'smd': lambda s: s if isinstance(s, bool) else s.lower() == 'true',
        }
        for key, func in convert_kwargs.items():
            if key in ps_kwargs:
                ps_kwargs[key] = func(ps_kwargs[key])

        return psana.DataSource(**ps_kwargs)

    @property
    def repeat_mode(self):
        return self.config.get('repeat', self.config.get('shmem', False))

    @property
    def counting_mode(self):
        return self.config.get('counting', not self.config.get('shmem', False))

    def _runs(self):
        yield from self.ds.runs()

    def _steps(self, run):
        yield from run.steps()

    def _events(self, step):
        yield from step.events()

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
        for (detname, det_xface_name), det_attr in run.scaninfo.items():
            yield detname, det_xface_name, [det_attr], True

    def _update_evt_attrs(self):
        for attr_name, attr_type in self.evt_attrs.items():
            if hasattr(psana.event.Event, attr_name):
                self.data_types[attr_name] = attr_type
                self.special_types[attr_name] = getattr(psana.event.Event, attr_name)

    def _update_special_attrs(self, detname, det_interface):
        for attr, attr_type in self.special_attrs.items():
            if hasattr(det_interface, attr):
                attr_name = self.delimiter.join((detname, attr))
                self.data_types[attr_name] = attr_type
                self.special_types[attr_name] = getattr(det_interface, attr)

    def _update_dets(self, run, detname, is_env_det):
        if detname not in self.detectors:
            det_xface = run.Detector(detname)
            self.detectors[detname] = at.Detector(detname, self.src_type, det_xface._dettype, det_xface)
        else:
            det_xface = self.detectors[detname].det

        if not is_env_det:
            self.data_types[detname] = at.Detector

        return det_xface

    def _update_group(self, detname, det_xface_name, det_attr_list, is_env_det):
        # ignore env dets and when det_attr_list is empty
        if not is_env_det and det_attr_list:
            group_name = self.delimiter.join((detname, det_xface_name))
            self.data_types[group_name] = at.Group
            self.grouped_types[group_name] = det_attr_list

    def _update_scanvars(self, scan_name, var_type, var_names):
        def safe_access(o, c):
            for v in o:
                if v.name() == c:
                    if var_type == at.ScanMonitorType:
                        return v.loValue(), v.hiValue()
                    else:
                        return v.value()

        for var_key_name in var_names:
            var_name = self.delimiter.join((scan_name, var_key_name))
            self.data_types[var_name] = var_type
            accessor = (safe_access, (var_key_name,), {})
            self.special_names[var_name] = (scan_name, accessor)

    def _update_waveform(self, wf_name, chan_type, num_chans):
        def safe_access(o, c):
            try:
                return o[c]
            except IndexError:
                return None

        for chan_key in range(num_chans):
            chan_key_name = str(chan_key)
            chan_name = self.delimiter.join((wf_name, chan_key_name))
            self.data_types[chan_name] = chan_type
            accessor = (safe_access, (chan_key,), {})
            self.special_names[chan_name] = (wf_name, accessor)

    def _update_hsd_segment(self, hsd_name, hsd_type, seg_chans):
        for seg_key, chanlist in seg_chans.items():
            # add the segment itself
            seg_key_name = str(seg_key)
            seg_key_type, seg_type = hsd_type.__args__
            seg_name = self.delimiter.join((hsd_name, seg_key_name))
            self.data_types[seg_name] = seg_type
            seg_accessor = (lambda o, s: o.get(s, {}), (seg_key,), {})
            self.special_names[seg_name] = (hsd_name, seg_accessor)
            # add the channels of the segment
            for chan_key_name, chan_type in typing.get_type_hints(seg_type).items():
                chan_name = self.delimiter.join((hsd_name, seg_key_name, chan_key_name))
                # for the HSD cast the channel ids to expected type
                try:
                    chan_key = seg_key_type(chan_key_name)
                except ValueError:
                    chan_key = chan_key_name
                if not isinstance(chan_key, seg_key_type) or chan_key in chanlist:
                    accessor = (lambda o, s, c: o.get(s, {}).get(c), (seg_key, chan_key), {})
                    self.data_types[chan_name] = chan_type
                    self.special_names[chan_name] = (hsd_name, accessor)

    def _update(self, run):
        self.detectors = {}
        self.env_detectors = set()
        self.special_names = {}
        for detname, det_xface_name, det_attr_list, is_env_det in self._detinfo(run):
            # make & cache the psana Detector object
            det_interface = self._update_dets(run, detname, is_env_det)

            # check if the evt has metadata to expose - e.g. keepraw
            self._update_evt_attrs()

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
                    # ignore things which are not derived from dict
                    if str(attr_type).startswith('dict'):
                        seg_chans = getattr(det_interface, det_xface_name)._seg_chans()
                        self._update_hsd_segment(attr_name, attr_type, seg_chans)
                    else:
                        logger.debug("DataSrc: unsupported HSDType: %s", attr_type)
                    # add the overall hsdtype too
                    self.data_types[attr_name] = attr_type
                elif attr_type in at.MultiChannelScalarTypes:
                    if attr_type is at.MultiChannelInt:
                        chan_type = int
                    else:
                        chan_type = float
                    # update the individual channels
                    self._update_waveform(attr_name, chan_type, det_interface.nchannels)
                    # add the overall acqiris type too
                    self.data_types[attr_name] = attr_type
                elif attr_type in at.AcqirisTypes:
                    # update the individual channels
                    self._update_waveform(attr_name, at.AcqirisChannel, det_interface.nchannels)
                    # add the overall acqiris type too
                    self.data_types[attr_name] = attr_type
                elif attr_type in at.GenericWfTypes:
                    # update the individual channels
                    self._update_waveform(attr_name, at.GenericWfChannel, det_interface.nchannels)
                    # add the overall genericwf type too
                    self.data_types[attr_name] = attr_type
                elif attr_type in at.ScanTypes:
                    var_type = None
                    var_names = None
                    # set the var_type and var_names based on the type
                    if attr_type is at.ScanControls:
                        var_type = at.ScanControlType
                        var_names = getattr(det_interface, det_xface_name).control_names
                    elif attr_type is at.ScanMonitors:
                        var_type = at.ScanMonitorType
                        var_names = getattr(det_interface, det_xface_name).monitor_names
                    elif attr_type is at.ScanLabels:
                        var_type = at.ScanLabelType
                        var_names = getattr(det_interface, det_xface_name).label_names
                    else:
                        logger.debug("DataSrc: unsupported ScanType: %s", attr_type)
                    # if var_type is not None then update the scan vars
                    if var_type is not None:
                        # update the individual scan variables
                        self._update_scanvars(attr_name, var_type, var_names)
                        # add the overall scan variable type too
                        self.data_types[attr_name] = attr_type
                else:
                    self.data_types[attr_name] = attr_type

            # if the det interface has more than one attr make a grouped source
            self._update_group(detname, det_xface_name, det_attr_list, is_env_det)

    def _process(self, evt):
        event = {}

        for name in self.requested_data.names:
            # check if it is a special type like calibconst
            if name in self.special_types:
                if name in self.evt_attrs:
                    obj = self.special_types[name](evt)
                else:
                    obj = self.special_types[name]
                # check if the object is callable or not before adding to the event
                event[name] = obj() if callable(obj) else obj
            elif name in self.detectors and name not in self.env_detectors:
                event[name] = self.detectors[name]
            else:
                if name in self.env_detectors:
                    namesplit = []
                    detname = name
                else:
                    # each name is like "detname:drp_class_name:attrN"
                    namesplit = name.split(':')
                    detname = namesplit[0]

                if name in self.grouped_types:
                    obj = self.detectors[detname].det
                    for token in namesplit[1:]:
                        obj = getattr(obj, token)
                    grouped = {}
                    for attr in self.grouped_types[name]:
                        grouped[attr] = getattr(obj, attr)(evt)
                    event[name] = at.Group(name, self.src_type, type(obj).__name__, grouped)
                else: # 'normal' detectors
                    # loop to the bottom level of the Det obj and get data
                    obj = self.detectors[detname].det
                    for token in namesplit[1:]:
                        obj = getattr(obj, token)
                    if name in self.requested_data.kwargs:
                        print(f'Would use kwargs here: {self.requested_data.kwargs[name]}')
                        #event[name] = obj(evt, **self.requested_data.kwargs[name]) # to clean up once the client side is working
                        event[name] = obj(evt)
                    else:
                        event[name] = obj(evt)

        for name, sub_names in self.requested_special.items():
            namesplit = name.split(':')
            detname = namesplit[0]

            # loop to the bottom level of the Det obj and get data
            obj = self.detectors[detname].det
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

    def _cleanup(self):
        # clear the references to the detector interface
        self.detectors.clear()


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
            return None, None, None
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
        if isinstance(obj, h5py.Group):
            self.data_types[self.encode(name)] = at.Group
            self.grouped_types[self.encode(name)] = obj
        elif isinstance(obj, h5py.Dataset):
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
                if ndims == 3:
                    self.data_types[self.encode(name)] = at.Array3d
                elif ndims == 2:
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
                    self._update_data_names(obj.name.strip('/'), obj)
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
            elif name in self.grouped_types:
                grouped = {}
                groups = [(self.grouped_types[name], grouped)]
                while groups:
                    grp, dset = groups.pop()
                    for oname, obj in grp.items():
                        if isinstance(obj, h5py.Group):
                            dset[oname] = {}
                            groups.append((obj, dset[oname]))
                        elif isinstance(obj, h5py.Dataset):
                            dset[oname] = obj[index]
                event[name] = at.Group(name, self.src_type, type(self.grouped_types[name]).__name__, grouped)
            else:
                event[name] = run[self.decode(name)][index]

        return event

    def _cleanup(self):
        pass


class SimSource(Source):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super().__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.count = 0
        self.synced = False
        # load the simulation configuration if not already done
        sim_cfg = self.config.get('config', {})
        if not isinstance(sim_cfg, dict):
            with open(sim_cfg, 'r') as cnf:
                self.config['config'] = json.load(cnf)
        # set up sync connection if specified
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

    def _load_sim_config(self):
        sim_cfg = self.config.get('config', {})
        if not isinstance(sim_cfg, dict):
            with open(sim_cfg, 'r') as cnf:
                sim_cfg = json.load(cnf)
        self.config['config'] = sim_cfg

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
            return self.num_workers * self.count + self.idnum, time.time()


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
            eventid, timestamp = self.timestamp
            if not self.prompt_mode and self.check_heartbeat_boundary(eventid):
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
            yield from self.event(eventid, timestamp, event)
            if self.prompt_mode and self.check_heartbeat_boundary(eventid):
                yield self.heartbeat_msg()
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
            eventid, timestamp = self.timestamp
            if not self.prompt_mode and self.check_heartbeat_boundary(eventid):
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
            yield from self.event(eventid, timestamp, event)
            if self.prompt_mode and self.check_heartbeat_boundary(eventid):
                yield self.heartbeat_msg()
            if count >= self.bound:
                break
            time.sleep(self.interval)
        # signal source has finished
        yield self.unconfigure()
