import abc
import zmq
import dill
import asyncio
import logging
from enum import IntEnum

import ami.graph_nodes as gn
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

    def set_graph(self, name, ver_key, graph):
        self.graphs[ver_key] = dill.loads(graph)
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
            name, version = self.sock.recv_pyobj()
            payload = self.sock.recv()
            if topic in self.handlers:
                self.handlers[topic](name, version, payload)


class CommHandler(abc.ABC):
    """Abstract base class for handling communication with the AMI graph manager.

    This abstract class provides an interface for interacting with the graph
    manager. Provides support for implementing both a synchronous as well as
    an asynchronous version.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
        async_mode (bool): if True the asyncio version of zmq is used
    """

    def __init__(self, addr, async_mode=False):
        if async_mode:
            self._ctx = zmq.asyncio.Context()
        else:
            self._ctx = zmq.Context()
        self._addr = addr
        self._sock = self._ctx.socket(zmq.REQ)
        self._sock.connect(self._addr)
        self._prune_keys = ['condition_needs', 'condition', 'reduction']
        self._expand_keys = ['inputs', 'outputs', 'condition_needs']

    def _make_node(self, node, **kwargs):
        """
        Constructs a graph node of the requested type.

        Args:
            node (cls): the class type of the node to create.
            **kwargs: aribitrary keyword args to pass to constructor of the node.

        Returns:
            The constructed graph node.
        """
        for key in self._prune_keys:
            if key in kwargs and kwargs[key] is None:
                del kwargs[key]
        for key in self._expand_keys:
            if key in kwargs:
                if not isinstance(kwargs[key], list):
                    kwargs[key] = [kwargs[key]]
                converted_vars = []
                for var in kwargs[key]:
                    if isinstance(var, gn.Var):
                        converted_vars.append(var)
                    else:
                        converted_vars.append(gn.Var(var))

                kwargs[key] = converted_vars

        return node(**kwargs)

    def auto(self, name):
        """
        Creates an auto generated name from the passed string by appending
        the prefix `_auto_` to the string.

        Args:
            name (str): the string to use for generating an auto name

        Returns:
            The auto generated name
        """
        return '_auto_%s' % name

    @property
    def graph(self):
        """
        Fetches the current graph from the manager.

        Returns:
            An object of type `Graph` representing the current analysis graph.
        """
        return self._request_dill('get_graph')

    @property
    def features(self):
        """
        Information on the features currently available in the global feature
        store.

        Returns:
            A dictionary where the keys are the names of the available features
            and the values are the `DataTypes` of those features.
        """
        return self._request('get_features')

    @property
    def names(self):
        """
        A set of all the user-defined output names in the in the graph that can
        be used as inputs for nodes in the graph.

        Returns:
            A set of all the user-defined output names.
        """
        return self._request('get_names')

    @property
    def versions(self):
        """
        The current graph and feature store versions.

        Returns:
            A tuple of the graph and feature store versions.
        """
        return self._request('get_versions')

    @property
    def graphVersion(self):
        """
        The current graph version.

        Returns:
            The current version of the graph.
        """
        return self._request('get_graph_version')

    @property
    def featuresVersion(self):
        """
        The current feature store version.

        Returns:
            The current version of the feature store.
        """
        return self._request('get_features_version')

    def get_type(self, name):
        """
        Lookups of the type of a `Var` node in the graph by its name field.

        Args:
            name (str): the name of the node

        Returns:
            The type of the node if it is found in the graph
        """
        return self._request("lookup:%s" % name, check=True)

    def fetch(self, name):
        """
        Attempts to fetch a feature with the requested name from the global
        features. If the feature is not present in the store then None is
        returned.

        Args:
            name (str): the name of the feature to fetch.

        Returns:
            The object that is fetched from the global feature store.
        """
        # if the reply is none try fetching the 'view' version of the name
        return self._request("fetch:%s" % name, check=True, retry="fetch:%s" % self.auto(name))

    def add(self, node):
        """
        Attempt to add the requested node (or list of nodes) to the graph.

        Args:
            node (list or node): the node or list of nodes to add to the graph.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._post_dill('add_graph', node)

    def view(self, name):
        """
        Adds a Pick1 graph node for the requested graph output so that is can
        be viewed. The format of output name of the Pick1 node is determined
        by calling the `auto` method of this class.

        Args:
            name (str): The name of the graph output to start viewing.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._view(name)

    def addPickN(self, name, inputs, outputs, N=1, condition_needs=None):
        """
        Adds a PickN graph node to the manager's graph.

        Args:
            name (str): the name of the node
            inputs (list or str): the input(s) to use for the node.
            outputs (list or str): the output(s) made by the node.
            N (int): the number to pick for the PickN.
            condition_needs (list or str): the names of any conditions
                that the node depends on.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        node = self._make_node(gn.PickN, name=name, inputs=inputs, outputs=outputs, N=N,
                               condition_needs=condition_needs)
        return self.add(node)

    def addMap(self, name, inputs, outputs, func, condition_needs=None):
        """
        Adds a Map graph node to the manager's graph.

        Args:
            name (str): the name of the node
            inputs (list or str): the input(s) to use for the node.
            outputs (list or str): the output(s) made by the node.
            func (function): the function to use for the map.
            condition_needs (list or str): the names of any conditions
                that the node depends on.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        node = self._make_node(gn.Map, name=name, inputs=inputs, outputs=outputs, func=func,
                               condition_needs=condition_needs)
        return self.add(node)

    def addReduce(self, name, inputs, outputs, reduction=None, condition_needs=None):
        """
        Adds a ReduceByKey graph node to the manager's graph.

        Args:
            name (str): the name of the node
            inputs (list or str): the input(s) to use for the node.
            outputs (list or str): the output(s) made by the node.
            reduction (function): the function to use for the reduction.
            condition_needs (list or str): the names of any conditions
                that the node depends on.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        node = self._make_node(gn.ReduceByKey, name=name, inputs=inputs, outputs=outputs,
                               reduction=reduction, condition_needs=condition_needs)
        return self.add(node)

    def addBinning(self, name, inputs, outputs, condition_needs=None):
        """
        Adds a Binning graph node to the manager's graph.

        Args:
            name (str): the name of the node
            inputs (list or str): the input(s) to use for the node.
            outputs (list or str): the output(s) made by the node.
            condition_needs (list or str): the names of any conditions
                that the node depends on.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        node = self._make_node(gn.Binning, name=name, inputs=inputs, outputs=outputs,
                               condition_needs=condition_needs)
        return self.add(node)

    def addFilterOn(self, name, condition_needs, outputs, condition=None):
        """
        Adds a FilterOn graph node to the manager's graph.

        Args:
            name (str): the name of the node
            condition_needs (list or str): the inputs needed for the evaluating
                the filter condition.
            outputs (list or str): the output(s) made by the node.
            condition (function): the condition evaluation function to use.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        node = self._make_node(gn.FilterOn, name=name, condition_needs=condition_needs, outputs=outputs,
                               condition=condition)
        return self.add(node)

    def addFilterOff(self, name, condition_needs, outputs, condition=None):
        """
        Adds a FilterOff graph node to the manager's graph.

        Args:
            name (str): the name of the node
            condition_needs (list or str): the inputs needed for the evaluating
                the filter condition.
            outputs (list or str): the output(s) made by the node.
            condition (function): the condition evaluation function to use.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        node = self._make_node(gn.FilterOff, name=name, condition_needs=condition_needs, outputs=outputs,
                               condition=condition)
        return self.add(node)

    def remove(self, name):
        """
        Removes the node (if it exists) with the requested name from the graph.

        Args:
            name (str): The name of the node to remove from the graph

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._post_dill('del_graph', name)

    def clear(self):
        """
        Clears the manager's current graph.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._command('clear_graph')

    def reset(self):
        """
        Clears all the data currently in the manager's feature store.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._command('reset_features')

    def update(self, graph):
        """
        Replaces the manager's current graph with the requested graph.

        Args:
            graph (Graph): The new graph for the manager to use.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._post_dill('set_graph', graph)

    def save(self, filename):
        """
        Saves the manager's current graph to a file.

        Args:
            filename (str): the name of the file for saving the graph.
        """
        if filename:
            try:
                return self._save(filename)
            except OSError:
                logger.exception("Problem opening saved graph configuration file:")

    def load(self, filename):
        """
        Loads a graph from a file and replaces the manager's graph with it.

        Args:
            filename (str): the name of the file to load.

        Returns:
            True if the graph update was successful, False otherwise.
        """
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
    def _view(self, name):
        pass

    @abc.abstractmethod
    def _load(self, graph):
        pass

    @abc.abstractmethod
    def _save(self, graph):
        pass


class AsyncGraphCommHandler(CommHandler):
    """An asynchronous interface for handling communication with the AMI graph manager.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
    """

    def __init__(self, addr):
        super(__class__, self).__init__(addr, True)
        self.lock = asyncio.Lock()

    async def _command(self, cmd):
        async with self.lock:
            await self._sock.send_string(cmd)
            return (await self._sock.recv_string()) == 'ok'

    async def _request(self, cmd, check=False, retry=None):
        async with self.lock:
            await self._sock.send_string(cmd)
            if check:
                reply = await self._sock.recv_string()
                if reply == 'ok':
                    return await self._sock.recv_pyobj()
                elif retry is not None:
                    await self._sock.send_string(retry)
                    reply = await self._sock.recv_string()
                    if reply == 'ok':
                        return await self._sock.recv_pyobj()
            else:
                return await self._sock.recv_pyobj()

    async def _request_dill(self, cmd):
        async with self.lock:
            await self._sock.send_string(cmd)
            return dill.loads(await self._sock.recv())

    async def _post_dill(self, cmd, payload):
        async with self.lock:
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

    async def _view(self, name):
        view_name = self.auto(name)
        var_type = await self.get_type(name)
        if var_type is None:
            return await self.addPickN('%s_view' % view_name, name, view_name)
        else:
            return await self.addPickN('%s_view' % view_name, gn.Var(name, var_type), gn.Var(view_name, var_type))

    async def _load(self, filename):
        with open(filename, 'rb') as cnf:
            graph = dill.load(cnf)
        return await self.update(graph)

    async def _save(self, filename):
        graph = await self.graph
        with open(filename, 'wb') as cnf:
            return dill.dump(graph, cnf)


class GraphCommHandler(CommHandler):
    """A synchronous interface for handling communication with the AMI graph manager.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
    """

    def __init__(self, addr):
        super(__class__, self).__init__(addr, False)

    def _command(self, cmd):
        self._sock.send_string(cmd)
        return self._sock.recv_string() == 'ok'

    def _request(self, cmd, check=False, retry=None):
        self._sock.send_string(cmd)
        if check:
            reply = self._sock.recv_string()
            if reply == 'ok':
                return self._sock.recv_pyobj()
            elif retry is not None:
                self._sock.send_string(retry)
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

    def _view(self, name):
        view_name = self.auto(name)
        var_type = self.get_type(name)
        if var_type is None:
            return self.addPickN('%s_view' % view_name, name, view_name)
        else:
            return self.addPickN('%s_view' % view_name, gn.Var(name, var_type), gn.Var(view_name, var_type))

    def _load(self, filename):
        with open(filename, 'rb') as cnf:
            self.update(dill.load(cnf))

    def _save(self, filename):
        with open(filename, 'wb') as cnf:
            dill.dump(self.graph, cnf)
