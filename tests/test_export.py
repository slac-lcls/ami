import pytest
import re
import zmq
import dill
import threading
import subprocess
import numpy as np
import multiprocessing as mp
import ami.graph_nodes as gn

from ami.graphkit_wrapper import Graph
try:
    from ami.export import run_export
    from ami.export.nt import CUSTOM_TYPE_WRAPPERS
    from ami.export.client import GraphCommHandler, AsyncGraphCommHandler
    from p4p.client.thread import Context, RemoteError
except ImportError:
    pytest.skip("skipping EPICS PVA tests", allow_module_level=True)


class ExportInjector:
    def __init__(self, export, comm):
        self.ctx = zmq.Context()
        self.export = self.ctx.socket(zmq.XPUB)
        self.export.bind(export)
        self.comm = self.ctx.socket(zmq.REP)
        self.comm.bind(comm)
        self.poller = zmq.Poller()
        self.poller.register(self.comm, zmq.POLLIN)
        self.cache = {}
        self.thread = None
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        if self.thread is not None:
            self.thread.join()
        self.export.close()
        self.comm.close()
        self.ctx.destroy()

    def send(self, topic, name, data):
        self.export.send_string(topic, zmq.SNDMORE)
        self.export.send_string(name, zmq.SNDMORE)
        self.export.send_pyobj(data)
        # cache the data injected into exporter
        if topic in self.cache:
            self.cache[topic][name] = data
        else:
            self.cache[topic] = {name: data}

    def wait(self):
        request = self.export.recv_string()
        return request == "\x01"

    def recv(self, reply=None, timeout=1000, fail=False):
        graph = None
        payload = None
        if self.poller.poll(timeout=timeout):
            cmd = self.comm.recv_string()
            if self.comm.getsockopt(zmq.RCVMORE):
                graph = self.comm.recv_string()
                if self.comm.getsockopt(zmq.RCVMORE):
                    payload = dill.loads(self.comm.recv())
                else:
                    payload = None
            else:
                graph = None
                payload = None
        else:
            raise TimeoutError("timeout waiting for comm data!")

        # send response
        if fail:
            self.comm.send_string('error')
        elif reply is None:
            self.comm.send_string('ok')
        else:
            self.comm.send_string('ok', zmq.SNDMORE)
            self.comm.send_pyobj(reply)

        return cmd, graph, payload

    def recv_thread(self, reply=None, timeout=1000, fail=False):
        try:
            self.result = self.recv(reply, timeout, fail)
        except TimeoutError:
            self.result = None

    def recv_start(self, reply=None, timeout=1000, fail=False):
        self.result = None
        self.thread = threading.Thread(name='injector_recv', target=self.recv_thread, args=(reply, timeout, fail))
        self.thread.daemon = True
        self.thread.start()

    def recv_wait(self, timeout=1.0):
        if self.thread is not None:
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                raise TimeoutError("recv_thread has not terminated!")
            else:
                self.thread = None
        return self.result


@pytest.fixture(scope='function')
def exporter(ipc_dir):
    pvbase = "testing:ami"
    comm = 'ipc://%s/pva_comm' % ipc_dir
    export = 'ipc://%s/pva_export' % ipc_dir

    with ExportInjector(export, comm) as injector:
        # start the manager process
        proc = mp.Process(
            name='export',
            target=run_export,
            args=(pvbase, comm, export, True)
        )
        proc.daemon = False
        proc.start()

        # wait for the export code to connect to the injector
        assert injector.wait()
        injector.send('info', '', {'graphs': ['test']})
        injector.send('store', 'test', {'version': 1, 'features': {'delta_t': float, 'laser': bool}})
        injector.send('graph',
                      'test',
                      {
                        'names': ['delta_t', 'laser', 'sum'],
                        'sources': {'delta_t': float, 'laser': bool},
                        'version': 0,
                        'dill': dill.dumps(Graph('test')),
                      })
        injector.send('data',
                      'test',
                      {
                        'laser': True,
                        'delta_t': 3,
                        'ebeam': 10.1,
                        'vals': ['foo', 'bar', 'baz'],
                        'wave8': np.zeros(20),
                        'cspad': np.zeros((10, 10)),
                      })
        injector.send('heartbeat',
                      'test',
                      5)
        yield pvbase, injector

        # cleanup the manager process
        proc.terminate()
        return proc.exitcode


@pytest.fixture(scope='function')
def pvacomm():
    graph_name = 'test'
    pvbase = "testing:ami"

    with GraphCommHandler(graph_name, pvbase) as comm:
        yield comm


@pytest.fixture(scope='function')
def pvacomm_tmo(request):
    graph_name = 'test'
    pvbase = "testing:ami"

    with GraphCommHandler(graph_name, pvbase, timeout=request.param) as comm:
        yield comm


@pytest.fixture(scope='function')
def pvacomm_async(event_loop):
    graph_name = 'test'
    pvbase = "testing:ami"

    with AsyncGraphCommHandler(graph_name, pvbase) as comm:
        yield comm


@pytest.fixture(scope='function')
def pvacomm_tmo_async(request, event_loop):
    graph_name = 'test'
    pvbase = "testing:ami"

    with AsyncGraphCommHandler(graph_name, pvbase, timeout=request.param) as comm:
        yield comm


@pytest.fixture(scope='function')
def pvactx():
    with Context('pva', nt=CUSTOM_TYPE_WRAPPERS) as ctx:
        yield ctx


def test_active_graphs(exporter, pvactx):
    pvbase, injector = exporter

    # check that there are no active graphs
    try:
        assert pvactx.get("%s:info:graphs" % pvbase) == injector.cache['info']['']['graphs']
    except TimeoutError:
        assert False, "timeout getting %s:info:graphs" % pvbase


def test_data_pvs(exporter, pvactx):
    pvbase, injector = exporter

    # check that there are no active graphs
    try:
        for graph, data in injector.cache['data'].items():
            # test the individual pvs
            for key, expected in data.items():
                value = pvactx.get("%s:ana:%s:data:%s" % (pvbase, graph, key))
                if isinstance(value, np.ndarray):
                    assert np.array_equal(value, expected)
                else:
                    assert value == expected
    except TimeoutError:
        assert False, "timeout getting pvs from exporter"


def test_store_pvs(exporter, pvactx):
    pvbase, injector = exporter

    try:
        for graph, data in injector.cache['store'].items():
            # test the aggregated pv
            assert pvactx.get("%s:ana:%s:store" % (pvbase, graph)) == data
            # test the individual pvs
            for key, value in data.items():
                assert pvactx.get("%s:ana:%s:store:%s" % (pvbase, graph, key)) == value
    except TimeoutError:
        assert False, "timeout getting pvs from exporter"


def test_graph_pvs(exporter, pvactx):
    pvbase, injector = exporter

    try:
        for graph, data in injector.cache['graph'].items():
            # test the aggregated pv
            assert pvactx.get("%s:ana:%s" % (pvbase, graph)) == data
            # test the individual pvs
            for key, value in data.items():
                assert pvactx.get("%s:ana:%s:%s" % (pvbase, graph, key)) == value
    except TimeoutError:
        assert False, "timeout getting pvs from exporter"


def test_heartbeat_pvs(exporter, pvactx):
    pvbase, injector = exporter

    try:
        for graph, data in injector.cache['heartbeat'].items():
            assert pvactx.get("%s:ana:%s:heartbeat" % (pvbase, graph)) == data
    except TimeoutError:
        assert False, "timeout getting pvs from exporter"


def test_delete_graph(exporter, pvactx):
    pvbase, injector = exporter

    graph_name = 'test'

    try:
        # test that the graph is there
        assert pvactx.get("%s:ana:%s" % (pvbase, graph_name)) is not None
    except TimeoutError:
        assert False, "timeout getting pvs from exporter"

    # inject the delete message
    injector.send('destroy', graph_name, None)

    try:
        retries = 10
        while retries:
            pvactx.get("%s:ana:%s" % (pvbase, graph_name), timeout=0.25)
            retries -= 1
        assert False, "graph pvs deletion failed"
    except TimeoutError:
        assert True, "graph pvs deleted"
    except RemoteError as err:
        assert str(err) == 'Disconnect'


@pytest.mark.parametrize('command',
                         [
                            ('create', 'create_graph'),
                            ('clear', 'clear_graph'),
                            ('reset', 'reset_features'),
                         ])
def test_graph_cmd(exporter, pvactx, command):
    pvbase, injector = exporter
    cmd, expected = command

    graph_name = 'test'

    # use pvcall to create a new graph
    proc = subprocess.Popen(['pvcall', '%s:cmd:%s' % (pvbase, cmd), 'graph=%s' % graph_name],
                            stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    # check that the exporter returned the expected zmq messages
    try:
        cmd, gname, payload = injector.recv()
    except TimeoutError:
        assert False, "timeout waiting for reponse from exporter"
    assert cmd == expected
    assert gname == graph_name
    assert payload is None

    # check the output of pvcall
    out, err = proc.communicate()
    # check the output
    assert not err
    assert re.split(r'\s+', out.decode())[2] == 'true'
    assert proc.returncode == 0


def test_graph_view(exporter, pvactx):
    pvbase, injector = exporter

    graph_name = 'test'
    view_name = 'cspad'

    # use pvcall to create a new graph
    proc = subprocess.Popen(['pvcall', '%s:cmd:view' % pvbase, 'graph=%s' % graph_name, 'name=%s' % view_name],
                            stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    # check that the exporter returned the expected zmq messages
    try:
        # see the node add
        cmd, gname, payload = injector.recv()
        assert cmd == 'add_graph'
        assert gname == graph_name
        # check the contents for the graph payload
        assert type(payload) == list
        assert len(payload) == 1
        assert type(payload[0]) == gn.PickN
        assert payload[0].N == 1
    except TimeoutError:
        assert False, "timeout waiting for reponse from exporter"

    # check the output of pvcall
    out, err = proc.communicate()
    # check the output
    assert not err
    assert re.split(r'\s+', out.decode())[2] == 'true'
    assert proc.returncode == 0


def test_comm_active_graphs(exporter, pvacomm):
    comm = pvacomm
    injector = exporter[1]

    assert comm.active == injector.cache['info']['']['graphs']


@pytest.mark.asyncio
async def test_comm_active_graphs_async(exporter, pvacomm_async):
    comm = pvacomm_async
    injector = exporter[1]

    assert await comm.active == injector.cache['info']['']['graphs']


def test_comm_select_graph(exporter, pvacomm):
    comm = pvacomm
    injector = exporter[1]

    new_graph_name = 'new_test_graph'

    # check that the current is one of the active ones
    assert comm.current in injector.cache['info']['']['graphs']

    # prep the injector to respond to the request
    injector.recv_start()
    # switch to the new graph and check result
    assert comm.select(new_graph_name)
    assert comm.current == new_graph_name
    # check request the injector received
    assert injector.recv_wait() == ('create_graph', new_graph_name, None)

    # prep the injector to respond to the request (want the change to fail)
    injector.recv_start(fail=True)
    # switch to the new graph and check result
    assert not comm.select(new_graph_name)
    assert comm.current == new_graph_name
    # check request the injector received
    assert injector.recv_wait() == ('create_graph', new_graph_name, None)


@pytest.mark.asyncio
async def test_comm_select_graph_async(exporter, pvacomm_async):
    comm = pvacomm_async
    injector = exporter[1]

    new_graph_name = 'new_test_graph'

    # check that the current is one of the active ones
    assert await comm.current in injector.cache['info']['']['graphs']

    # prep the injector to respond to the request
    injector.recv_start()
    # switch to the new graph and check result
    assert await comm.select(new_graph_name)
    assert await comm.current == new_graph_name
    # check request the injector received
    assert injector.recv_wait() == ('create_graph', new_graph_name, None)

    # prep the injector to respond to the request (want the change to fail)
    injector.recv_start(fail=True)
    # switch to the new graph and check result
    assert not await comm.select(new_graph_name)
    assert await comm.current == new_graph_name
    # check request the injector received
    assert injector.recv_wait() == ('create_graph', new_graph_name, None)


@pytest.mark.parametrize('command, expected',
                         [
                            ('create',  'create_graph'),
                            ('destroy', 'destroy_graph'),
                            ('clear',   'clear_graph'),
                            ('reset',   'reset_features'),
                         ])
def test_comm_graph_command(exporter, pvacomm, command, expected):
    comm = pvacomm
    injector = exporter[1]

    graph_name = comm.current

    # prep the injector to respond to the request
    injector.recv_start()
    # send the graph create command
    assert getattr(comm, command)()
    # check request the injector received
    assert injector.recv_wait() == (expected, graph_name, None)

    # prep the injector to respond to the request
    injector.recv_start(fail=True)
    # send the graph create command
    assert not getattr(comm, command)()
    # check request the injector received
    assert injector.recv_wait() == (expected, graph_name, None)


@pytest.mark.asyncio
@pytest.mark.parametrize('command, expected',
                         [
                            ('create',  'create_graph'),
                            ('destroy', 'destroy_graph'),
                            ('clear',   'clear_graph'),
                            ('reset',   'reset_features'),
                         ])
async def test_comm_graph_command_async(exporter, pvacomm_async, command, expected):
    comm = pvacomm_async
    injector = exporter[1]

    graph_name = await comm.current

    # prep the injector to respond to the request
    injector.recv_start()
    # send the graph create command
    assert await getattr(comm, command)()
    # check request the injector received
    assert injector.recv_wait() == (expected, graph_name, None)

    # prep the injector to respond to the request
    injector.recv_start(fail=True)
    # send the graph create command
    assert not await getattr(comm, command)()
    # check request the injector received
    assert injector.recv_wait() == (expected, graph_name, None)


@pytest.mark.parametrize('views', ['delta_t', ['delta_t'], ['delta_t', 'laser']])
def test_comm_graph_view(exporter, pvacomm, views):
    comm = pvacomm
    injector = exporter[1]

    graph_name = comm.current

    # prep the injector to respond to the request
    injector.recv_start()
    # send the view command
    assert comm.view(views)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, list)
    assert all(isinstance(node, gn.PickN) for node in payload)
    if isinstance(views, list):
        assert len(payload) == len(views)
        for node, view in zip(payload, views):
            assert node.name == comm.auto(view) + '_view'
    else:
        assert len(payload) == 1
        assert payload[0].name == comm.auto(views) + '_view'


def test_comm_graph_add(exporter, pvacomm):
    comm = pvacomm
    injector = exporter[1]

    graph_name = comm.current

    # prep the injector to respond to the request
    injector.recv_start()
    # add a map to the graph
    assert comm.addMap('test_map', inputs=['foo'], outputs=['bar'], func=lambda x: x*2)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, gn.Map)
    assert payload.name == 'test_map'

    # prep the injector to respond to the request - have it return a failure
    injector.recv_start(fail=True)
    # add a map to the graph
    assert not comm.addMap('test_map2', inputs=['foo'], outputs=['bar'], func=lambda x: x*3)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, gn.Map)
    assert payload.name == 'test_map2'

    # prep the injector to respond to the request
    injector.recv_start()
    # add multiple maps to the graph
    nodes = [
        gn.Map(name='test_mapA', inputs=['foo'], outputs=['bar'], func=lambda x: x),
        gn.Map(name='test_mapB', inputs=['foo'], outputs=['bar'], func=lambda x: x*2),
    ]
    assert comm.add(nodes)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, list)
    assert all(isinstance(node, gn.Map) for node in payload)


@pytest.mark.asyncio
async def test_comm_graph_add_async(exporter, pvacomm_async):
    comm = pvacomm_async
    injector = exporter[1]

    graph_name = await comm.current

    # prep the injector to respond to the request
    injector.recv_start()
    # add a map to the graph
    assert await comm.addMap('test_map', inputs=['foo'], outputs=['bar'], func=lambda x: x*2)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, gn.Map)
    assert payload.name == 'test_map'

    # prep the injector to respond to the request - have it return a failure
    injector.recv_start(fail=True)
    # add a map to the graph
    assert not await comm.addMap('test_map2', inputs=['foo'], outputs=['bar'], func=lambda x: x*3)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, gn.Map)
    assert payload.name == 'test_map2'

    # prep the injector to respond to the request
    injector.recv_start()
    # add multiple maps to the graph
    nodes = [
        gn.Map(name='test_mapA', inputs=['foo'], outputs=['bar'], func=lambda x: x),
        gn.Map(name='test_mapB', inputs=['foo'], outputs=['bar'], func=lambda x: x*2),
    ]
    assert await comm.add(nodes)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, list)
    assert all(isinstance(node, gn.Map) for node in payload)


@pytest.mark.parametrize('nodes', ['test_node', ['test_node', 'another_test_node']])
def test_comm_graph_remove(exporter, pvacomm, nodes):
    comm = pvacomm
    injector = exporter[1]

    graph_name = comm.current

    # generate expected reply
    if isinstance(nodes, str):
        expected_reply = ('del_graph', graph_name, [nodes])
    else:
        expected_reply = ('del_graph', graph_name, nodes)

    # prep the injector to respond to the request
    injector.recv_start()
    # add remove a node from the graph
    assert comm.remove(nodes)
    # check request the injector received
    assert injector.recv_wait() == expected_reply

    # prep the injector to respond to the request but make it fail
    injector.recv_start(fail=True)
    # add remove a node from the graph
    assert not comm.remove(nodes)
    # check request the injector received
    assert injector.recv_wait() == expected_reply


@pytest.mark.asyncio
@pytest.mark.parametrize('nodes', ['test_node', ['test_node', 'another_test_node']])
async def test_comm_graph_remove_async(exporter, pvacomm_async, nodes):
    comm = pvacomm_async
    injector = exporter[1]

    graph_name = await comm.current

    # generate expected reply
    if isinstance(nodes, str):
        expected_reply = ('del_graph', graph_name, [nodes])
    else:
        expected_reply = ('del_graph', graph_name, nodes)

    # prep the injector to respond to the request
    injector.recv_start()
    # add remove a node from the graph
    assert await comm.remove(nodes)
    # check request the injector received
    assert injector.recv_wait() == expected_reply

    # prep the injector to respond to the request but make it fail
    injector.recv_start(fail=True)
    # add remove a node from the graph
    assert not await comm.remove(nodes)
    # check request the injector received
    assert injector.recv_wait() == expected_reply


@pytest.mark.asyncio
@pytest.mark.parametrize('views', ['delta_t', ['delta_t'], ['delta_t', 'laser']])
async def test_comm_graph_view_async(exporter, pvacomm_async, views):
    comm = pvacomm_async
    injector = exporter[1]

    graph_name = await comm.current

    # prep the injector to respond to the request
    injector.recv_start()
    # send the view command
    assert await comm.view(views)
    # check request the injector received
    cmd, name, payload = injector.recv_wait()
    assert cmd == 'add_graph'
    assert name == graph_name
    assert isinstance(payload, list)
    assert all(isinstance(node, gn.PickN) for node in payload)
    if isinstance(views, list):
        assert len(payload) == len(views)
        for node, view in zip(payload, views):
            assert node.name == comm.auto(view) + '_view'
    else:
        assert len(payload) == 1
        assert payload[0].name == comm.auto(views) + '_view'


@pytest.mark.parametrize('pvacomm_tmo', [0.5], indirect=True)
@pytest.mark.parametrize('names',
                         [
                            'laser',
                            'delta_t',
                            'vals',
                            'wave8',
                            'notadet',
                            ['notadet'],
                            ['laser', 'delta_t'],
                            ['notadet1', 'notadet2'],
                            ['notadet', 'laser'],
                         ])
def test_comm_graph_fetch(exporter, pvacomm_tmo, names):
    comm = pvacomm_tmo
    injector = exporter[1]

    graph_name = comm.current

    fetched = comm.fetch(names)
    if isinstance(names, list):
        results = [injector.cache['data'][graph_name].get(name) for name in names]
        if all(res is None for res in results):
            assert fetched is None
        else:
            assert fetched == results
    elif isinstance(fetched, np.ndarray):
        assert np.array_equal(fetched, injector.cache['data'][graph_name].get(names))
    else:
        assert fetched == injector.cache['data'][graph_name].get(names)


@pytest.mark.asyncio
@pytest.mark.parametrize('pvacomm_tmo_async', [0.5], indirect=True)
@pytest.mark.parametrize('names',
                         [
                            'laser',
                            'delta_t',
                            'vals',
                            'wave8',
                            'notadet',
                            ['notadet'],
                            ['laser', 'delta_t'],
                            ['notadet1', 'notadet2'],
                            ['notadet', 'laser'],
                         ])
async def test_comm_graph_fetch_async(exporter, pvacomm_tmo_async, names):
    comm = pvacomm_tmo_async
    injector = exporter[1]

    graph_name = await comm.current

    fetched = await comm.fetch(names)
    if isinstance(names, list):
        results = [injector.cache['data'][graph_name].get(name) for name in names]
        if all(res is None for res in results):
            assert fetched is None
        else:
            assert fetched == results
    elif isinstance(fetched, np.ndarray):
        assert np.array_equal(fetched, injector.cache['data'][graph_name].get(names))
    else:
        assert fetched == injector.cache['data'][graph_name].get(names)


def test_comm_graph_info(exporter, pvacomm):
    comm = pvacomm
    injector = exporter[1]

    graph_name = comm.current

    # check fetching the heartbeat
    assert comm.heartbeat == injector.cache['heartbeat'][graph_name]

    # check that fetching the graph works
    graph = comm.graph
    assert isinstance(graph, Graph)
    assert graph.name == dill.loads(injector.cache['graph'][graph_name]['dill']).name

    # check fetching feature info works
    assert comm.features == injector.cache['store'][graph_name]['features']

    # check fetching names info works
    assert comm.names == injector.cache['graph'][graph_name]['names']

    # check fetching sources info works
    assert comm.sources == injector.cache['graph'][graph_name]['sources']

    # check the graph and store versions
    assert comm.versions == [injector.cache['graph'][graph_name]['version'],
                             injector.cache['store'][graph_name]['version']]

    # check the graph version
    assert comm.graphVersion == injector.cache['graph'][graph_name]['version']

    # check the feature store version
    assert comm.featuresVersion == injector.cache['store'][graph_name]['version']


@pytest.mark.asyncio
async def test_comm_graph_info_async(exporter, pvacomm_async):
    comm = pvacomm_async
    injector = exporter[1]

    graph_name = await comm.current

    # check fetching the heartbeat
    assert await comm.heartbeat == injector.cache['heartbeat'][graph_name]

    # check that fetching the graph works
    graph = await comm.graph
    assert isinstance(graph, Graph)
    assert graph.name == dill.loads(injector.cache['graph'][graph_name]['dill']).name

    # check fetching feature info works
    assert await comm.features == injector.cache['store'][graph_name]['features']

    # check fetching names info works
    assert await comm.names == injector.cache['graph'][graph_name]['names']

    # check fetching sources info works
    assert await comm.sources == injector.cache['graph'][graph_name]['sources']

    # check the graph and store versions
    assert await comm.versions == [injector.cache['graph'][graph_name]['version'],
                                   injector.cache['store'][graph_name]['version']]

    # check the graph version
    assert await comm.graphVersion == injector.cache['graph'][graph_name]['version']

    # check the feature store version
    assert await comm.featuresVersion == injector.cache['store'][graph_name]['version']
