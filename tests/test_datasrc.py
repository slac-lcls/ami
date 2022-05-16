import pytest
import typing
import numpy as np
import amitypes as at
try:
    import h5py
except ImportError:
    h5py = None

from ami import psana
from conftest import psanatest, psana1test, hdf5test
from ami.data import MsgTypes, Source, Transition, Transitions, NumPyTypeDict


@pytest.fixture(scope='function')
def sim_src_cfg():
    return {
        'interval': 0,
        'init_time': 0,
        'bound': 5,
        'config': {
            "delta_t": {"dtype": "Scalar", "range": [0, 10], "integer": True},
            "cspad": {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]},
            "acq": {"dtype": "Waveform", "pedestal": 5, "width": 1, "shape": 512},
            "laser": {"dtype": "Scalar", "range": [0, 2], "integer": True},
        },
    }


def test_find_source():
    src_cls = Source.find_source('static')
    assert src_cls is not None

    src_cls = Source.find_source('random')
    assert src_cls is not None

    src_cls = Source.find_source('notreal')
    assert src_cls is None


@hdf5test
def test_hdf5_source(hdf5writer):
    src_cls = Source.find_source('hdf5')
    assert src_cls is not None
    idnum = 0
    num_workers = 1
    heartbeat_period = 5
    src_cfg = {
        'type': 'hdf5',
        'interval':  0,
        'init_time':  0,
        'files': [str(hdf5writer)],
    }
    expected_cfg = {
        'gasdet': float,
        'ec': int,
        'camera': at.Group,
        'camera:image': at.Array2d,
        'camera:raw': at.Array3d,
        'eventid': int,
        'timestamp': float,
        'heartbeat': int,
        'source': at.DataSource,
    }
    expected_grps = {
        'camera': {
            'image': at.Array2d,
            'raw': at.Array3d,
        }
    }

    source = src_cls(idnum, num_workers, heartbeat_period, src_cfg)

    assert source.src_type == 'hdf5'

    # request all the sources
    source.request(set(expected_cfg))

    # loop over all the events
    count = 0
    for evt in source.events():
        if evt.mtype == MsgTypes.Transition:
            assert evt.identity == idnum
            assert isinstance(evt.payload, Transition)
            if evt.payload.ttype == Transitions.Configure:
                sources = {k: at.loads(v) for k, v in evt.payload.payload.items()}
                assert sources == expected_cfg
        elif evt.mtype == MsgTypes.Datagram:
            assert set(evt.payload) == set(expected_cfg)
            for name, data in evt.payload.items():
                if type(data) in NumPyTypeDict:
                    assert NumPyTypeDict[type(data)] == expected_cfg[name]
                else:
                    assert isinstance(data, expected_cfg[name])

                if isinstance(data, at.DataSource):
                    assert data.cfg == src_cfg
                    assert data.key == 1
                    assert isinstance(data.run, h5py.File)
                    assert data.evt == (count, data.run)
                elif isinstance(data, at.Group):
                    assert data.src == source.src_type
                    assert data.type == 'Group'
                    assert data.name == name
                    assert name in expected_grps
                    assert set(data) == set(expected_grps[name])
                    # check the types of the group
                    for k, v in expected_grps[name].items():
                        assert isinstance(data[k], v)

            count += 1
        elif evt.mtype == MsgTypes.Heartbeat:
            assert count == heartbeat_period * (evt.payload.identity + 1)

    # check that the last evt was an unconfigure
    assert evt.mtype == MsgTypes.Transition and evt.payload.ttype == Transitions.Unconfigure


@psana1test
@pytest.mark.parametrize('psana1_xtc',
                         [('test_031_xpptut15', 'e665-r0540-s01-c00.xtc')],
                         indirect=['psana1_xtc'])
def test_psana1_source(psana1_xtc):
    psana_src_cls = Source.find_source('psana')
    assert psana_src_cls is not None
    idnum = 0
    num_workers = 1
    heartbeat_period = 2
    src_cfg = {
        'type': 'psana',
        'interval':  0,
        'init_time':  0,
        'files': [str(psana1_xtc)],
    }
    # these are broken
    if psana1_xtc.name == 'e665-r0540-s01-c00.xtc':
        excludes = {'evr1:raw', 'evr1:raw:eventCodes'}
        expected_cfg = {
            'XCS-IPM-gon': at.Detector,
            'XCS-IPM-gon:fex': at.Group,
            'XCS-IPM-gon:fex:channel': at.MultiChannelFloat,
            'XCS-IPM-gon:fex:channel:0': float,
            'XCS-IPM-gon:fex:channel:1': float,
            'XCS-IPM-gon:fex:channel:2': float,
            'XCS-IPM-gon:fex:channel:3': float,
            'XCS-IPM-gon:fex:sum': float,
            'XCS-IPM-gon:fex:xpos': float,
            'XCS-IPM-gon:fex:ypos': float,
            'XCS-USB-ENCODER-01': at.Detector,
            'XCS-USB-ENCODER-01:calibconst': typing.Dict,
            'XCS-USB-ENCODER-01:fex': at.Group,
            'XCS-USB-ENCODER-01:fex:values': at.MultiChannelFloat,
            'XCS-USB-ENCODER-01:fex:values:0': float,
            'XCS-USB-ENCODER-01:fex:values:1': float,
            'XCS-USB-ENCODER-01:fex:values:2': float,
            'XCS-USB-ENCODER-01:fex:values:3': float,
            'XCS-USB-ENCODER-01:raw': at.Group,
            'XCS-USB-ENCODER-01:raw:analog_in': at.MultiChannelInt,
            'XCS-USB-ENCODER-01:raw:analog_in:0': int,
            'XCS-USB-ENCODER-01:raw:analog_in:1': int,
            'XCS-USB-ENCODER-01:raw:analog_in:2': int,
            'XCS-USB-ENCODER-01:raw:analog_in:3': int,
            'XCS-USB-ENCODER-01:raw:digital_in': int,
            'XCS-USB-ENCODER-01:raw:encoder_count': at.MultiChannelInt,
            'XCS-USB-ENCODER-01:raw:encoder_count:0': int,
            'XCS-USB-ENCODER-01:raw:encoder_count:1': int,
            'XCS-USB-ENCODER-01:raw:encoder_count:2': int,
            'XCS-USB-ENCODER-01:raw:encoder_count:3': int,
            'XCS-USB-ENCODER-01:raw:status': at.MultiChannelInt,
            'XCS-USB-ENCODER-01:raw:status:0': int,
            'XCS-USB-ENCODER-01:raw:status:1': int,
            'XCS-USB-ENCODER-01:raw:status:2': int,
            'XCS-USB-ENCODER-01:raw:status:3': int,
            'XCS-USB-ENCODER-01:raw:timestamp': int,
            'epix10ka2m': at.Detector,
            'epix10ka2m:raw': at.Group,
            'epix10ka2m:raw:calib': at.Array3d,
            'epix10ka2m:raw:image': at.Array2d,
            'epix10ka2m:raw:raw': at.Array3d,
            'eventid': int,
            'evr0': at.Detector,
            'evr0:raw': at.Group,
            'evr0:raw:eventCodes': typing.List[int],
            'evr1': at.Detector,
            'evr1:raw': at.Group,
            'evr1:raw:eventCodes': typing.List[int],
            'heartbeat': int,
            'opal_1': at.Detector,
            'opal_1:raw': at.Group,
            'opal_1:raw:calib': at.Array3d,
            'opal_1:raw:image': at.Array2d,
            'opal_1:raw:raw': at.Array3d,
            'source': at.DataSource,
            'timestamp': float,
        }
        expected_grps = {
            'XCS-IPM-gon:fex': {
                'channel': at.MultiChannelFloat,
                'sum': float,
                'xpos': float,
                'ypos': float,
            },
            'XCS-USB-ENCODER-01:fex': {
                'values': at.MultiChannelFloat,
            },
            'XCS-USB-ENCODER-01:raw': {
                'analog_in': at.MultiChannelInt,
                'digital_in': int,
                'encoder_count': at.MultiChannelInt,
                'status': at.MultiChannelInt,
                'timestamp': int,
            },
            'epix10ka2m:raw': {
                'raw': at.Array3d,
                'calib': at.Array3d,
                'image': at.Array2d,
            },
            'opal_1:raw': {
                'raw': at.Array3d,
                'calib': at.Array3d,
                'image': at.Array2d,
            },
            'evr0:raw': {
                'eventCodes': list,
            },
            'evr1:raw': {
                'eventCodes': list,
            },
        }
        expected_grp_types = {
            'XCS-IPM-gon:fex': 'IpimbDetector',
            'XCS-USB-ENCODER-01:fex': 'UsdUsbDetector',
            'XCS-USB-ENCODER-01:raw': 'RawUsdUsbDetector',
            'epix10ka2m:raw': 'AreaDetector',
            'opal_1:raw': 'AreaDetector',
            'evr0:raw': 'EvrDetector',
            'evr1:raw': 'EvrDetector',
        }
    else:
        excludes = set()
        expected_cfg = {}
        expected_grps = {}
        expected_grp_types = {}
    psana_source = psana_src_cls(idnum, num_workers, heartbeat_period, src_cfg)

    assert psana_source.src_type == 'psana'

    evtgen = psana_source.events()

    # check the returned configuration message
    config = next(evtgen)  # first event is the config
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    sources = {k: at.loads(v) for k, v in config.payload.payload.items()}
    assert sources == expected_cfg

    # check the returned step message
    step = next(evtgen)
    assert step.mtype == MsgTypes.Transition
    assert step.identity == idnum
    assert isinstance(step.payload, Transition)
    assert step.payload.ttype == Transitions.BeginStep
    assert step.payload.payload == 0

    # request all the sources
    psana_source.request(set(expected_cfg))

    # patch expected_cfg to remove typing._GenericAlias and convert to real type
    expected_types = {}
    for name, cls in expected_cfg.items():
        if isinstance(cls, typing._GenericAlias):
            cls = at.loads('typing.'+cls._name)
        expected_types[name] = cls

    # loop over all the events
    for count, msg in enumerate(evtgen):
        if msg.mtype == MsgTypes.Datagram:
            assert set(msg.payload) == set(expected_cfg)
            for name, data in msg.payload.items():
                if name in excludes:
                    continue

                if isinstance(data, np.integer):
                    data = int(data)
                elif isinstance(data, np.floating):
                    data = float(data)
                assert isinstance(data, expected_types[name])

                if isinstance(data, at.DataSource):
                    assert data.cfg == src_cfg
                    assert data.key == 1
                    assert isinstance(data.run, psana.datasource.Run)
                    assert isinstance(data.evt, psana.datasource.Event)
                elif isinstance(data, at.Group):
                    assert name in expected_grps and name in expected_grp_types
                    assert data.src == psana_source.src_type
                    assert data.type == expected_grp_types[name]
                    assert data.name == name
                    assert set(data) == set(expected_grps[name])
                    # check the types of the group
                    for k, v in expected_grps[name].items():
                        assert isinstance(data[k], v)
        elif msg.mtype == MsgTypes.Heartbeat:
            break

    # check the number of events we processed
    assert count == heartbeat_period


@psanatest
def test_psana_source(xtcwriter):
    psana_src_cls = Source.find_source('psana')
    assert psana_src_cls is not None
    idnum = 0
    num_workers = 1
    heartbeat_period = 10
    src_cfg = {
        'type': 'psana',
        'interval':  0,
        'init_time':  0,
        'files': [str(xtcwriter)],
    }
    # these are broken in xtcwriter
    excludes = {'HX2:DVD:GCC:01:PMON', 'HX2:DVD:GPI:01:PMON', 'motor1', 'motor2'}
    expected_cfg = {
        'HX2:DVD:GCC:01:PMON': float,
        'HX2:DVD:GPI:01:PMON': str,
        'motor1': float,
        'motor2': float,
        'xpphsd': at.Detector,
        'xpphsd:calibconst': typing.Dict,
        'xpphsd:raw:calib': at.Array1d,
        'xpphsd:raw': at.Group,
        'xpphsd:fex:calib': at.Array1d,
        'xpphsd:fex': at.Group,
        'xppcspad': at.Detector,
        'xppcspad:calibconst': typing.Dict,
        'xppcspad:raw:calib': at.Array3d,
        'xppcspad:raw:image': at.Array2d,
        'xppcspad:raw:raw': at.Array3d,
        'xppcspad:raw': at.Group,
        'epicsinfo': at.Detector,
        'epicsinfo:epicsinfo': typing.Dict,
        'epicsinfo:calibconst': typing.Dict,
        'eventid': int,
        'timestamp': float,
        'heartbeat': int,
        'source': at.DataSource,
    }
    expected_grps = {
        'xpphsd:raw': {
            'calib': at.Array1d,
        },
        'xpphsd:fex': {
            'calib': at.Array1d,
        },
        'xppcspad:raw': {
            'calib': at.Array3d,
            'image': at.Array2d,
            'raw': at.Array3d,
        },
    }
    expected_grp_types = {
        'xpphsd:raw': 'hsd_raw_0_0_0',
        'xpphsd:fex': 'hsd_fex_4_5_6',
        'xppcspad:raw': 'cspad_raw_2_3_42',
    }
    psana_source = psana_src_cls(idnum, num_workers, heartbeat_period, src_cfg)

    assert psana_source.src_type == 'psana'

    evtgen = psana_source.events()

    # check the returned configuration message
    config = next(evtgen)  # first event is the config
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    sources = {k: at.loads(v) for k, v in config.payload.payload.items()}
    assert sources == expected_cfg

    # check the returned step message
    step = next(evtgen)
    assert step.mtype == MsgTypes.Transition
    assert step.identity == idnum
    assert isinstance(step.payload, Transition)
    assert step.payload.ttype == Transitions.BeginStep
    assert step.payload.payload == 0

    # request all the sources
    psana_source.request(set(expected_cfg))

    # loop over all the events
    for count, msg in enumerate(evtgen):
        if msg.mtype == MsgTypes.Datagram:
            assert set(msg.payload) == set(expected_cfg)
            for name, data in msg.payload.items():
                if name in excludes:
                    continue

                assert isinstance(data, expected_cfg[name])

                if isinstance(data, at.DataSource):
                    assert data.cfg == src_cfg
                    assert data.key == 1
                    assert isinstance(data.run, psana.psexp.run.Run)
                    assert isinstance(data.evt, psana.event.Event)
                elif isinstance(data, at.Group):
                    assert name in expected_grps and name in expected_grp_types
                    assert data.src == psana_source.src_type
                    assert data.type == expected_grp_types[name]
                    assert data.name == name
                    assert set(data) == set(expected_grps[name])
                    # check the types of the group
                    for k, v in expected_grps[name].items():
                        assert isinstance(data[k], v)
        elif msg.mtype == MsgTypes.Heartbeat:
            break

    # check the number of events we processed
    assert count == heartbeat_period


def test_static_source(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    idnum = 0
    num_workers = 1
    heartbeat_period = 10

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    assert source.src_type == 'static'

    # check the names from the source are correct
    expected_names = {'eventid', 'timestamp', 'heartbeat', 'source'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'eventid': int, 'timestamp': float, 'heartbeat': int, 'source': at.DataSource}
    for name, cfg in sim_src_cfg['config'].items():
        if cfg["dtype"] == "Scalar":
            if cfg.get("integer", False):
                expected_dtypes[name] = int
            else:
                expected_dtypes[name] = float
        elif cfg["dtype"] == "Waveform":
            expected_dtypes[name] = at.Array1d
        elif cfg["dtype"] == "Image":
            expected_dtypes[name] = at.Array2d
        else:
            expected_dtypes[name] = None
    assert source.types == expected_dtypes

    # check the returned configuration message
    config = source.configure()
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    assert set(config.payload.payload) == expected_names
    for name, dtype in config.payload.payload.items():
        assert at.loads(dtype) == expected_dtypes[name]

    # do a first loop over the data (events should be empty)
    count = 0
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            assert not msg.payload
            count += 1
            assert msg.timestamp == num_workers * count + idnum

    # check that the static source returned the correct number of events
    assert count == sim_src_cfg['bound']

    # test the request feature of the source
    assert not source.requested_names
    source.request(expected_names)
    assert source.requested_names == expected_names

    # do a second loop over the data (events should be non-empty)
    count = 0
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            for name, cfg in sim_src_cfg['config'].items():
                if cfg["dtype"] == "Scalar":
                    assert msg.payload[name] == 1
                elif (cfg["dtype"] == "Image") or (cfg["dtype"] == "Waveform"):
                    assert (msg.payload[name] == 1).all()
            count += 1
            expected_ts = num_workers * count + idnum + sim_src_cfg['bound']
            assert msg.timestamp == expected_ts
            assert msg.payload['eventid'] == expected_ts
            assert msg.payload['heartbeat'] == expected_ts // heartbeat_period

    # check that the static source returned the correct number of events
    assert count == sim_src_cfg['bound']


def test_random_source(sim_src_cfg):
    src_cls = Source.find_source('random')
    assert src_cls is not None

    idnum = 0
    num_workers = 1
    heartbeat_period = 10

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    assert source.src_type == 'random'

    # check the names from the source are correct
    expected_names = {'eventid', 'timestamp', 'heartbeat', 'source'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'eventid': int, 'timestamp': float, 'heartbeat': int, 'source': at.DataSource}
    for name, cfg in sim_src_cfg['config'].items():
        if cfg["dtype"] == "Scalar":
            if cfg.get("integer", False):
                expected_dtypes[name] = int
            else:
                expected_dtypes[name] = float
        elif cfg["dtype"] == "Waveform":
            expected_dtypes[name] = at.Array1d
        elif cfg["dtype"] == "Image":
            expected_dtypes[name] = at.Array2d
        else:
            expected_dtypes[name] = None
    assert source.types == expected_dtypes

    # check the returned configuration message
    config = source.configure()
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    assert set(config.payload.payload) == expected_names
    for name, dtype in config.payload.payload.items():
        assert at.loads(dtype) == expected_dtypes[name]

    # do a first loop over the data (events should be empty)
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            assert not msg.payload
            break

    # test the request feature of the source
    assert not source.requested_names
    source.request(expected_names)
    assert source.requested_names == expected_names

    # do a second loop over the data (events should be non-empty)
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            for name in expected_names:
                assert name in msg.payload
                if expected_dtypes[name] == at.Array1d:
                    assert type(msg.payload[name]) == np.ndarray
                    assert msg.payload[name].ndim == 1
                elif expected_dtypes[name] == at.Array2d:
                    assert type(msg.payload[name]) == np.ndarray
                    assert msg.payload[name].ndim == 2
                else:
                    assert type(msg.payload[name]) == expected_dtypes[name]
            break


def test_source_heartbeat(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    sim_src_cfg['bound'] = 10

    idnum = 0
    num_workers = 1
    heartbeat_period = 3

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    # loop over the events testing that heartbeats appear when expected
    count = 0
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            count += 1
        elif msg.mtype == MsgTypes.Heartbeat:
            # check that heart happened between the right events
            assert ((count + 1) % heartbeat_period) == 0
            # check that the number of the heartbeat is as expected
            assert msg.payload == ((count - 1) // heartbeat_period)


def test_source_request(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    sim_src_cfg['bound'] = 10

    idnum = 0
    num_workers = 1
    heartbeat_period = 3

    expected_names = [
        ['cspad'],
        [],
        ['cspad', 'delta_t'],
    ]

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    # loop over the events testing that data dict keys match the requested names
    for msg in source.events():
        if msg.mtype == MsgTypes.Datagram:
            assert set(msg.payload.keys()) == source.requested_names
        elif msg.mtype == MsgTypes.Heartbeat:
            source.request(expected_names[msg.payload.identity])


def test_source_badrequest(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    sim_src_cfg['bound'] = 10

    idnum = 0
    num_workers = 1
    heartbeat_period = 3

    requested_names = [
        ('cspad', True),
        ('notthere', False),
    ]

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)
    source.request(entry[0] for entry in requested_names)

    for name, present in requested_names:
        # check that the requested names are there
        assert name in source.requested_names
        # check that the bad names are not in requested_data
        assert (name in source.requested_data) is present
