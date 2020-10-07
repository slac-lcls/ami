import pytest
import typing
import numpy as np
import amitypes as at
try:
    import psana
except ImportError:
    psana = None
try:
    import h5py
except ImportError:
    h5py = None

from conftest import psanatest, hdf5test
from ami.data import MsgTypes, Source, Transition, Transitions


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
        'timestamp': int,
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
                if type(data) in at.NumPyTypeDict:
                    assert at.NumPyTypeDict[type(data)] == expected_cfg[name]
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
            assert count == heartbeat_period * (evt.payload + 1)

    # check that the last evt was an unconfigure
    assert evt.mtype == MsgTypes.Transition and evt.payload.ttype == Transitions.Unconfigure


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
    excludes = {'HX2:DVD:GCC:01:PMON', 'HX2:DVD:GPI:01:PMON'}
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
    expected_names = {'timestamp', 'heartbeat', 'source'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'timestamp': int, 'heartbeat': int, 'source': at.DataSource}
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
            assert msg.payload['timestamp'] == expected_ts
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
    expected_names = {'timestamp', 'heartbeat', 'source'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'timestamp': int, 'heartbeat': int, 'source': at.DataSource}
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
            source.request(expected_names[msg.payload])


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
