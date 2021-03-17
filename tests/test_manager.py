import pytest
import zmq
import time
import dill
import functools
import numpy as np
import multiprocessing as mp
import ami.graph_nodes as gn
import amitypes as at

from ami.data import MsgTypes, Transitions, Transition, Heartbeat
from ami.comm import AutoExport, Store, Node, ZmqHandler, GraphCommHandler
from ami.manager import run_manager


class ExportHelper:
    def __init__(self, addr, ctx):
        self.ctx = ctx
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sock.connect(addr)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.sock.close()

    def recv(self):
        topic = self.sock.recv_string()
        graph = self.sock.recv_string()
        data = self.sock.recv_pyobj()
        return topic, graph, data

    @staticmethod
    def store(version=0, features=None):
        if features is None:
            features = {}
        return {'version': version, 'features': features}

    @staticmethod
    def graph(version=0, names=None, sources=None, graph=None):
        if names is None:
            names = set()
        if sources is None:
            sources = {}
        else:
            sources = {src: at.dumps(typ) for src, typ in sources.items()}
        return {'version': version, 'names': names, 'sources': sources, 'dill': dill.dumps(graph)}


class ResultsInjector(Node, ZmqHandler):
    def __init__(self, addrs, ctx, identity, name, version=0):
        Node.__init__(self, identity, addrs['graph'], addrs['msg'], ctx=ctx)
        ZmqHandler.__init__(self, addrs['results'], ctx=ctx)
        self.comm = GraphCommHandler(name, addrs['comm'], ctx=ctx)
        self._name = name
        self.version = version
        self.exceptions = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.graph_comm.close()
        self.node_msg_comm.close()
        self.collector.close()
        self.comm.close()

    @property
    def name(self):
        return self._name

    @property
    def wait_counter(self):
        hb = self.comm.heartbeat
        return hb if hb is not None else -1

    def recv_graph(self, name, version, args, payload):
        self.store_graph(name, version, payload)

    def recv_graph_add(self, name, version, args, payload):
        self.store_graph(name, version, payload)

    def recv_graph_del(self, name, version, args, payload):
        self.store_graph(name, version, payload)

    def recv_graph_purge(self, name, version, args, payload):
        if name in self.graphs:
            del self.graphs[name]

    def recv_graph_exception(self, name, version, exception):
        if name not in self.exceptions:
            self.exceptions[name] = {}
        self.exceptions[name][version] = exception

    def store_graph(self, name, version, payload):
        if name not in self.graphs:
            self.graphs[name] = {}
        self.graphs[name][version] = payload

    def mark(self):
        count = self.wait_counter + 1
        self.collector_message(self.node, Heartbeat(count, 0), self.name, self.version, {})
        return count

    def partition(self, payload, wait=False):
        payload = {src: at.dumps(typ) for src, typ in payload.items()}
        self.message(MsgTypes.Transition, self.node, Transition(Transitions.Configure, payload))
        if wait:
            self.wait_for(self.mark())
        else:
            return self.mark

    def data(self, hb, payload, wait=False):
        self.collector_message(self.node, Heartbeat(hb, 0), self.name, self.version, payload)
        if wait:
            self.wait_for(hb)
        else:
            return hb

    def wait_for(self, counter):
        while self.wait_counter < counter:
            time.sleep(0.01)

    def wait_graph(self, timeout=None):
        if timeout is None:
            self.graph_comm.recv()
            return True
        else:
            failed = True
            start = time.time()
            while time.time() - start < timeout:
                try:
                    self.graph_comm.recv(False)
                    failed = False
                    break
                except zmq.Again:
                    pass
            return not failed


@pytest.fixture(scope='function')
def result_data():
    return {
        'laser': True,
        'delta_t': np.random.random(),
        'wave8': np.random.normal(0, 20.0, 100),
        'cspad': np.random.normal(30, 5.0, (10, 10)),
    }


@pytest.fixture(scope='function')
def manager_proc(ipc_dir):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    addrs = {
        'results': 'ipc://%s/manager_results' % ipc_dir,
        'comm': 'ipc://%s/manager_comm' % ipc_dir,
        'graph': 'ipc://%s/manager_graph' % ipc_dir,
        'msg': 'ipc://%s/manager_msg' % ipc_dir,
        'info': 'ipc://%s/manager_info' % ipc_dir,
        'profile': 'ipc://%s/manager_profile' % ipc_dir,
        'export': 'ipc://%s/manager_export' % ipc_dir,
        'view': 'ipc://%s/manager_view' % ipc_dir,
    }

    # start the manager process
    proc = mp.Process(
        name='manager',
        target=run_manager,
        args=(1, 1, addrs['results'], addrs['graph'], addrs['comm'],
              addrs['msg'], addrs['info'], addrs['export'], addrs['view'], addrs['profile'],
              None, None)
    )
    proc.daemon = False
    proc.start()

    yield addrs

    # cleanup the manager process
    proc.terminate()
    proc.join(1)
    return proc.exitcode


@pytest.fixture(scope='function')
def manager_ctrl(manager_proc):
    ctx = zmq.Context()
    name = "graph"
    try:
        with ResultsInjector(manager_proc, ctx, 0, name) as inject:
            # wait for the graph subscription to finish setting up
            inject.graph_comm.recv()

            yield inject.comm, inject
    finally:
        # clean up the shared zmq Context
        ctx.destroy()


@pytest.fixture(scope='function')
def manager_export(manager_proc):
    ctx = zmq.Context()
    name = "graph"
    addr = manager_proc['export']
    try:
        with ExportHelper(addr, ctx) as export, ResultsInjector(manager_proc, ctx, 0, name) as inject:
            # wait for the graph subscription to finish setting up
            inject.graph_comm.recv()

            yield export, inject
    finally:
        # clean up the shared zmq Context
        ctx.destroy()


@pytest.fixture(scope='function')
def manager_info(request, manager_proc):
    ctx = zmq.Context()
    name = "graph"
    try:
        with ctx.socket(zmq.SUB) as info, ResultsInjector(manager_proc, ctx, 0, name) as inject:
            info.setsockopt_string(zmq.SUBSCRIBE, request.param)
            info.connect(manager_proc['info'])

            # wait for the graph subscription to finish setting up
            inject.graph_comm.recv()

            yield info, inject
    finally:
        # clean up the shared zmq Context
        ctx.destroy()


@pytest.mark.parametrize('partition', [{'cspad': np.ndarray, 'delta_t': float}, {'laser': bool}, {}])
def test_manager_export_config(manager_export, partition):
    export, injector = manager_export

    # Get the set of expected graph names
    expected_names = {injector.comm.current}

    # commands to run before checking the export output
    cmds = [
        None,
        injector.comm.create,
        functools.partial(injector.partition, partition, wait=True),
        injector.comm.destroy,
    ]
    replies = [
        [
            ('info', '', {'graphs': set()}, 'initial info message'),
        ],
        [
            ('info', '', {'graphs': expected_names}, 'info after create is called'),
            ('store', injector.comm.current, export.store(), 'store after create is called'),
            ('graph', injector.comm.current, export.graph(), 'graph after create is called'),
        ],
        [
            ('info', '', {'graphs': expected_names}, 'info after configure'),
            ('store', injector.comm.current, export.store(), 'store after configure'),
            ('graph', injector.comm.current, export.graph(names=set(partition), sources=partition),
             'graph after configure'),
            ('heartbeat', injector.comm.current, 0, 'hb after configure'),
        ],
        [
            ('graph', injector.comm.current, export.graph(version=1, names=set(partition), sources=partition),
             'graph after destroy is called'),
            ('info', '', {'graphs': set()}, 'info after destroy is called'),
            ('destroy', injector.comm.current, None, 'destroy after destroy is called'),
        ],
    ]

    for cmd, reply in zip(cmds, replies):
        if callable(cmd):
            cmd()
        for exp_topic, exp_graph, exp_data, test_name in reply:
            # Wait for a message on the export socket
            topic, graph, data = export.recv()
            # check the contents of the message
            assert topic == exp_topic, "checking topic of %s" % test_name
            assert graph == exp_graph, "checking graph of %s" % test_name
            assert data == exp_data, "checking data of %s" % test_name


@pytest.mark.parametrize('exports',
                         [
                            [],
                            ['cspad'],
                            ['delta_t'],
                            ['cspad', 'delta_t'],
                            ['laser'],
                            ['fake'],
                            ['fake', 'laser'],
                         ])
@pytest.mark.parametrize('inputs', [{'cspad': [0, 1, 2, 3], 'delta_t': 10.1}, {'laser': True}, {}])
def test_manager_export_data(manager_export, inputs, exports):
    export, injector = manager_export

    # construct the input data
    input_data = {AutoExport.mangle(k): v for k, v in inputs.items() if k in exports}
    input_data.update(inputs)
    # Get the set of expected graph names
    expected_hb = 1
    expected_names = {injector.comm.current}
    expected_features = {
        'version': injector.version,
        'features': {k: Store.get_type(v) for k, v in input_data.items()},
    }
    expected_data = {k: v for k, v in inputs.items() if k in exports}

    # commands to run before checking the export output
    commands = [
        [],
        [injector.comm.create],
    ]
    replies = [
        [
            ('info', '', {'graphs': set()}, 'initial info message'),
        ],
        [
            ('info', '', {'graphs': expected_names}, 'info after create is called'),
            ('store', injector.comm.current, export.store(), 'store after create is called'),
            ('graph', injector.comm.current, export.graph(), 'graph after create is called'),
        ],
    ]

    # deal with the initial flood of export message at startup/graph creation
    for cmds, reply in zip(commands, replies):
        for cmd in cmds:
            cmd()
        for exp_topic, exp_graph, exp_data, test_name in reply:
            # Wait for a message on the export socket
            topic, graph, data = export.recv()
            # check the contents of the message
            assert topic == exp_topic, "checking topic of %s" % test_name
            assert graph == exp_graph, "checking graph of %s" % test_name
            assert data == exp_data, "checking data of %s" % test_name

    # send the names to export to the manager
    injector.comm.export(exports)
    # check that the change is in the received graph object
    if exports:
        assert injector.wait_graph(timeout=1.0)
        # check the graph message
        topic, graph, data = export.recv()
        assert topic == 'graph'
        assert graph == injector.comm.current
        for name in exports:
            assert AutoExport.mangle(name) in data['names']

    # inject some data
    injector.data(expected_hb, input_data, wait=True)

    # check if the inputs dictionary is non-empty
    if inputs:
        # check the updated features list
        topic, graph, data = export.recv()
        assert topic == 'store'
        assert graph == injector.comm.current
        assert data == expected_features

    # check for data if the exports and input names overlap
    if set(exports) & set(inputs):
        # check the data message
        topic, graph, data = export.recv()
        assert topic == 'data'
        assert graph == injector.comm.current
        assert data == expected_data

    # check the heartbeat message
    topic, graph, data = export.recv()
    assert topic == 'heartbeat'
    assert graph == injector.comm.current
    assert data == expected_hb


@pytest.mark.parametrize('partition', [{'cspad': at.Array2d, 'delta_t': float}, {'laser': bool}, {}])
def test_manager_partition(manager_ctrl, partition):
    comm, injector = manager_ctrl

    # test that names and sources are empty
    assert not comm.sources
    assert not comm.names
    # test that the exports are empty
    assert not comm.exports

    injector.partition(partition, wait=True)

    # check that we have the correct partition data from the manager
    assert comm.sources == partition
    assert comm.names == set(partition)
    # test that the exports are still empty
    assert not comm.exports


@pytest.mark.parametrize('manager_info, partition',
                         [
                            ('', {'cspad': at.Array2d, 'delta_t': float})
                         ],
                         indirect=['manager_info'])
def test_manager_partition_updates(manager_info, partition):
    info, injector = manager_info

    # receive the data from the info socket (sent on sub connect)
    topic = info.recv_string()
    node = info.recv_string()
    payload = dill.loads(info.recv())
    # check that the topic of the message is as expected
    assert topic == 'sources'
    # check that the message came from the manager
    assert node == 'manager'
    # check that the expected partition/source info was empty
    assert not payload

    # inject a partition change into the manager
    injector.partition(partition, wait=True)

    # receive the data from the info socket
    topic = info.recv_string()
    node = info.recv_string()
    payload = dill.loads(info.recv())
    # check that the topic of the message is as expected
    assert topic == 'sources'
    # check that the message came from the manager
    assert node == 'manager'
    # check that the expected partition/source info was attached
    payload = {src: at.loads(typ) for src, typ in payload.items()}
    assert payload == partition


@pytest.mark.parametrize('names',
                         [
                            ["cspad"],
                            ["delta_t"],
                            ["test"],
                            ["cspad", "delta_t"],
                         ])
def test_manager_add_view(manager_ctrl, names):
    comm, injector = manager_ctrl

    # create a fake partition
    partition = {'cspad': np.ndarray, 'delta_t': float}
    injector.partition(partition, wait=True)

    # add a view to the graph
    version = comm.graphVersion
    assert comm.view(names)
    assert comm.graphVersion == version + 1
    for name in names:
        assert comm.auto(name) in comm.names

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    nodes = injector.graphs[comm.current][comm.graphVersion]
    assert len(nodes) == len(names)
    for name, node in zip(names, nodes):
        assert node.name == "%s_view" % comm.auto(name)

    # remove the view from the graph
    version = comm.graphVersion
    assert comm.unview(names)
    assert comm.graphVersion == version + 1
    for name in names:
        assert comm.auto(name) not in comm.names

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    removes = injector.graphs[comm.current][comm.graphVersion]
    for name, remove in zip(names, removes):
        assert remove == "%s_view" % comm.auto(name)


@pytest.mark.parametrize('exports',
                         [
                            (["cspad"], [None]),
                            (["delta_t"], ["t_atled"]),
                            (["test"], [None]),
                            (["cspad", "delta_t"], [None, "t_atled"]),
                         ])
def test_manager_add_export(manager_ctrl, exports):
    names, aliases = exports
    comm, injector = manager_ctrl

    # create a fake partition
    partition = {'cspad': np.ndarray, 'delta_t': float}
    injector.partition(partition, wait=True)

    # add a export to the graph
    version = comm.graphVersion

    assert comm.export(names, aliases=aliases)
    assert comm.graphVersion == version + 1
    for name, alias in zip(names, aliases):
        assert comm.alias(name, alias=alias) in comm.names
        assert (alias or name) in comm.exports

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    nodes = injector.graphs[comm.current][comm.graphVersion]
    assert len(nodes) == len(names)
    for name, alias, node in zip(names, aliases, nodes):
        assert node.name == "%s_export" % comm.alias(name, alias=alias)

    # remove the export from the graph
    version = comm.graphVersion
    assert comm.unexport(names, aliases=aliases)
    assert comm.graphVersion == version + 1
    for name in names:
        assert comm.alias(name, alias=alias) not in comm.names
        assert (alias or name) not in comm.exports

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    removes = injector.graphs[comm.current][comm.graphVersion]
    for name, alias, remove in zip(names, aliases, removes):
        assert remove == "%s_export" % comm.alias(name, alias=alias)


@pytest.mark.parametrize('node_info',
                         [
                            ('addMap',
                             {
                                'name': 'test_map',
                                'inputs': 'inval',
                                'outputs': 'outval',
                                'func': lambda x: float(x),
                             },
                             gn.Map),
                            ('addPickN',
                             {
                                'name': 'test_map',
                                'inputs': 'inval',
                                'outputs': 'outval',
                                'N': 5,
                             },
                             gn.PickN),
                         ])
def test_manager_add_node(manager_ctrl, node_info):
    comm, injector = manager_ctrl
    func, kwargs, expected = node_info

    # insert the node in the graph
    assert hasattr(comm, func)
    assert getattr(comm, func)(**kwargs)

    # check that the node is in the graph
    assert kwargs['inputs'] in comm.graph.names
    assert kwargs['outputs'] in comm.graph.names

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    node = injector.graphs[comm.current][comm.graphVersion]
    # check the type of the node
    assert isinstance(node, expected)
    # check the name of the node
    assert node.name == kwargs['name']
    # check the inputs and outputs of the node
    assert kwargs['inputs'] in node.inputs
    assert kwargs['outputs'] in node.outputs

    # remove the node from the graph
    assert comm.remove(kwargs['name'])

    # check that the node was removed
    assert comm.graph is None

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    names = injector.graphs[comm.current][comm.graphVersion]
    assert kwargs['name'] in names


def test_manager_create(manager_ctrl):
    comm, injector = manager_ctrl

    # make a graph and test that it is there
    view_name = 'test'
    default = comm.current
    alt_name = "%s_alt" % default
    assert comm.create()
    assert default in comm.active

    # add a view to the default graph
    assert comm.view(view_name)
    assert comm.auto(view_name) in comm.names

    # change the graph and check
    assert comm.select(alt_name)
    assert comm.current == alt_name
    assert alt_name in comm.active
    # view added to the other graph should not be here
    assert comm.auto(view_name) not in comm.names

    # switch the graph back now
    assert comm.select(default)
    assert comm.current == default
    assert default in comm.active
    assert comm.auto(view_name) in comm.names


def test_manager_destroy(manager_ctrl):
    comm, injector = manager_ctrl

    view_name = 'test'
    name = comm.current
    assert name not in comm.active

    # make a graph and test that it is there
    assert comm.create()
    assert name in comm.active

    # add a view to the default graph
    assert comm.view(view_name)
    assert comm.auto(view_name) in comm.names
    assert injector.wait_graph(timeout=1.0)
    assert name in injector.graphs

    # destory the graph and check
    assert comm.destroy()
    assert name not in comm.active
    assert injector.wait_graph(timeout=1.0)
    assert name not in injector.graphs


def test_manager_store(manager_ctrl, result_data):
    comm, injector = manager_ctrl

    hb = 1

    # allocate a graph
    assert comm.create()

    # inject data into the manager
    injector.version = comm.graphVersion
    injector.data(hb, result_data, wait=True)

    # test the data returned by features
    assert comm.heartbeat == hb
    assert comm.featuresVersion == injector.version
    features = comm.features
    assert features
    assert set(features) == set(result_data)
    for name, value in result_data.items():
        # check that features has the correct type for each key
        if isinstance(value, np.ndarray):
            assert features[name] == (type(value), value.ndim)
            # check that fetch returns the expected array
            assert np.array_equal(comm.fetch(name), value)
        else:
            assert features[name] == type(value)
            # check that fetch returns the expected value
            assert comm.fetch(name) == value

    # reset the store
    assert comm.reset()

    # check that the features dictionary is empty
    assert comm.heartbeat == hb
    assert comm.featuresVersion == 0
    features = comm.features
    assert not features
    # check that none of the names in the result data are fetchable
    for name in result_data:
        assert comm.fetch(name) is None


def test_manager_clear(manager_ctrl, complex_graph):
    comm, injector = manager_ctrl

    # push the complex graph
    assert comm.update(complex_graph)

    # check that the graph is not None
    assert comm.graph is not None
    # check that the manager published the graph change
    assert injector.wait_graph(timeout=1.0)
    assert injector.graphs[comm.current][comm.graphVersion] is not None

    # clear the graph
    assert comm.clear()
    # check that the graph is None now
    assert comm.graph is None
    # check that the manager published the graph change
    assert injector.wait_graph(timeout=1.0)
    assert injector.graphs[comm.current][comm.graphVersion] is None


def test_manager_badcommand(manager_ctrl):
    comm, injector = manager_ctrl

    # send an unknown command to manager
    comm._header("fake_command")
    assert comm._sock.recv_string() != 'ok'

    # check that a valid command still works
    assert comm.clear()

    # send an incomplete command
    comm._sock.send_string("clear_graph")
    assert comm._sock.recv_string() != 'ok'

    # check that a valid command still works
    assert comm.clear()


def test_manager_graphinfo(manager_ctrl, complex_graph):
    comm, injector = manager_ctrl

    # push the complex graph
    assert comm.update(complex_graph)

    # check that the graph is not None
    assert comm.graph is not None

    # check the names in the graph
    assert comm.names == complex_graph.names


def test_manager_versions(manager_ctrl):
    comm, injector = manager_ctrl

    graph_version = 0
    feature_version = 0

    # check the version readback
    assert comm.graphVersion == graph_version
    assert comm.featuresVersion == feature_version
    assert comm.versions == (graph_version, feature_version)

    # bump the graph version and recheck
    graph_version += 1
    assert comm.clear()
    assert comm.graphVersion == graph_version
    assert comm.featuresVersion == feature_version
    assert comm.versions == (graph_version, feature_version)

    # bump the feature version and recheck
    feature_version = graph_version
    # inject fake data with the new version
    injector.version = feature_version
    injector.data(1, {}, wait=True)
    assert comm.graphVersion == graph_version
    assert comm.featuresVersion == feature_version
    assert comm.versions == (graph_version, feature_version)
