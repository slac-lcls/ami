import abc
import zmq
import dill
import logging
from enum import IntEnum

from ami.graph_nodes import Map, PickN
from ami.data import MsgTypes, Message, CollectorMessage, DataTypes, Datagram


logger = logging.getLogger(__name__)


class Colors:
    Worker = "worker"
    LocalCollector = "localCollector"
    GlobalCollector = "globalCollector"


class Ports(IntEnum):
    Comm = 5555
    Graph = 5556
    NodeCollector = 5557
    FinalCollector = 5558
    Results = 5559
    Export = 5560


class Store:
    """
    This class is a key value that for holding Datagrams
    """

    def __init__(self, version=0):
        self.version = version
        self._store = {}

    def create(self, name, datatype=DataTypes.Unset):
        if name in self._store:
            raise ValueError("result named %s already exists in ResultStore" % name)
        else:
            self._store[name] = Datagram(name, datatype)

    def get_dgram(self, name):
        return self._store[name]

    @property
    def namespace(self):
        ns = {}
        for k in self._store.keys():
            ns[k] = self._store[k].data
        return ns

    @property
    def types(self):
        ns = {}
        for k in self._store.keys():
            ns[k] = self._store[k].dtype
        return ns

    def get(self, name):
        return self._store[name].data

    def update(self, updates):
        if updates is not None:
            for k, v in updates.items():
                self.put(k, v)

    def put(self, name, data):
        datatype = DataTypes.get_type(data)
        if datatype is not DataTypes.Unset:
            if name in self._store:
                if datatype == self._store[name].dtype or self._store[name].dtype == DataTypes.Unset:
                    self._store[name].dtype = datatype
                    self._store[name].data = data
                else:
                    raise TypeError("type of new result (%s) differs from existing"
                                    " (%s)" % (datatype, self._store[name].dtype))
            else:
                self._store[name] = Datagram(name, datatype, data)

    def clear(self):
        self._store = {}


class ZmqHandler:
    def __init__(self, addr, ctx=None):
        if ctx is None:
            self.ctx = zmq.Context()
        else:
            self.ctx = ctx
        self.collector = self.ctx.socket(zmq.PUSH)
        self.collector.connect(addr)

    def send(self, msg):
        self.collector.send_pyobj(msg)

    def message(self, mtype, identity, payload):
        msg = Message(mtype, identity, payload)
        self.send(msg)


class ResultStore(Store, ZmqHandler):
    """
    This class is a AMI /graph node that collects results
    from a single process and has the ability to send them
    to another (via zeromq). The sending end point is typically
    a Collector object.
    """

    def __init__(self, addr, ctx=None):
        Store.__init__(self)
        ZmqHandler.__init__(self, addr, ctx)

    def collect(self, identity, heartbeat):
        self.send(CollectorMessage(MsgTypes.Datagram, identity, heartbeat, self.version, self.namespace))


class EventBuilder(ZmqHandler):

    def __init__(self, num_contribs, depth, color, addr, ctx=None):
        super(__class__, self).__init__(addr, ctx)
        self.num_contribs = num_contribs
        self.depth = depth
        self.color = color
        self.latest = 0
        # using a dict because it is random access instead of a sequential list
        self.transitions = {}
        self.pending = {}
        self.contribs = {}
        self.graphs = {}

    def prune(self, prune_key=None):
        if prune_key is None:
            depth = self.depth
        else:
            depth = self.latest - prune_key
        if len(self.pending) > depth:
            for eb_key in sorted(self.pending.keys(), reverse=True)[depth:]:
                logger.debug("Pruned uncompleted heartbeat %d", eb_key)
                del self.pending[eb_key]
                del self.contribs[eb_key]

    def active_graphs(self):
        active = set()
        for store in self.pending.values():
            active.add(store.version)
        return active

    def clear_graphs(self):
        active = self.active_graphs()
        for ver_key in sorted(self.graphs.keys(), reverse=True)[self.depth:]:
            if ver_key not in active:
                logger.debug("Pruned old graph (v%d)", ver_key)
                del self.graphs[ver_key]

    def set_graph(self, ver_key, nwork, ncol, graph):
        self.graphs[ver_key] = dill.loads(graph)
        if self.graphs[ver_key] is not None:
            self.graphs[ver_key].compile(num_workers=nwork, num_local_collectors=ncol)
        self.clear_graphs()

    def complete(self, eb_key, identity):
        if eb_key in self.pending:
            self.send(CollectorMessage(MsgTypes.Datagram,
                                       identity,
                                       eb_key,
                                       self.pending[eb_key].version,
                                       self.pending[eb_key].namespace))
            del self.pending[eb_key]
            del self.contribs[eb_key]
            logger.debug("Completed heartbeat %s", eb_key)

    def update(self, eb_key, eb_id, ver_key, data):
        if eb_key not in self.pending:
            self.pending[eb_key] = Store(version=ver_key)
            self.contribs[eb_key] = 0
        if eb_key > self.latest:
            self.latest = eb_key
        if ver_key != self.pending[eb_key].version:
            logger.error("Graph version mismatch: heartbeat %s from id %s has version %s when %s was expected",
                         eb_key, eb_id, ver_key, self.pending[eb_key].version)
        else:
            graph = self.graphs.get(ver_key)
            if graph is not None:
                self.pending[eb_key].update(graph(data, color=self.color))

    def transition(self, eb_key, eb_id):
        if eb_key not in self.transitions:
            self.transitions[eb_key] = 0
        self.transitions[eb_key] |= (1 << eb_id)

    def heartbeat(self, eb_key, eb_id):
        if eb_key not in self.contribs:
            self.contribs[eb_key] = 0
        self.contribs[eb_key] |= (1 << eb_id)

    def get(self, eb_key, name):
        return self.pending[eb_key].get(name)

    def transition_ready(self, eb_key):
        if eb_key not in self.transitions:
            return False
        return ((1 << self.num_contribs) - 1) == self.transitions[eb_key]

    def heartbeat_ready(self, eb_key):
        if eb_key not in self.contribs:
            return False
        return ((1 << self.num_contribs) - 1) == self.contribs[eb_key]


class Collector(abc.ABC):
    """
    This class gathers (via zeromq) results from many
    ResultsStores. But rather than use gather, it employs
    an async send/recieve pattern.
    """

    def __init__(self, addr, ctx=None):
        if ctx is None:
            self.ctx = zmq.Context()
        else:
            self.ctx = ctx
        self.poller = zmq.Poller()
        self.collector = self.ctx.socket(zmq.PULL)
        self.collector.bind(addr)
        self.poller.register(self.collector, zmq.POLLIN)
        self.handlers = {}
        return

    def register(self, sock, handler):
        self.handlers[sock] = handler
        self.poller.register(sock, zmq.POLLIN)

    def unregister(self, sock):
        if sock in self.handlers:
            del self.handlers[sock]
            self.poller.unregister(sock)

    def recv(self):
        return self.collector.recv_pyobj()

    @abc.abstractmethod
    def process_msg(self, msg):
        return

    def run(self):
        while True:
            for sock, flag in self.poller.poll():
                if flag != zmq.POLLIN:
                    continue
                if sock is self.collector:
                    msg = self.recv()
                    self.process_msg(msg)
                elif sock in self.handlers:
                    self.handlers[sock]()


class GraphReceiver:

    def __init__(self, addr):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sock.connect(addr)
        self.handlers = {"cmd": self.command}
        self.commands = {}
        self.special = set(self.handlers.keys())

    def command(self):
        name = self.sock.recv_string()
        if name in self.commands:
            self.commands[name]()

    def add_handler(self, topic, handler):
        if topic not in self.special:
            self.handlers[topic] = handler
        else:
            raise ValueError("handler for topic %s cannot be modified" % topic)

    def add_command(self, name, handler):
        self.commands[name] = handler

    def recv(self, block=True):
        if block:
            topic = self.sock.recv_string()
        else:
            topic = self.sock.recv_string(flags=zmq.NOBLOCK)
        # check if the topic is a special one
        if topic in self.special:
            self.handlers[topic]()
        else:
            num_work, num_col, version = self.sock.recv_pyobj()
            payload = self.sock.recv()
            if topic in self.handlers:
                self.handlers[topic](num_work, num_col, version, payload)


class CommHandler(abc.ABC):

    def __init__(self, addr, async_mode=False):
        if async_mode:
            self._ctx = zmq.asyncio.Context()
        else:
            self._ctx = zmq.Context()
        self._addr = addr
        self._sock = self._ctx.socket(zmq.REQ)
        self._sock.connect(self._addr)
        self._expand_keys = ['inputs', 'outputs']

    def _make_node(self, node, **kwargs):
        for key in self._expand_keys:
            if key in kwargs and not isinstance(kwargs[key], list):
                kwargs[key] = [kwargs[key]]
        return node(**kwargs)

    def auto(self, name):
        return '_auto_%s' % name

    @property
    def graph(self):
        return self._request_dill('get_graph')

    @property
    def features(self):
        return self._request('get_features')

    @property
    def names(self):
        return self._request('get_names')

    @property
    def versions(self):
        return self._request('get_versions')

    @property
    def graphVersion(self):
        return self._request('get_graph_version')

    @property
    def featuresVersion(self):
        return self._request('get_features_version')

    def fetch(self, name):
        return self._request("fetch:%s" % name, check=True)

    def edit(self, cmd, node):
        return self._post_dill('%s_graph' % cmd, node)

    def view(self, name):
        view_name = self.auto(name)
        return self.pickN('%s_view' % view_name, name, view_name)

    def pickN(self, name, inputs, outputs, N=1):
        node = self._make_node(PickN, name=name, inputs=inputs, outputs=outputs, N=N)
        return self.edit("add", node)

    def map(self, name, inputs, outputs, func):
        node = self._make_node(Map, name=name, inputs=inputs, outputs=outputs, func=func)
        return self.edit("add", node)

    def remove(self, name):
        return self.edit("del", name)

    def clear(self):
        return self._command('clear_graph')

    def reset(self):
        return self._command('reset_features')

    def update(self, graph):
        return self._post_dill('set_graph', graph)

    def save(self, filename):
        if filename:
            try:
                return self._save(filename)
            except OSError:
                logger.exception("Problem opening saved graph configuration file:")

    def load(self, filename):
        if filename:
            try:
                return self._load(filename)
            except OSError:
                    logger.exception("Problem opening saved graph configuration file:")
            except dill.UnpicklingError:
                    logger.exception("Problem parsing saved graph configuration file (%s):", filename)

    @abc.abstractmethod
    def _command(self, cmd):
        pass

    @abc.abstractmethod
    def _request(self, cmd, check=False):
        pass

    @abc.abstractmethod
    def _request_dill(self, cmd):
        pass

    @abc.abstractmethod
    def _post_dill(self, cmd, payload):
        pass

    @abc.abstractmethod
    def _load(self, graph):
        pass

    @abc.abstractmethod
    def _save(self, graph):
        pass


class AsyncGraphCommHandler(CommHandler):

    def __init__(self, addr):
        super(__class__, self).__init__(addr, True)

    async def _command(self, cmd):
        await self._sock.send_string(cmd)
        return (await self._sock.recv_string()) == 'ok'

    async def _request(self, cmd, check=False):
        await self._sock.send_string(cmd)
        if check:
            reply = await self._sock.recv_string()
            if reply == 'ok':
                return await self._sock.recv_pyobj()
        else:
            return await self._sock.recv_pyobj()

    async def _request_dill(self, cmd):
        await self._sock.send_string(cmd)
        return dill.loads(await self._sock.recv())

    async def _post_dill(self, cmd, payload):
        await self._sock.send_string(cmd, zmq.SNDMORE)
        await self._sock.send(dill.dumps(payload))
        return (await self._sock.recv_string()) == 'ok'

    async def save(self, filename):
        if filename:
            try:
                with open(filename, 'wb') as cnf:
                    dill.dump(await self.graph, cnf)
            except OSError:
                logger.exception("Problem opening saved graph configuration file:")

    async def _load(self, filename):
        with open(filename, 'rb') as cnf:
            graph = dill.load(cnf)
        return await self.update(graph)

    async def _save(self, filename):
        graph = await self.graph
        with open(filename, 'wb') as cnf:
            return dill.dump(graph, cnf)


class GraphCommHandler(CommHandler):

    def __init__(self, addr):
        super(__class__, self).__init__(addr, False)

    def _command(self, cmd):
        self._sock.send_string(cmd)
        return self._sock.recv_string() == 'ok'

    def _request(self, cmd, check=False):
        self._sock.send_string(cmd)
        if check:
            reply = self._sock.recv_string()
            if reply == 'ok':
                return self._sock.recv_pyobj()
        else:
            return self._sock.recv_pyobj()

    def _request_dill(self, cmd):
        self._sock.send_string(cmd)
        return dill.loads(self._sock.recv())

    def _post_dill(self, cmd, payload):
        self._sock.send_string(cmd, zmq.SNDMORE)
        self._sock.send(dill.dumps(payload))
        return self._sock.recv_string() == 'ok'

    def _load(self, filename):
        with open(filename, 'rb') as cnf:
            self.update(dill.load(cnf))

    def _save(self, filename):
        with open(filename, 'wb') as cnf:
            dill.dump(self.graph, cnf)
