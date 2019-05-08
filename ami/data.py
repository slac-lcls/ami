import sys
import abc
import zmq
import time
import inspect
import logging
try:
    import psana
except ImportError:
    psana = None
import numpy as np
from enum import Enum
from ami.nptype import Array1d, Array2d, HSDWaveforms


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
        self.interval = src_cfg.get('interval', 0)
        self.init_time = src_cfg.get('init_time', 0)
        self.config = src_cfg.get('config', {})
        self.requested_names = set()
        self.flags = flags or {}
        self._base_types = {
            'timestamp': int,
            'heartbeat': int,
        }

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
        return Message(MsgTypes.Transition,
                       self.idnum,
                       Transition(Transitions.Configure, self.types))

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

    @abc.abstractmethod
    def events(self):
        """
        Generator which yields `Message` containing dictionary of data as payload.
        """
        pass


class PsanaSource(Source):

    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super(__class__, self).__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.delimiter = ":"
        self.xtcdata_names = []
        if psana is not None:
            self.ds = psana.DataSource(src_cfg['filename'])
        else:
            raise NotImplementedError("psana is not available!")

    def _update_xtcdata_names(self, run):
        detinfo = run.detinfo
        self.xtcdata_names = []
        for (detname, det_xface_name), det_attr_list in detinfo.items():
            self.xtcdata_names += [self.delimiter.join((detname, det_xface_name, attr)) for attr in det_attr_list]
        return

    def _fake_detector_types(self, detname):
        types = {
            'EBeam:raw:energy': np.float64,
            'xppcspad:raw:image': np.ndarray,
            'xpphsd:raw:waveform': np.ndarray,
            'xpplaser:raw:laserOn': bool,
            'xpphsd:hsd:waveforms': HSDWaveforms,
        }
        return types.get(detname, object)

    def _names(self):
        return set(self.xtcdata_names)

    def _types(self):
        return {detname: self._fake_detector_types(detname) for detname in self.xtcdata_names}

    def events(self):

        timestamp = 0
        time.sleep(self.init_time)

        while True:
            event = {}
            for run in self.ds.runs():
                self._update_xtcdata_names(run)
                self.detectors = {}  # psana Detector object cache
                yield self.configure()

                for evt in run.events():
                    # FIXME: when we move to real timestamps we should use this line
                    # timestamp = evt.seq.timestamp()
                    if self.check_heartbeat_boundary(timestamp):
                        yield self.heartbeat_msg()

                    for name in self.requested_names:

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

                    yield from self.event(timestamp, event)
                    timestamp += 1
                    time.sleep(self.interval)


class SimSource(Source):
    def __init__(self, idnum, num_workers, heartbeat_period, src_cfg, flags=None):
        super(__class__, self).__init__(idnum, num_workers, heartbeat_period, src_cfg, flags)
        self.count = 0
        self.synced = False
        if 'sync' in self.flags:
            self.ctx = zmq.Context()
            self.ts_src = self.ctx.socket(zmq.REQ)
            self.ts_src.connect(self.flags['sync'])
            self.synced = True

    def _map_dtype(self, config):
        if config['dtype'] == 'Scalar':
            if config.get('integer', False):
                return int
            else:
                return float
        elif config['dtype'] == 'Waveform':
            return Array1d
        elif config['dtype'] == 'Image':
            return Array2d
        else:
            return None

    def _names(self):
        return set(self.config.keys())

    def _types(self):
        return {name: self._map_dtype(config) for name, config in self.config.items()}

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
            for name, config in self.config.items():
                if name in self.requested_names:
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
        self.bound = src_cfg.get('bound', np.inf)

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
            for name, config in self.config.items():
                if name in self.requested_names:
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
