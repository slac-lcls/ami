import pytest
import re
import zmq
import dill
import threading
import zmq.asyncio
import numpy as np

from ami.comm import GraphCommHandler, AsyncGraphCommHandler


class FakeManager:
    def __init__(self, ctx, addr, conf, use_thread=True):
        self.ctx = ctx
        self.sock = self.ctx.socket(zmq.REP)
        self.sock.bind(addr)
        self.conf = conf
        self.graph = None
        self.feature_req = re.compile("(?P<type>fetch|lookup):(?P<name>.*)")
        if use_thread:
            self.thread = threading.Thread(target=self.run)
            self.thread.daemon = True
            self.thread.start()

    def feature_request(self, request):
        matched = self.feature_req.match(request)
        if matched:
            cmd_type = matched.group('type')
            if cmd_type in self.conf and matched.group('name') in self.conf[cmd_type]:
                self.sock.send_string('ok', zmq.SNDMORE)
                self.sock.send_pyobj(self.conf[cmd_type][matched.group('name')])
            else:
                self.sock.send_string('error')
            return True
        else:
            return False

    def run(self):
        while True:
            request = self.sock.recv_string()
            if request == 'test_exit':
                self.sock.close()
                break
            elif self.feature_request(request):
                pass
            elif request in self.conf:
                if self.sock.getsockopt(zmq.RCVMORE):
                    payload = self.sock.recv()
                    if self.conf[request] == 'graph':
                        self.graph = dill.loads(payload)
                        self.sock.send_string('ok')
                    elif self.conf[request] == 'add_graph':
                        self.graph.add(dill.loads(payload))
                        self.sock.send_string('ok')
                    elif self.conf[request] == 'del_graph':
                        for name in dill.loads(payload):
                            self.graph.remove(name)
                        self.sock.send_string('ok')
                    else:
                        self.sock.send_string('error')
                elif self.conf[request] == 'graph':
                    self.sock.send(dill.dumps(self.graph))
                elif self.conf[request] is None:
                    self.sock.send_string('ok')
                else:
                    self.sock.send_pyobj(self.conf[request])
            else:
                while self.sock.getsockopt(zmq.RCVMORE):
                    self.sock.recv()
                self.sock.send_string('error')


@pytest.fixture(scope='function')
def graph_comm(request, ipc_dir, event_loop):
    ctxs = []
    addr = "ipc://%s/graphcomm_async" % ipc_dir
    # check the requested parameters
    if isinstance(request.param, dict):
        conf = request.param
        use_async = False
    else:
        use_async, conf = request.param

    if use_async:
        ctx = zmq.Context()
        manager = FakeManager(ctx, addr, conf)
        ctxs.append(ctx)
        comm = AsyncGraphCommHandler(addr)
        ctxs.append(comm._ctx)
    else:
        comm = GraphCommHandler(addr)
        ctx = comm._ctx
        manager = FakeManager(ctx, addr, conf)
        ctxs.append(ctx)

    yield comm, conf

    comm._sock.send_string('test_exit')
    manager.thread.join()
    # clean up all the zmq stuff
    for ctx in ctxs:
        ctx.destroy()


@pytest.mark.asyncio
@pytest.mark.parametrize('graph_comm',
                         [
                            (True, {'lookup': {'cspad': int, 'opal': float}}),
                            (True, {'lookup': {'cspad': object, 'opal': type(None)}})
                         ],
                         indirect=True)
async def test_get_type_async(graph_comm):
    comm, conf = graph_comm

    # test looking up the types of names that exist
    assert await comm.get_type('cspad') == conf['lookup']['cspad']
    assert await comm.get_type('opal') == conf['lookup']['opal']
    # test looking up the types of names that do not exist
    assert await comm.get_type('laser') is None
    # test batch lookup of types
    names_to_lookup = ['cspad', 'opal']
    assert await comm.get_type(names_to_lookup) == [conf['lookup'][name] for name in names_to_lookup]
    # test batch lookup of types where they don't exist
    assert await comm.get_type(['laser', 'delta_t']) is None
    # test batch lookup of types where some names don't exist
    names_to_lookup = ['cspad', 'opal', 'delta_t']
    assert await comm.get_type(names_to_lookup) == [conf['lookup'].get(name) for name in names_to_lookup]


@pytest.mark.parametrize('graph_comm',
                         [
                            {'lookup': {'cspad': int, 'opal': float}},
                            {'lookup': {'cspad': object, 'opal': type(None)}},
                         ],
                         indirect=True)
def test_get_type(graph_comm):
    comm, conf = graph_comm

    # test looking up the types of names that exist
    assert comm.get_type('cspad') == conf['lookup']['cspad']
    assert comm.get_type('opal') == conf['lookup']['opal']
    # test looking up the types of names that do not exist
    assert comm.get_type('laser') is None
    # test batch lookup of types
    names_to_lookup = ['cspad', 'opal']
    assert comm.get_type(names_to_lookup) == [conf['lookup'][name] for name in names_to_lookup]
    # test batch lookup of types where they don't exist
    assert comm.get_type(['laser', 'delta_t']) is None
    # test batch lookup of types where some names don't exist
    names_to_lookup = ['cspad', 'opal', 'delta_t']
    assert comm.get_type(names_to_lookup) == [conf['lookup'].get(name) for name in names_to_lookup]


@pytest.mark.asyncio
@pytest.mark.parametrize('graph_comm',
                         [
                            (True, {'get_versions': (3, 0), 'get_graph_version': 3, 'get_features_version': 0}),
                            (True, {'get_versions': (0, 0), 'get_graph_version': 0, 'get_features_version': 0}),
                         ],
                         indirect=True)
async def test_versions_async(graph_comm):
    comm, conf = graph_comm

    # test the version properties of the comm handler
    assert await comm.versions == conf['get_versions']
    assert await comm.graphVersion == conf['get_graph_version']
    assert await comm.featuresVersion == conf['get_features_version']


@pytest.mark.parametrize('graph_comm',
                         [
                            {'get_versions': (3, 0), 'get_graph_version': 3, 'get_features_version': 0},
                            {'get_versions': (0, 0), 'get_graph_version': 0, 'get_features_version': 0},
                         ],
                         indirect=True)
def test_versions(graph_comm):
    comm, conf = graph_comm

    # test the version properties of the comm handler
    assert comm.versions == conf['get_versions']
    assert comm.graphVersion == conf['get_graph_version']
    assert comm.featuresVersion == conf['get_features_version']


@pytest.mark.asyncio
@pytest.mark.parametrize('graph_comm',
                         [
                            (
                                True,
                                {
                                    'get_names': {'cspad', 'delta_t', 'laser'},
                                    'get_sources': {'cspad': float, 'delta_t': int, 'laser': int},
                                    'get_features': {'cspad_img': np.ndarray}
                                }
                            ),
                            (True, {'get_names': set(), 'get_sources':  {}, 'get_features': {}}),
                         ],
                         indirect=True)
async def test_names_async(graph_comm):
    comm, conf = graph_comm

    # test the names of features property give the expected value
    assert await comm.names == conf['get_names']
    assert await comm.sources == conf['get_sources']
    assert await comm.features == conf['get_features']


@pytest.mark.parametrize('graph_comm',
                         [
                            {
                                'get_names': {'cspad', 'delta_t', 'laser'},
                                'get_sources': {'cspad': float, 'delta_t': int, 'laser': int},
                                'get_features': {'cspad_img': np.ndarray}
                            },
                            {'get_names': set(), 'get_sources':  {}, 'get_features': {}},
                         ],
                         indirect=True)
def test_names(graph_comm):
    comm, conf = graph_comm

    # test the names of features property give the expected value
    assert comm.names == conf['get_names']
    assert comm.sources == conf['get_sources']
    assert comm.features == conf['get_features']


@pytest.mark.asyncio
@pytest.mark.parametrize('graph_comm', [(True, {'clear_graph': None, 'reset_features': None})], indirect=True)
async def test_commands_async(graph_comm):
    comm, conf = graph_comm

    assert await comm.clear()
    assert await comm.reset()


@pytest.mark.parametrize('graph_comm', [{'clear_graph': None, 'reset_features': None}], indirect=True)
def test_commands(graph_comm):
    comm, conf = graph_comm

    assert comm.clear()
    assert comm.reset()


@pytest.mark.asyncio
@pytest.mark.parametrize('graph_comm',
                         [(True, {'set_graph': 'graph', 'get_graph': 'graph'})],
                         indirect=True)
async def test_graph_async(graph_comm, complex_graph):
    comm, conf = graph_comm

    # send and retrieve an empty graph
    assert await comm.update(None)
    assert await comm.graph is None

    # send a complex graph
    assert await comm.update(complex_graph)
    # check that the names of the return graph are the same
    assert (await comm.graph).names == complex_graph.names
    # check that the sources of the return graph are the same
    assert (await comm.graph).sources == complex_graph.sources


@pytest.mark.parametrize('graph_comm',
                         [{'set_graph': 'graph', 'get_graph': 'graph'}],
                         indirect=True)
def test_graph(graph_comm, complex_graph):
    comm, conf = graph_comm

    # send and retrieve an empty graph
    assert comm.update(None)
    assert comm.graph is None

    # send a complex graph
    assert comm.update(complex_graph)
    # check that the names of the return graph are the same
    assert comm.graph.names == complex_graph.names
    # check that the sources of the return graph are the same
    assert comm.graph.sources == complex_graph.sources


@pytest.mark.asyncio
@pytest.mark.parametrize('graph_comm',
                         [(
                            True,
                            {
                              'set_graph': 'graph',
                              'get_graph': 'graph',
                              'add_graph': 'add_graph',
                              'del_graph': 'del_graph'
                            }
                         )],
                         indirect=True)
async def test_modify_graph_async(graph_comm, complex_graph):
    comm, conf = graph_comm

    # send a complex graph
    assert await comm.update(complex_graph)

    # add a view to the graph
    assert await comm.view('cspad')
    # check that it is in the graph
    assert comm.auto('cspad') in (await comm.graph).names
    # remove the view
    assert await comm.remove('%s_view' % comm.auto('cspad'))
    assert comm.auto('cspad') not in (await comm.graph).names

    # add multiple views to the graph
    names_to_view = ['cspad', 'delta_t']
    assert await comm.view(names_to_view)
    # check that the views are in the graph
    assert comm.auto('cspad') in (await comm.graph).names
    assert comm.auto('delta_t') in (await comm.graph).names
    # remove the views
    assert await comm.remove(['%s_view' % comm.auto(name) for name in names_to_view])
    assert comm.auto('cspad') not in (await comm.graph).names
    assert comm.auto('delta_t') not in (await comm.graph).names

    # Test the various addNode functions of comm handler
    functions_to_test = {
        comm.addMap:        ('test_map', 'signal', 'test_value', (lambda x: x + 2,)),
        comm.addPickN:      ('test_pickn', 'cspad', 'test_pick_val', (2,)),
        comm.addReduce:     ('test_reduce', ['delta_t', 'laser'], 'test_reduce_value', ()),
        comm.addFilterOn:   ('test_filteron', ['laser'], 'test_laser_on', ()),
        comm.addFilterOff:  ('test_filteroff', ['laser'], 'test_laser_off', ()),
    }

    # Loop over the set of functions to test
    for func, (name, inputs, output, args) in functions_to_test.items():
        # add the node to the graph
        assert await func(name, inputs, output, *args)
        # test that the node was added
        assert output in (await comm.graph).names
        # remove the node
        assert await comm.remove(name)
        assert output not in (await comm.graph).names


@pytest.mark.parametrize('graph_comm',
                         [{
                            'set_graph': 'graph',
                            'get_graph': 'graph',
                            'add_graph': 'add_graph',
                            'del_graph': 'del_graph'
                         }],
                         indirect=True)
def test_modify_graph(graph_comm, complex_graph):
    comm, conf = graph_comm

    # send a complex graph
    assert comm.update(complex_graph)

    # add a view to the graph
    assert comm.view('cspad')
    # check that it is in the graph
    assert comm.auto('cspad') in comm.graph.names
    # remove the view
    assert comm.remove('%s_view' % comm.auto('cspad'))
    assert comm.auto('cspad') not in comm.graph.names

    # add multiple views to the graph
    names_to_view = ['cspad', 'delta_t']
    assert comm.view(names_to_view)
    # check that the views are in the graph
    assert comm.auto('cspad') in comm.graph.names
    assert comm.auto('delta_t') in comm.graph.names
    # remove the views
    assert comm.remove(['%s_view' % comm.auto(name) for name in names_to_view])
    assert comm.auto('cspad') not in comm.graph.names
    assert comm.auto('delta_t') not in comm.graph.names

    # Test the various addNode functions of comm handler
    functions_to_test = {
        comm.addMap:        ('test_map', 'signal', 'test_value', (lambda x: x + 2,)),
        comm.addPickN:      ('test_pickn', 'cspad', 'test_pick_val', (2,)),
        comm.addReduce:     ('test_reduce', ['delta_t', 'laser'], 'test_reduce_value', ()),
        comm.addFilterOn:   ('test_filteron', ['laser'], 'test_laser_on', ()),
        comm.addFilterOff:  ('test_filteroff', ['laser'], 'test_laser_off', ()),
    }

    # Loop over the set of functions to test
    for func, (name, inputs, output, args) in functions_to_test.items():
        # add the node to the graph
        assert func(name, inputs, output, *args)
        # test that the node was added
        assert output in comm.graph.names
        # remove the node
        assert comm.remove(name)
        assert output not in comm.graph.names


@pytest.mark.asyncio
@pytest.mark.parametrize('graph_comm',
                         [
                            (True, {'fetch': {'cspad': 5, '_auto_opal': 6}}),
                            (True, {'fetch': {'cspad': 'apple', '_auto_opal': 'orange'}})
                         ],
                         indirect=True)
async def test_fetch_async(graph_comm):
    comm, conf = graph_comm

    # test we can fetch something we expect
    assert await comm.fetch('cspad') == conf['fetch']['cspad']
    # test the feature where you can fetch names generated by view by regular name
    assert await comm.fetch(comm.auto('opal')) == conf['fetch'][comm.auto('opal')]
    assert await comm.fetch('opal') == conf['fetch'][comm.auto('opal')]
    # check that None is return when we ask for something that isn't there
    assert await comm.fetch('delta_t') is None

    # test bulk fetch for things that aren't there
    assert await comm.fetch(['delta_t', 'laser']) is None
    # test bulk fetch where one item is not there
    assert await comm.fetch(['cspad', 'delta_t']) == [conf['fetch']['cspad'], None]
    # test bulk fetch where all items are there
    assert await comm.fetch(['cspad', comm.auto('opal')]) == [conf['fetch']['cspad'], conf['fetch'][comm.auto('opal')]]
    # test the feature where you can fetch names generated by view by regular name
    assert await comm.fetch(['cspad', 'opal']) == [conf['fetch']['cspad'], conf['fetch'][comm.auto('opal')]]


@pytest.mark.parametrize('graph_comm',
                         [
                            {'fetch': {'cspad': 5, '_auto_opal': 6}},
                            {'fetch': {'cspad': 'apple', '_auto_opal': 'orange'}}
                         ],
                         indirect=True)
def test_fetch(graph_comm):
    comm, conf = graph_comm

    # test we can fetch something we expect
    assert comm.fetch('cspad') == conf['fetch']['cspad']
    # test the feature where you can fetch names generated by view by regular name
    assert comm.fetch(comm.auto('opal')) == conf['fetch'][comm.auto('opal')]
    assert comm.fetch('opal') == conf['fetch'][comm.auto('opal')]
    # check that None is return when we ask for something that isn't there
    assert comm.fetch('delta_t') is None

    # test bulk fetch for things that aren't there
    assert comm.fetch(['delta_t', 'laser']) is None
    # test bulk fetch where one item is not there
    assert comm.fetch(['cspad', 'delta_t']) == [conf['fetch']['cspad'], None]
    # test bulk fetch where all items are there
    assert comm.fetch(['cspad', comm.auto('opal')]) == [conf['fetch']['cspad'], conf['fetch'][comm.auto('opal')]]
    # test the feature where you can fetch names generated by view by regular name
    assert comm.fetch(['cspad', 'opal']) == [conf['fetch']['cspad'], conf['fetch'][comm.auto('opal')]]
