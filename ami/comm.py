import abc
import zmq
import dill
from enum import IntEnum

from ami.data import MsgTypes, Message, CollectorMessage, DataTypes, Datagram


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

    def __init__(self):
        self._updated = {}
        self._store = {}

    def create(self, name, datatype=DataTypes.Unset):
        if name in self._store:
            raise ValueError("result named %s already exists in ResultStore" % name)
        else:
            self._store[name] = Datagram(name, datatype)
            self._updated[name] = False

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
        if name in self._store:
            if datatype == self._store[name].dtype or self._store[name].dtype == DataTypes.Unset:
                self._store[name].dtype = datatype
                self._store[name].data = data
            else:
                raise TypeError("type of new result (%s) differs from existing"
                                " (%s)" % (datatype, self._store[name].dtype))
        else:
            self._store[name] = Datagram(name, datatype, data)

        self._updated[name] = True

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

    def ready_items(self, clear=False):
        for name, result in self._store.items():
            if self._updated[name]:
                if clear:
                    self._updated[name] = False
                yield name, result

    def is_ready(self, name):
        if name in self._store.keys():
            return self._updated[name]
        else:
            return False


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
        self.send(CollectorMessage(MsgTypes.Datagram, identity, heartbeat, self.namespace))


class PickNBuilder(ZmqHandler):
    def __init__(self, num_contribs, addr, ctx=None):
        super(__class__, self).__init__(addr, ctx)
        self.num_contribs = num_contribs
        self.count = 0
        self.dgram = None

    def put(self, dgram):
        if self.dgram is None:
            self.dgram = dgram
        else:
            self.dgram.data += dgram.data
        self.count += 1
        if self.count == self.num_contribs:
            self.send(Message(MsgTypes.Datagram, 0, self.dgram))
            self.count = 0


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

    def set_graph(self, eb_key, nwork, ncol, graph):
        self.graphs[eb_key] = dill.loads(graph)
        if self.graphs[eb_key] is not None:
            self.graphs[eb_key].compile(num_workers=nwork, num_local_collectors=ncol)

    def graph(self, eb_key):
        return self.graphs.get(eb_key)

    def complete(self, identity, eb_key):
        if eb_key in self.pending:
            self.send(CollectorMessage(MsgTypes.Datagram, identity, eb_key, self.pending[eb_key].namespace))
            del self.pending[eb_key]
            del self.contribs[eb_key]
            # print("completed heartbeat", eb_key)

    def update(self, eb_key, eb_id, data):
        if eb_key not in self.pending:
            self.pending[eb_key] = Store()
            self.contribs[eb_key] = 0
        self.latest = eb_key
        graph = self.graph(eb_key)
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
