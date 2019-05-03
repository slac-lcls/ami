import pytest

from conftest import psanatest
from ami.data import MsgTypes, Source, Transition, Transitions
from ami.nptype import Array1d, Array2d


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


@psanatest
def test_psana_source(xtcwriter):
    psana_src_cls = Source.find_source('psana')
    assert psana_src_cls is not None
    idnum = 0
    num_workers = 1
    heartbeat_period = 10
    src_cfg = {
        'interval':  0,
        'init_time':  0,
        'filename': xtcwriter,
    }
    psana_source = psana_src_cls(idnum, num_workers, heartbeat_period, src_cfg)
    evtgen = psana_source.events()
    next(evtgen)  # first event is the config
    psana_source.requested_names = psana_source.xtcdata_names
    evt = next(evtgen)
    assert evt.payload['xppcspad:raw:raw'].shape == (2, 3, 6)


def test_static_source(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    idnum = 0
    num_workers = 1
    heartbeat_period = 10

    source = src_cls(idnum, num_workers, heartbeat_period, sim_src_cfg)

    # check the names from the source are correct
    expected_names = {'timestamp', 'heartbeat'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'timestamp': int, 'heartbeat': int}
    for name, cfg in sim_src_cfg['config'].items():
        if cfg["dtype"] == "Scalar":
            if cfg.get("integer", False):
                expected_dtypes[name] = int
            else:
                expected_dtypes[name] = float
        elif cfg["dtype"] == "Waveform":
            expected_dtypes[name] = Array1d
        elif cfg["dtype"] == "Image":
            expected_dtypes[name] = Array2d
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
        assert dtype == expected_dtypes[name]

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

    # check the names from the source are correct
    expected_names = {'timestamp', 'heartbeat'}
    expected_names.update(sim_src_cfg['config'].keys())
    assert source.names == expected_names
    # check the types from the source are correct
    expected_dtypes = {'timestamp': int, 'heartbeat': int}
    for name, cfg in sim_src_cfg['config'].items():
        if cfg["dtype"] == "Scalar":
            if cfg.get("integer", False):
                expected_dtypes[name] = int
            else:
                expected_dtypes[name] = float
        elif cfg["dtype"] == "Waveform":
            expected_dtypes[name] = Array1d
        elif cfg["dtype"] == "Image":
            expected_dtypes[name] = Array2d
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
        assert dtype == expected_dtypes[name]

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
