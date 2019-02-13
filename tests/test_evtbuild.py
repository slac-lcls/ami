import pytest
import zmq
import dill

from ami.data import MsgTypes, CollectorMessage
from ami.comm import Colors, EventBuilder
from ami.graphkit_wrapper import Graph
from ami.graph_nodes import PickN


@pytest.fixture(scope='module')
def eb_graph():
    graph = Graph(name='graph')
    graph.add(PickN(name='pick1_values', N=1, inputs=['values'], outputs=['value']))
    return dill.dumps(graph)


@pytest.fixture(scope='function')
def event_builder(request):
    num, depth = request.param
    eb = EventBuilder(num, depth, Colors.LocalCollector, "inproc://eb_test")
    yield eb

    # clean up all the zmq stuff
    eb.collector.close()
    eb.ctx.destroy()


@pytest.mark.parametrize('event_builder', [(1, 5), (2, 5), (3, 5)], indirect=True)
def test_eb_comp(event_builder):
    num_hb = 5

    for hb in range(num_hb):
        for i in range(event_builder.num_contribs):
            assert not event_builder.heartbeat_ready(hb)
            event_builder.heartbeat(hb, i)
    assert event_builder.heartbeat_ready(hb)


@pytest.mark.parametrize('event_builder', [(2, 1), (2, 5)], indirect=True)
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


@pytest.mark.parametrize('event_builder', [(2, 5)], indirect=True)
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


@pytest.mark.parametrize('event_builder', [(2, 5)], indirect=True)
def test_comp_graph(event_builder, eb_graph):
    sock = event_builder.ctx.socket(zmq.PULL)
    sock.bind("inproc://eb_test")

    hb = 0
    idnum = 0
    graph_version = 0
    nworkers = event_builder.num_contribs
    ncollectors = 1
    value = 6
    data = {'value_%s' % Colors.Worker: value}

    # add the graph to the event builder
    event_builder.set_graph(graph_version, nworkers, ncollectors, eb_graph)
    # check that the graph is there
    assert graph_version in event_builder.graphs

    event_builder.update(hb, 0, graph_version, data)
    event_builder.heartbeat(hb, 0)
    event_builder.update(hb, 1, graph_version, data)
    event_builder.heartbeat(hb, 1)

    # test that the heartbeat is ready
    assert event_builder.heartbeat_ready(hb)

    event_builder.complete(hb, idnum)

    try:
        msg = sock.recv_pyobj(zmq.NOBLOCK)
    except zmq.Again:
        msg = None
    # test that the sock recv worked
    assert msg is not None
    # check that the message 'header' is as expected
    assert isinstance(msg, CollectorMessage)
    assert msg.mtype == MsgTypes.Datagram
    assert msg.identity == idnum
    assert msg.heartbeat == hb
    assert msg.version == graph_version
    # test the value in the results dictionary from the message
    assert msg.payload.get('value_%s' % Colors.LocalCollector) == value
