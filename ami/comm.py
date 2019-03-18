import abc
import zmq
import dill
import asyncio
import logging
import numpy as np
import zmq.asyncio
from enum import IntEnum

import ami.graph_nodes as gn
from ami.data import MsgTypes, Message, CollectorMessage, Datagram


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
    Message = 5561
    Info = 5562


class Store:
    """Class for holding data as key value pairs.

    The data is store internally as Datagram objects. When new data is inserted
    for a key its type is checked to see if it matches the type of previous
    value (if any).

    Args:
        version (int): The current version id of the store. Defaults to zero.
    """

    def __init__(self, version=0):
        self.version = version
        self._store = {}

    def __bool__(self):
        """
        Returns the truth value of the store class.

        Returns:
            False if the store is empty and True otherwise.
        """
        if self._store:
            return True
        else:
            return False

    @staticmethod
    def get_type(data):
        """
        Static method for returning the type of a piece of data as used for
        comparisons by the store. When the object is a `numpy.ndarray` a tuple
        of the type and number of dimensions is returned, otherwise just the
        type is returned.

        Args:
            data (object): the object whose type is to be returned

        Returns:
            the type of the object.
        """
        if isinstance(data, np.ndarray):
            return type(data), data.ndim
        else:
            return type(data)

    def create(self, name, datatype=None):
        """
        Creates an empty entry in the store for the name provided. This is
        intended for cases where you want to set the type of an entry in the
        store, but don't yet have any data for the entry.

        Args:
            name (str): the name of the entry.
            datatype (type): the type of the entry.

        Raises:
            ValueError: if `name` already exists in the store.
        """
        if name in self._store:
            raise ValueError("result named %s already exists in the store" % name)
        else:
            self._store[name] = Datagram(name, datatype)

    def get_dgram(self, name):
        """
        Returns the `Datagram` in the store associated with that entry.

        Args:
            name (str): the name of the entry

        Raises:
            KeyError: if there is no entry in the store with the requested
                name.

        Returns:
            the current `Datagram` object of the entry in the store.
        """
        return self._store[name]

    @property
    def namespace(self):
        """
        Returns a dictionary containing the raw data associated with all the
        entries in the store where the entry name is the key.

        Returns:
            A dictionary with all the raw data in the store.
        """
        ns = {}
        for k in self._store.keys():
            ns[k] = self._store[k].data
        return ns

    @property
    def types(self):
        """
        Returns a dictionary containing the types of all the entries in the
        store where the entry name is the key.

        Returns:
            A dictionary with all the types in the store.
        """
        ns = {}
        for k in self._store.keys():
            ns[k] = self._store[k].dtype
        return ns

    def get(self, name):
        """
        Retrieves the raw data associated with an entry in the store.

        Args:
            name (str): the name of the entry

        Raises:
            KeyError: if there is no entry in the store with the requested
                name.

        Returns:
            the raw data associated with the entry
        """
        return self._store[name].data

    def update(self, updates):
        """
        Update the using the passed dictionary, where the key in the dictionary
        is used as the name of the entry and the value becomes the new data
        associated with the entry.

        Args:
            updates (dict): the dictionary to use for the update.

        Raises:
            TypeError: if the type of data doesn't match the type of the
                existing entry in the store with that name.
        """
        if updates is not None:
            for k, v in updates.items():
                self.put(k, v)

    def put(self, name, data):
        """
        Sets the data associated with an entry in the store. If there is an
        existing entry in the store with that name, the type of the data is
        checked to see that it matches with what is already in the store.

        Args:
            name (str): the name of the entry
            data (object): the data to associate with the entry

        Raises:
            TypeError: if the type of data doesn't match the type of the
                existing entry in the store with that name.
        """
        if data is not None:
            datatype = self.get_type(data)
            if name in self._store:
                if datatype == self._store[name].dtype or self._store[name].dtype is None:
                    self._store[name].dtype = datatype
                    self._store[name].data = data
                else:
                    raise TypeError("type of new result (%s) differs from existing"
                                    " (%s)" % (datatype, self._store[name].dtype))
            else:
                self._store[name] = Datagram(name, datatype, data)

    def clear(self):
        """
        Clears all the entries currently in the store.
        """
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
        super().__init__(addr, ctx)
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
            if graph:
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


class Node(abc.ABC):
    """Abstract base class for nodes that interact with the AMI graph manager.

    This abstract class provides basically functionality for nodes that need
    to receive updates from the AMI graph managers publish socket. It also
    provides a method for nodes to report back information to the graph manager
    out-of-band from the normal gather mechanism.

    Args:
        node (int): the numeric node identifier
        graph_addr (str): the zmq address of the graph manager update socket
        msg_addr (str): the zmq address of the graph manager out-of-band
            message socket.
        ctx (zmq.Context): optional zmq context for the node to use. If none is
            passed it creates one.
    """

    def __init__(self, node, graph_addr, msg_addr, ctx=None):
        self.node = node
        if ctx is None:
            self.ctx = zmq.Context()
        else:
            self.ctx = ctx

        self.graph = None

        self.graph_comm = GraphReceiver(graph_addr)
        self.graph_comm.add_handler("graph", self.recv_graph)

        self.node_msg_comm = self.ctx.socket(zmq.PUSH)
        self.node_msg_comm.connect(msg_addr)

    @property
    @abc.abstractmethod
    def name(self):
        """
        An abstract property that subclassess should implement which returns
        the node's name.

        Returns:
            The name of this node
        """
        pass

    @abc.abstractmethod
    def recv_graph(self, name, version, payload):
        """
        An abstract method that subclasses should implement. This method is
        called everytime that a graph update is received.

        Args:
            name (str):      the name of the graph that is updated.
            version (int):   the version number of the updated graph.
            payload (bytes): the raw payload of the update.
        """
        pass

    def report(self, topic, payload):
        """
        Sends an out-of-band report from this node directly to the AMI graph
        manager without going through the normal gather mechanism. E.g. this
        could be used to report a failure executing the graph on the node.

        Args:
            topic (str): the topic of the report.
            payload (obj): the payload of the report. This can be any arbitrary
                object that can be serialized using dill.
        """
        self.node_msg_comm.send_string(topic, zmq.SNDMORE)
        self.node_msg_comm.send_string(self.name, zmq.SNDMORE)
        self.node_msg_comm.send(dill.dumps(payload))


class Collector(abc.ABC):
    """Abstract base class for collecting (via zeromq) results from many
    node's ResultsStores.

    Whenever results are received on the collection socket they are processed.
    This processing should be implemented in the subclass by overriding the
    `process_msg` method.

    The class also has the ability to register other sockets (plus a callback).
    During the main collection loop if there is data available on this extra
    socket, then the associated callback is called.

    Args:
        addr (str): the zmq address for receiving the collected results.
        ctx (zmq.Context): optional zmq context for the node to use. If none is
            passed it creates one.
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

    def register(self, sock, handler):
        """
        Register the passed socket with the poller used in the main collection
        loop. If data is received on the socket then the associated handler
        function is called. It is the responsibility of the handler function
        to read the data from the socket.

        Args:
            sock (zmq.Socket): the zmq socket to add to the poller.
            handler (function): the handler function to be called when the
                socket has data available.
        """
        self.handlers[sock] = handler
        self.poller.register(sock, zmq.POLLIN)

    def unregister(self, sock):
        """
        Removes a previously registered socket from the poller used in the main
        collection loop.

        Args:
            sock (zmq.Socket): the zmq socket to remove from the poller.
        """
        if sock in self.handlers:
            del self.handlers[sock]
            self.poller.unregister(sock)

    @abc.abstractmethod
    def process_msg(self, msg):
        """
        An abstract method that subclasses should implement. This method is
        called each time a message is received on the collector socket.

        Args:
            msg (CollectorMessage): the message to be processed.
        """
        pass

    def run(self):
        """
        The main collector loop runs forever polling the collector socket
        plus any additional sockets added by calling the `register` method.
        When data is available on the socket the corresponding handler is
        called.
        """
        while True:
            for sock, flag in self.poller.poll():
                if flag != zmq.POLLIN:
                    continue
                if sock is self.collector:
                    msg = self.collector.recv_pyobj()
                    self.process_msg(msg)
                elif sock in self.handlers:
                    self.handlers[sock]()


class GraphReceiver:
    """Class for handling graph updates from the AMI graph manager.

    This class is intended to handle graph update information published by the
    AMI graph manager. It allows handler functions to be set for certain topics
    or commands published by the graph manager. When a particular topic or
    command is received the corresponding handler function is called.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
    """

    def __init__(self, addr):
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sock.connect(addr)
        self.handlers = {"cmd": self.command}
        self.commands = {}
        self.special = set(self.handlers.keys())

    def command(self):
        """
        Called when a message with the topic "cmd" is received. If there are
        any handlers designated for the command received they will be called.
        """
        name = self.sock.recv_string()
        if name in self.commands:
            self.commands[name]()

    def add_handler(self, topic, handler):
        """
        Sets the handler for the requested topic to the provided handler
        function. Only one handler can be assigned to a topic, but a
        handler function can be used by multiple topics.

        The handler function is called with three positional arguments:
            name (str):      the name of the graph that is updated.
            version (int):   the version number of the updated graph.
            payload (bytes): the raw payload of the update.

        Args:
            topic (str): the name of the topic.
            handler (function): the handler function to be called.

        Raises:
            ValueError: if the topic name conflicts with one of the internally
                        reserved topics.
        """
        if topic not in self.special:
            self.handlers[topic] = handler
        else:
            raise ValueError("handler for topic %s cannot be modified" % topic)

    def add_command(self, name, handler):
        """
        Sets the handler for the requested command to the provided handler
        function. Only one handler can be assigned to a command, but a
        handler function can be used by multiple commands.

        The handler function is called with no arguments.

        Args:
            name (str): the name of the command.
            handler (function): the handler function to be called.
        """
        self.commands[name] = handler

    def recv(self, block=True):
        """
        Function should be called to receive data from the AMI graph manager.
        This function blocks until a graph update is available. Non-blocking
        behavior is possible by passing `block=False` to the call.

        Keyword Arguments:
            block (bool): determines if the function call should block. Defaults
                to True.

        Raises:
            zmq.Again: if no graph update is available and the function is called in
                non-blocking mode.
        """
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


class GraphInfoReceiver:
    """Class for handling information messages sent by the AMI graph manager.

    This class is intended to handle status information published by the
    AMI graph manager. The graph manager publishes status information such as
    node failures via zmq pub/sub. This class is intended as a helper for
    receiving these messages.

    Args:
        addr (str): the zmq address of the graph manager info service
            (e.g. tcp://localhost:5555)
        subscriptions (str): the subscription string used for topic filtering
            of the messages by zmq.
        ctx (zmq.Context): optional zmq context for the node to use. If none is
            passed it creates one.
    """

    def __init__(self, addr, subscriptions="", ctx=None):
        if ctx is None:
            self.ctx = zmq.Context()
        else:
            self.ctx = ctx
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, subscriptions)
        self.sock.connect(addr)

    def recv(self):
        """
        Low level function for receiving a raw message from the graph manager
        info service.

        Returns:
            A tuple containing the message topic, the name of the node that
                generated the message, and the raw payload of the message.
        """
        topic = self.sock.recv_string()
        node = self.sock.recv_string()
        payload = dill.loads(self.sock.recv())
        return topic, node, payload

    @property
    def messages(self):
        """
        A generator that returns formatted messages from the graph manager info
        service. Only messages where the payload is a string are returned by
        this generator. The message is re-formatted as string containing both
        the node name and the body of the message.

        Returns:
            A tuple consisting of the message topic and the formatted message.
        """
        while True:
            topic, node, msg = self.recv()
            if isinstance(msg, str):
                yield topic, "%s: %s" % (node, msg)


class CommHandler(abc.ABC):
    """Abstract base class for handling communication with the AMI graph manager.

    This abstract class provides an interface for interacting with the graph
    manager. The protocol used for talking to the manager is left to the
    subclass to implement.
    """

    def __init__(self):
        self._prune_keys = ['condition_needs', 'condition', 'reduction']
        self._expand_keys = ['inputs', 'outputs', 'condition_needs']

    @abc.abstractmethod
    def __enter__(self):
        pass

    @abc.abstractmethod
    def __exit__(self, exc_type, exc_value, traceback):
        pass

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
            and the values are the types of those features. In the case of a
            feature where the type is an ndarray the value is a tuple of the
            type and the number of dimensions of the array.
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
    def sources(self):
        """
        A dictionary with information on all of the external data sources that
        can be used as inputs for nodes in the graph, where the key is the name
        of the data source and the value is the type of the data source.

        Returns:
            A dictionary with information on all of the external data sources.
        """
        return self._request('get_sources')

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

    def get_type(self, names):
        """
        Lookups of the type of a `Var` node in the graph by its name field.

        Args:
            names (str or list): the name of the node. List of node names also
                                accepted.

        Returns:
            The types of the nodes if they are found in the graph
        """
        if isinstance(names, list):
            return self._request_batch(cmds=["lookup:%s" % name for name in names], check=True)
        else:
            return self._request("lookup:%s" % names, check=True)

    def fetch(self, names):
        """
        Attempts to fetch a feature with the requested name from the global
        features. If the feature is not present in the store then None is
        returned.

        Args:
            names (str or list): the name of the feature to fetch. List of
                                names also accepted.

        Returns:
            The object or list of objects that was fetched from the global
            feature store.
        """
        if isinstance(names, list):
            return self._request_batch(cmds=["fetch:%s" % name for name in names],
                                       check=True,
                                       retries=["fetch:%s" % self.auto(name) for name in names])
        else:
            # if the reply is none try fetching the 'view' version of the name
            return self._request("fetch:%s" % names, check=True, retry="fetch:%s" % self.auto(names))

    def add(self, nodes):
        """
        Attempt to add the requested node (or list of nodes) to the graph.

        Args:
            nodes (node or list): the node or list of nodes to add to the graph.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._post_dill('add_graph', nodes)

    def view(self, names):
        """
        Adds a Pick1 graph node for the requested graph output so that is can
        be viewed. The format of output name of the Pick1 node is determined
        by calling the `auto` method of this class.

        Args:
            names (str or list): The names of the graph outputs to start viewing.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        if not isinstance(names, list):
            names = [names]

        return self._view(names)

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

    def remove(self, names):
        """
        Removes the node (if it exists) with the requested name from the graph.

        Args:
            names (str or list): The names of the nodes to remove from the graph

        Returns:
            True if the graph change was successful, False otherwise.
        """
        if not isinstance(names, list):
            names = [names]

        return self._post_dill('del_graph', names)

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
    def _request(self, cmd, check=False, retry=None):
        pass

    @abc.abstractmethod
    def _request_batch(self, cmds, check=False, retries=None):
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


class ZmqCommHandler(CommHandler):
    """Abstract base class for handling communication with the AMI graph manager via zmq.

    This abstract class provides an interface for interacting with the graph
    manager via zmq. Provides support for implementing both a synchronous as
    well as an asynchronous version.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
        async_mode (bool): if True the asyncio version of zmq is used
    """

    def __init__(self, addr, async_mode=False):
        super().__init__()
        if async_mode:
            self._ctx = zmq.asyncio.Context()
        else:
            self._ctx = zmq.Context()
        self._addr = addr
        self._sock = self._ctx.socket(zmq.REQ)
        self._sock.connect(self._addr)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._sock.close()
        self._ctx.destroy()


class AsyncGraphCommHandler(ZmqCommHandler):
    """An asynchronous interface for handling communication with the AMI graph manager.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
    """

    def __init__(self, addr):
        super().__init__(addr, True)
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

    async def _request_batch(self, cmds, check=False, retries=None):
        results = []
        if retries is None:
            for cmd in cmds:
                results.append(await self._request(cmd, check))
        else:
            for cmd, retry in zip(cmds, retries):
                results.append(await self._request(cmd, check, retry))
        if all(entry is None for entry in results):
            return None
        else:
            return results

    async def _request_dill(self, cmd):
        async with self.lock:
            await self._sock.send_string(cmd)
            return dill.loads(await self._sock.recv())

    async def _post_dill(self, cmd, payload):
        async with self.lock:
            await self._sock.send_string(cmd, zmq.SNDMORE)
            await self._sock.send(dill.dumps(payload))
            return (await self._sock.recv_string()) == 'ok'

    async def _view(self, names):
        nodes = []
        for name in names:
            view_name = self.auto(name)
            var_type = await self.get_type(name)
            node_name = '%s_view' % view_name
            if var_type is None:
                inputs = name
                outputs = view_name
            else:
                inputs = gn.Var(name, var_type)
                outputs = gn.Var(view_name, var_type)
            nodes.append(self._make_node(gn.PickN, name=node_name, inputs=inputs, outputs=outputs, N=1))

        return await self.add(nodes)

    async def _load(self, filename):
        with open(filename, 'rb') as cnf:
            graph = dill.load(cnf)
        return await self.update(graph)

    async def _save(self, filename):
        graph = await self.graph
        with open(filename, 'wb') as cnf:
            return dill.dump(graph, cnf)


class GraphCommHandler(ZmqCommHandler):
    """A synchronous interface for handling communication with the AMI graph manager.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
    """

    def __init__(self, addr):
        super().__init__(addr, False)

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

    def _request_batch(self, cmds, check=False, retries=None):
        results = []
        if retries is None:
            for cmd in cmds:
                results.append(self._request(cmd, check))
        else:
            for cmd, retry in zip(cmds, retries):
                results.append(self._request(cmd, check, retry))
        if all(entry is None for entry in results):
            return None
        else:
            return results

    def _request_dill(self, cmd):
        self._sock.send_string(cmd)
        return dill.loads(self._sock.recv())

    def _post_dill(self, cmd, payload):
        self._sock.send_string(cmd, zmq.SNDMORE)
        self._sock.send(dill.dumps(payload))
        return self._sock.recv_string() == 'ok'

    def _view(self, names):
        nodes = []
        for name in names:
            view_name = self.auto(name)
            var_type = self.get_type(name)
            node_name = '%s_view' % view_name
            if var_type is None:
                inputs = name
                outputs = view_name
            else:
                inputs = gn.Var(name, var_type)
                outputs = gn.Var(view_name, var_type)
            nodes.append(self._make_node(gn.PickN, name=node_name, inputs=inputs, outputs=outputs, N=1))

        return self.add(nodes)

    def _load(self, filename):
        with open(filename, 'rb') as cnf:
            self.update(dill.load(cnf))

    def _save(self, filename):
        with open(filename, 'wb') as cnf:
            dill.dump(self.graph, cnf)
