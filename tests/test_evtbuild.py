import pytest

from ami.comm import EventBuilder


@pytest.fixture(scope='function')
def event_builder(request):
    num, depth, color = request.param
    eb = EventBuilder(num, depth, color, "inproc://eb_test")
    yield eb

    # clean up all the zmq stuff
    eb.collector.close()
    eb.ctx.destroy()


@pytest.mark.parametrize('event_builder', [(1, 5, 'worker'), (2, 5, 'worker'), (3, 5, 'worker')], indirect=True)
def test_eb_comp(event_builder):
    num_hb = 5

    for hb in range(num_hb):
        for i in range(event_builder.num_contribs):
            assert not event_builder.heartbeat_ready(hb)
            event_builder.heartbeat(hb, i)
    assert event_builder.heartbeat_ready(hb)


@pytest.mark.parametrize('event_builder', [(2, 1, 'worker'), (2, 5, 'worker')], indirect=True)
def test_eb_depth(event_builder):
    num_hb = 10
    depth = event_builder.depth

    for hb in range(num_hb):
        event_builder.update(hb, 0, 0, {})
        event_builder.heartbeat(hb, 0)
        event_builder.prune()
        assert event_builder.latest == hb
        expected_depth = hb + 1 if hb < depth else depth
        expected_keys = {val for val in range(hb + 1) if (event_builder.latest - val) < depth}
        # check that the contribs and pending dictionaries have the expected num of entries
        assert len(event_builder.contribs.keys()) == expected_depth
        assert len(event_builder.pending.keys()) == expected_depth
        # check that the contribs and pending dictionaries include the expected keys
        assert set(event_builder.contribs.keys()) == expected_keys
        assert set(event_builder.pending.keys()) == expected_keys


@pytest.mark.parametrize('event_builder', [(2, 5, 'worker')], indirect=True)
def test_comp_prune(event_builder):
    # Do the first three heartbeats partially, fourth is complete
    # (hb, list(contributers), expected depth)
    hbs = [
        (0, [0], 1),
        (1, [0], 2),
        (2, [1], 3),
        (3, [0, 1], 0),
    ]
    for hb, contribs, depth in hbs:
        for contrib in contribs:
            event_builder.update(hb, contrib, 0, {})
            event_builder.heartbeat(hb, contrib)
        if event_builder.heartbeat_ready(hb):
            event_builder.prune(hb)
        # check the contribs and pending are the correct size
        assert len(event_builder.contribs.keys()) == depth
        assert len(event_builder.pending.keys()) == depth

    # check that the last hearbeat is the one we expected
    assert event_builder.latest == hbs[-1][0]
