import pytest
import zmq
import dill

from ami.data import MsgTypes, Transitions, Message, CollectorMessage
from ami.comm import Colors, ContributionBuilder, TransitionBuilder, EventBuilder
from ami.graphkit_wrapper import Graph
from ami.graph_nodes import PickN, Var


class FakeBuilder(ContributionBuilder):
    def __init__(self, num_contribs):
        super().__init__(num_contribs)
        self.completed = set()

    def _complete(self, eb_key, identity):
        self.completed.add((eb_key, identity))

    def _update(self, eb_key, eb_id, data):
        if eb_key not in self.pending:
            self.pending[eb_key] = {}
        self.pending[eb_key][eb_id] = data


@pytest.fixture(scope='module')
def eb_graph():
    graph = Graph(name='graph')
    graph.add(PickN(name='pick1_values', N=1,
                    inputs=[Var(name='values', type=int)],
                    outputs=[Var(name='value', type=int)]))
    return dill.dumps(graph)


@pytest.fixture(scope='function')
def event_builder(request):
    num, depth = request.param
    eb = EventBuilder(num, depth, Colors.LocalCollector, "inproc://eb_test")
    yield eb

    # clean up all the zmq stuff
    eb.collector.close()
    eb.ctx.destroy()


@pytest.fixture(scope='function')
def transition_builder(request):
    num = request.param
    addr = "inproc://eb_test"
    tb = TransitionBuilder(num, addr)
    yield num, addr, tb

    # clean up all the zmq stuff
    tb.collector.close()
    tb.ctx.destroy()


@pytest.fixture(scope='function')
def test_builder(request):
    return FakeBuilder(request.param)


@pytest.mark.parametrize('test_builder, num_contribs, expected',
                         [
                            (1, 1, True),
                            (2, 2, True),
                            (3, 2, False),
                         ],
                         indirect=['test_builder'])
def test_builder_comp(test_builder, num_contribs, expected):
    num_hb = 5
    identity = 0
    expected_comp = set()

    for hb in range(num_hb):
        # check that the heartbeat is not ready
        assert not test_builder.ready(hb)
        for contrib in range(num_contribs):
            # check that the heartbeat is not ready
            assert not test_builder.ready(hb)
            test_builder.update(hb, contrib, (hb << 4) + contrib)
            # check that the expected data was added to pending
            assert test_builder.pending[hb][contrib] == (hb << 4) + contrib
        if expected:
            # check that the event builder is ready as expected
            assert test_builder.ready(hb)
            expected_comp.add((hb, identity))
            test_builder.complete(hb, identity)
            # check that pending has been clearted
            assert hb not in test_builder.pending
            # check that the completion function was called
            assert test_builder.completed
            assert test_builder.completed == expected_comp
        else:
            # check that the event builder is ready as expected
            assert not test_builder.ready(hb)
            # check that pending has not been clearted
            assert hb in test_builder.pending
            # check that the completion function was not called
            assert not test_builder.completed


@pytest.mark.parametrize('test_builder, contrib_id, bad',
                         [
                            (1, -1, True),
                            (1, 0, False),
                            (1, 1, True),
                            (2, 0, False),
                            (2, 1, False),
                            (2, 2, True),
                         ],
                         indirect=['test_builder'])
def test_builder_valid_contributors(test_builder, contrib_id, bad):
    try:
        test_builder.update(0, contrib_id, "test_data")
        # check that we didn't get here with an invalid contributor id
        assert not bad
    except ValueError:
        # check that a ValueError was thrown on an invalid contributor id
        assert bad


@pytest.mark.parametrize('transition_builder, ttype',
                         [
                            (1, Transitions.Configure),
                            (2, Transitions.Configure),
                            (3, Transitions.Configure),
                            (1, Transitions.Allocate),
                            (2, Transitions.Allocate),
                            (3, Transitions.Allocate),
                         ],
                         indirect=['transition_builder'])
def test_tb_comp(transition_builder, ttype):
    contribs, addr, tb = transition_builder
    sock = tb.ctx.socket(zmq.PULL)
    sock.bind(addr)
    idnum = 0
    alt_key = "alt_key"
    payload = {"test": "val"}

    for contrib in range(contribs):
        assert not tb.ready(alt_key)
        assert not tb.ready(ttype)
        # update the transition
        tb.update(ttype, contrib, payload)
    # check that the builder is ready for the expected type
    assert tb.ready(ttype)
    # check that other keys aren't ready
    assert not tb.ready(alt_key)

    # complete the transition
    tb.complete(ttype, idnum)

    try:
        msg = sock.recv_pyobj(zmq.NOBLOCK)
    except zmq.Again:
        msg = None
    # test that the sock recv worked
    assert msg is not None
    assert isinstance(msg, Message)
    assert msg.mtype == MsgTypes.Transition
    assert msg.identity == idnum
    # test the value in the results dictionary from the message
    assert msg.payload.ttype == ttype
    assert msg.payload.payload == payload


@pytest.mark.parametrize('event_builder', [(1, 5), (2, 5), (3, 5)], indirect=True)
def test_eb_comp(event_builder):
    name = 'test'
    num_hb = 5
    event_builder.create(name)

    for hb in range(num_hb):
        for i in range(event_builder.num_contribs):
            assert not event_builder.ready(name, hb)
            event_builder.mark(name, hb, i)
    assert event_builder.ready(name, hb)


@pytest.mark.parametrize('event_builder', [(2, 1), (2, 5)], indirect=True)
def test_eb_depth(event_builder):
    name = 'test'
    num_hb = 10
    depth = event_builder.depth
    event_builder.create(name)

    for hb in range(num_hb):
        event_builder.update(name, hb, 0, 0, {})
        event_builder.prune(name)
        assert event_builder.latest(name) == hb
        expected_depth = hb + 1 if hb < depth else depth
        expected_keys = {val for val in range(hb + 1) if (event_builder.latest(name) - val) < depth}
        # check that the contribs and pending dictionaries have the expected num of entries
        assert len(event_builder.contribs(name).keys()) == expected_depth
        assert len(event_builder.pending(name).keys()) == expected_depth
        # check that the contribs and pending dictionaries include the expected keys
        assert set(event_builder.contribs(name).keys()) == expected_keys
        assert set(event_builder.pending(name).keys()) == expected_keys


@pytest.mark.parametrize('event_builder', [(2, 5)], indirect=True)
def test_comp_prune(event_builder):
    # Do the first three heartbeats partially, fourth is complete
    # (hb, list(contributers), expected depth)
    name = 'test'
    hbs = [
        (0, [0], 1),
        (1, [0], 2),
        (2, [1], 3),
        (3, [0, 1], 0),
    ]
    event_builder.create(name)

    for hb, contribs, depth in hbs:
        for contrib in contribs:
            event_builder.update(name, hb, contrib, 0, {})
        if event_builder.ready(name, hb):
            event_builder.prune(name, hb)
        # check the contribs and pending are the correct size
        assert len(event_builder.contribs(name).keys()) == depth
        assert len(event_builder.pending(name).keys()) == depth

    # check that the last hearbeat is the one we expected
    assert event_builder.latest(name) == hbs[-1][0]


@pytest.mark.parametrize('event_builder', [(2, 5)], indirect=True)
def test_comp_graph(event_builder, eb_graph):
    sock = event_builder.ctx.socket(zmq.PULL)
    sock.bind("inproc://eb_test")

    hb = 0
    idnum = 0
    graph_version = 0
    graph_name = 'test'
    nworkers = event_builder.num_contribs
    ncollectors = 1
    value = 6
    data = {'value_%s' % Colors.Worker: value}

    # add the graph to the event builder
    eb_graph = dill.loads(eb_graph)
    eb_graph.compile(num_workers=nworkers, num_local_collectors=ncollectors)
    event_builder.set_graph(graph_name, graph_version, dill.dumps(eb_graph))
    # check that the graph is there
    assert graph_version in event_builder.graphs(graph_name)

    event_builder.update(graph_name, hb, 0, graph_version, data)
    event_builder.update(graph_name, hb, 1, graph_version, data)

    # test that the heartbeat is ready
    assert event_builder.ready(graph_name, hb)

    event_builder.complete(graph_name, hb, idnum)

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
    assert msg.name == graph_name
    assert msg.version == graph_version
    # test the value in the results dictionary from the message
    assert msg.payload.get('value_%s' % Colors.LocalCollector) == value
