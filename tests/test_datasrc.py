import pytest

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


def test_psana_source(xtcwriter):
    if xtcwriter is None:
        return
    psana_src_cls = Source.find_source('psana')
    assert psana_src_cls is not None
    idnum = 0
    num_workers = 1
    src_cfg = {}
    src_cfg['interval'] = 0
    src_cfg['init_time'] = 0
    src_cfg['config'] = {'filename': xtcwriter}
    psana_source = psana_src_cls(idnum, num_workers, src_cfg)
    evtgen = psana_source.events()
    next(evtgen)  # first event is the config
    psana_source.requested_names = psana_source.xtcdata_names
    evt = next(evtgen)
    assert(len(evt.payload['xppcspad:raw:raw']) == 18)


def test_static_source(sim_src_cfg):
    src_cls = Source.find_source('static')
    assert src_cls is not None

    idnum = 0
    num_workers = 1

    source = src_cls(idnum, num_workers, sim_src_cfg)

    # check the names from the source are correct
    expected_names = set(sim_src_cfg['config'].keys())
    assert source.names == expected_names

    # check the returned configuration message
    config = source.configure()
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    assert config.payload.payload == expected_names

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
            assert msg.timestamp == num_workers * count + idnum + sim_src_cfg['bound']

    # check that the static source returned the correct number of events
    assert count == sim_src_cfg['bound']


def test_random_source(sim_src_cfg):
    src_cls = Source.find_source('random')
    assert src_cls is not None

    idnum = 0
    num_workers = 1

    source = src_cls(idnum, num_workers, sim_src_cfg)

    # check the names from the source are correct
    expected_names = set(sim_src_cfg['config'].keys())
    assert source.names == expected_names

    # check the returned configuration message
    config = source.configure()
    assert config.mtype == MsgTypes.Transition
    assert config.identity == idnum
    assert isinstance(config.payload, Transition)
    assert config.payload.ttype == Transitions.Configure
    assert config.payload.payload == expected_names

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
            break
