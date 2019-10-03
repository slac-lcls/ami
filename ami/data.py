import sys
import abc
import zmq
import time
import typing
import inspect
import logging
try:
    import psana
except ImportError:
    psana = None
import numpy as np
import amitypes as at
from enum import Enum


logger = logging.getLogger(__name__)


class MsgTypes(Enum):
    Transition = 0
    Heartbeat = 1
    Datagram = 2
    Graph = 3


class Transitions(Enum):
    Allocate = 0
    Configure = 1
    Enable = 2
    Disable = 3


class Transition(object):
    def __init__(self, ttype, payload):
        self.ttype = ttype
        self.payload = payload

    def __str__(self):
        return "Transition:\n type: %s\n data: %s" % (self.ttype, self.payload)


class Datagram(object):
    def __init__(self, name, dtype, data=None):
        self.name = name
        self.dtype = dtype
        self.data = data

    def __str__(self):
        return "Datagram:\n dtype: %s\n data: %s" % (self.dtype, self.data)


class Message(object):
    def __init__(self, mtype, identity, payload):
        """
        Message container

        Args:
            mtype (MsgTypes): Message type

            identity (int): Message id number

            payload (dict): Message payload
        """
        self.mtype = mtype
        self.identity = identity
        self.payload = payload


class CollectorMessage(Message):
    def __init__(self, mtype, identity, heartbeat, name, version, payload):
        super(__class__, self).__init__(mtype, identity, payload)
        self.heartbeat = heartbeat
        self.name = name
        self.version = version


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
        self._base_types = {
            'timestamp': int,
            'heartbeat': int,
        }
        self._base_names = set(self._base_types)
        self._flag_types = {
            'interval': float,
            'init_time': float,
            'bound': int,
            'repeat': lambda s: s.lower() == 'true',
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
            An object of type `Message` which includes a list of
            names of the currently available detectors/data.
        """
        self.request(self.requested_names)
        flatten_types = {name: at.dumps(dtype) for name, dtype in self.types.items()}
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.Configure, flatten_types))

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
        base = [('timestamp', timestamp), ('heartbeat', self.heartbeat)]
        data.update({k: v for k, v in base if k in self.requested_names})
        msg = Message(MsgTypes.Datagram, self.idnum, data)
        msg.timestamp = timestamp
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


class PsanaSource(Source):

    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super(__class__, self).__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.ds_loop_count = 0
        self.ds_keys = {
            'exp', 'dir', 'files', 'shmem', 'filter', 'batch_size', 'max_events', 'sel_det_ids', 'det_name'
        }
        self.repeat_mode = self.config.get('repeat', False) and (not self.config.get('shmem', False))
        self.delimiter = ":"
        self.xtcdata_names = []
        self.xtcdata_types = {}
        if psana is not None:
            ps_kwargs = {k: self.config[k] for k in self.ds_keys if k in self.config}
            self.ds = psana.DataSource(**ps_kwargs)
        else:
            raise NotImplementedError("psana is not available!")

    def _update_hsd_segment_names(self, seg_name, seg_type, seg_chans):
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
                    self.xtcdata_names.append(chan_name)
                    self.xtcdata_types[chan_name] = chan_type
                    self.special_names[chan_name] = (seg_name, accessor)

    def _update_xtcdata_names(self, run):
        detinfo = run.detinfo
        self.xtcdata_names = []
        self.xtcdata_types = {}
        self.special_names = {}
        for (detname, det_xface_name), det_attr_list in detinfo.items():
            for attr in det_attr_list:
                attr_name = self.delimiter.join((detname, det_xface_name, attr))
                det_interface = run.Detector(detname)
                try:
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
                        self._update_hsd_segment_names(attr_name, attr_type, seg_chans)
                    else:
                        logger.debug("DataSrc: unsupported HSDType: %s", attr_type)
                else:
                    self.xtcdata_names.append(attr_name)
                    self.xtcdata_types[attr_name] = attr_type

    def _names(self):
        return set(self.xtcdata_names)

    def _types(self):
        return self.xtcdata_types

    @property
    def repeat(self):
        if self.ds_loop_count and not self.repeat_mode:
            return False
        else:
            self.ds_loop_count += 1
            return True

    def events(self):

        counter = 0
        time.sleep(self.init_time)

        while self.repeat:
            event = {}
            for run in self.ds.runs():
                self._update_xtcdata_names(run)
                self.detectors = {}  # psana Detector object cache
                yield self.configure()

                for evt in run.events():
                    # If in repeat mode (a.k.a. looping forever over the same events) then use fake ts for heartbeats
                    if self.check_heartbeat_boundary(counter if self.repeat_mode else evt.timestamp):
                        yield self.heartbeat_msg()

                    for name in self.requested_data:
                        # each name is like "detname:drp_class_name:attrN"
                        namesplit = name.split(':')
                        detname = namesplit[0]

                        # if this is the first time we request a detector,
                        # make & cache the psana Detector object
                        if detname not in self.detectors:
                            self.detectors[detname] = run.Detector(detname)

                        # loop to the bottom level of the Det obj and get data
                        obj = self.detectors[detname]
                        for token in namesplit[1:]:
                            obj = getattr(obj, token)
                        event[name] = obj(evt)

                    for name, sub_names in self.requested_special.items():
                        namesplit = name.split(':')
                        detname = namesplit[0]

                        # if this is the first time we request a detector,
                        # make & cache the psana Detector object
                        if detname not in self.detectors:
                            self.detectors[detname] = run.Detector(detname)

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

                    yield from self.event(counter if self.repeat_mode else evt.timestamp, event)
                    counter += 1
                    time.sleep(self.interval)


class SimSource(Source):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super(__class__, self).__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
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
        super(__class__, self).__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
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


class StaticSource(SimSource):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super(__class__, self).__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
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
