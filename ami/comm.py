import abc
import zmq
import dill
import logging
from enum import IntEnum

from ami.graphkit_wrapper import Map, PickN
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

    def sum(self, name, data):
        datatype = DataTypes.get_type(data)
        if name in self._store:
            if datatype == self._store[name].dtype or self._store[name].dtype == DataTypes.Unset:
                self._store[name].dtype = datatype
                self._store[name].data += data
            else:
                raise TypeError("type of new result (%s) differs from existing"
                                " (%s)" % (datatype, self._store[name].dtype))
        else:
            self.put(name, data)

    def clear(self):
        self._store = {}


class ZmqHandler(object):
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
        self.latest = None
        # using a dict because it is random access instead of a sequential list
        self.transitions = {}
        self.pending = {}
        self.contribs = {}
        self.graphs = {}

    def set_graph(self, ver_key, nwork, ncol, graph):
        self.graphs[ver_key] = dill.loads(graph)
        if self.graphs[ver_key] is not None:
            self.graphs[ver_key].compile(num_workers=nwork, num_local_collectors=ncol)

    def graph(self, ver_key):
        return self.graphs.get(ver_key)

    def complete(self, identity, eb_key):
        if eb_key in self.pending:
            self.send(CollectorMessage(MsgTypes.Datagram,
                                       identity,
                                       eb_key,
                                       self.pending[eb_key].version,
                                       self.pending[eb_key].namespace))
            del self.pending[eb_key]
            del self.contribs[eb_key]
            logger.debug("completed heartbeat %s", eb_key)

    def update(self, eb_key, eb_id, ver_key, data):
        if eb_key not in self.pending:
            self.pending[eb_key] = Store(version=ver_key)
            self.contribs[eb_key] = 0
        self.latest = eb_key
        if ver_key != self.pending[eb_key].version:
            logger.error("Graph version mismatch: heartbeat %s from id %s has version %s when %s was expected",
                         eb_key, eb_id, ver_key, self.pending[eb_key].version)
        else:
            graph = self.graph(ver_key)
            if graph is not None:
                self.pending[eb_key].update(graph(data, color=self.color))

    def put(self, eb_key, eb_id, name, data):
        if eb_key not in self.pending:
            self.pending[eb_key] = Store()
            self.contribs[eb_key] = 0
        self.latest = eb_key
        self.pending[eb_key].put(name, data)

    def sum(self, eb_key, eb_id, name, data):
        if eb_key not in self.pending:
            self.pending[eb_key] = Store()
            self.contribs[eb_key] = 0
        self.latest = eb_key
        self.pending[eb_key].sum(name, data)

    def transition(self, eb_id, eb_key):
        if eb_key not in self.transitions:
            self.transitions[eb_key] = 0
        self.transitions[eb_key] |= (1 << eb_id)

    def heartbeat(self, eb_id, eb_key):
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


class GraphCommHandler(object):

    def __init__(self, addr):
        self.ctx = zmq.Context()
        self.addr = addr
        self.sock = self.ctx.socket(zmq.REQ)
        self.sock.connect(self.addr)

    @property
    def graph(self):
        self.sock.send_string('get_graph')
        return dill.loads(self.sock.recv())

    @property
    def features(self):
        self.sock.send_string('get_features')
        return self.sock.recv_pyobj()

    @property
    def types(self):
        self.sock.send_string('get_types')
        return self.sock.recv_pyobj()

    def get_feature(self, name):
        self.sock.send_string("feature:%s" % name)
        reply = self.sock.recv_string()
        if reply == 'ok':
            return self.sock.recv_pyobj()

    def edit(self, cmd, node):
        self.sock.send_string('%s_graph' % cmd, zmq.SNDMORE)
        self.sock.send(dill.dumps(node))
        return self.sock.recv_string() == 'ok'

    def pickN(self, name, inputs, outputs, N=1):
        node = PickN(name=name, inputs=inputs, outputs=outputs, N=N)
        return self.edit("add", node)

    def map(self, name, inputs, outputs, func):
        node = Map(name=name, inputs=inputs, outputs=outputs, func=func)
        return self.edit("add", node)

    def remove(self, name):
        return self.edit("del", name)

    def clear(self):
        self.sock.send_string('clear_graph')
        return self.sock.recv_string() == 'ok'

    def reset(self):
        self.sock.send_string('reset_features')
        return self.sock.recv_string() == 'ok'

    def update(self, graph):
        self.sock.send_string('set_graph', zmq.SNDMORE)
        self.sock.send(dill.dumps(graph))
        return self.sock.recv_string() == 'ok'

    def save(self, filename):
        if filename:
            try:
                with open(filename, 'wb') as cnf:
                    dill.dump(self.graph, cnf)
            except OSError as os_exp:
                logger.exception("Problem opening saved graph configuration file:")

    def load(self, filename):
        if filename:
            try:
                with open(filename, 'rb') as cnf:
                    self.update(dill.load(cnf))
            except OSError as os_exp:
                    logger.exception("Problem opening saved graph configuration file:")
            except dill.UnpicklingError as dill_exp:
                    logger.exception("Problem parsing saved graph configuration file (%s):", filename)
