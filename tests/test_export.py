import pytest
import re
import zmq
import dill
import subprocess
import numpy as np
import multiprocessing as mp
import ami.graph_nodes as gn

from p4p.client.thread import Context, RemoteError
from ami.export import run_export
from ami.export.nt import CUSTOM_TYPE_WRAPPERS


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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
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

    def recv(self, reply=None, timeout=1000):
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
        if reply is None:
            self.comm.send_string('ok')
        else:
            self.comm.send_string('ok', zmq.SNDMORE)
            self.comm.send_pyobj(reply)

        return cmd, graph, payload


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
                        'types': {'delta_t': float, 'laser': bool, 'sum': (np.ndarray, 2)},
                        'sources': {'delta_t': float, 'laser': bool},
                        'version': 0,
                        'dill': dill.dumps(None),
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
        yield pvbase, injector

        # cleanup the manager process
        proc.terminate()
        return proc.exitcode


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
        retries = 5
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
        # see response from lookup cmd
        cmd, gname, payload = injector.recv(reply=float)
        assert cmd == 'lookup:%s' % view_name
        assert gname == graph_name
        assert payload is None
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
