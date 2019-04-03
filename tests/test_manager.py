import pytest
import zmq
import time
import dill
import numpy as np
import multiprocessing as mp

from ami.data import MsgTypes, Transitions, Transition
from ami.comm import Node, ZmqHandler, GraphCommHandler
from ami.manager import run_manager


class ResultsInjector(Node, ZmqHandler):
    def __init__(self, addrs, ctx, identity, name, version=0):
        Node.__init__(self, identity, addrs['graph'], addrs['msg'], ctx=ctx)
        ZmqHandler.__init__(self, addrs['results'], ctx=ctx)
        self.comm = GraphCommHandler(name, addrs['comm'], ctx=ctx)
        self._name = name
        self.version = version

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

    def recv_graph(self, name, version, payload):
        if name not in self.graphs:
            self.graphs[name] = {}
        self.graphs[name][version] = payload

    def mark(self):
        count = self.wait_counter + 1
        self.collector_message(self.node, count, self.name, self.version, {})
        return count

    def partition(self, payload, wait=False):
        self.message(MsgTypes.Transition, self.node, Transition(Transitions.Configure, payload))
        if wait:
            self.wait_for(self.mark())
        else:
            return self.mark

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
def manager_proc(ipc_dir):
    addrs = {
        'results': 'ipc://%s/manager_results' % ipc_dir,
        'comm': 'ipc://%s/manager_comm' % ipc_dir,
        'graph': 'ipc://%s/manager_graph' % ipc_dir,
        'msg': 'ipc://%s/manager_msg' % ipc_dir,
        'info': 'ipc://%s/manager_info' % ipc_dir,
    }

    # start the manager process
    proc = mp.Process(
        name='manager',
        target=run_manager,
        args=(1, 1, addrs['results'], addrs['graph'], addrs['comm'], addrs['msg'], addrs['info'])
    )
    proc.daemon = False
    proc.start()

    yield addrs

    # cleanup the manager process
    proc.terminate()
    return proc.exitcode


@pytest.fixture(scope='function')
def manager_ctrl(manager_proc):
    ctx = zmq.Context()
    name = "graph"
    addr = manager_proc['comm']
    try:
        with GraphCommHandler(name, addr, ctx=ctx) as comm, ResultsInjector(manager_proc, ctx, 0, name) as inject:
            # wait for the graph subscription to finish setting up
            inject.graph_comm.recv()

            yield comm, inject
    finally:
        # clean up the shared zmq Context
        ctx.destroy()


@pytest.fixture(scope='function')
def manager_config(request, manager_proc):
    ctx = zmq.Context()
    name = "graph"
    addr = manager_proc['comm']
    partition = request.param['partition']
    try:
        with GraphCommHandler(name, addr, ctx=ctx) as comm, ResultsInjector(manager_proc, ctx, 0, name) as inject:
            inject.partition(partition, wait=True)
            # wait for the graph subscription to finish setting up
            inject.graph_comm.recv()

            yield comm, inject, request.param
    finally:
        # clean up the shared zmq Context
        ctx.destroy()


@pytest.mark.parametrize('partition', [{'cspad': np.ndarray, 'delta_t': float}, {'laser': True}, {}])
def test_manager_partition(manager_ctrl, partition):
    comm, injector = manager_ctrl

    # test that names and sources are empty
    assert not comm.sources
    assert not comm.names

    injector.partition(partition, wait=True)

    # check that we have the correct partition data from the manager
    assert comm.sources == partition
    assert comm.names == set(partition)


@pytest.mark.parametrize('name', ["cspad", "delta_t", "test"])
def test_manager_add_view(manager_ctrl, name):
    comm, injector = manager_ctrl

    # create a fake partition
    partition = {'cspad': np.ndarray, 'delta_t': float}
    injector.partition(partition, wait=True)

    # add a view to the graph
    version = comm.graphVersion
    assert comm.view(name)
    assert comm.graphVersion == version + 1
    assert comm.auto(name) in comm.names

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    graph = dill.loads(injector.graphs[comm.current][comm.graphVersion])
    assert comm.auto(name) in graph.names

    # remove the view from the graph
    version = comm.graphVersion
    assert comm.unview(name)
    assert comm.graphVersion == version + 1
    assert comm.auto(name) not in comm.names

    # check that the change is in the received graph object
    assert injector.wait_graph(timeout=1.0)
    graph = dill.loads(injector.graphs[comm.current][comm.graphVersion])
    assert graph is None


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
