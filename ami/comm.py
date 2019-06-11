import abc
import zmq
import dill
import asyncio
import logging
import functools
import numpy as np
import zmq.asyncio
from enum import IntEnum

import amitypes as at
import ami.graph_nodes as gn
from ami.graphkit_wrapper import Graph
from ami.data import MsgTypes, Message, Transition, CollectorMessage, Datagram


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
    Sync = 5600


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
    def names(self):
        """
        Returns a set containing the names of all the entries in the store.

        Returns:
            A set of the names of the entries in the store.
        """
        return set(self._store)

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

    def collector_message(self, identity, heartbeat, name, version, payload):
        msg = CollectorMessage(MsgTypes.Datagram, identity, heartbeat, name, version, payload)
        self.send(msg)


class ResultStore(ZmqHandler):
    """
    This class is a AMI /graph node that collects results
    from a single process and has the ability to send them
    to another (via zeromq). The sending end point is typically
    a Collector object.
    """

    def __init__(self, addr, ctx=None):
        super().__init__(addr, ctx)
        self.stores = {}

    def __bool__(self):
        if self.stores:
            return True
        else:
            return False

    def __contains__(self, name):
        return name in self.stores

    def configure(self, name, version):
        if name not in self.stores:
            self.stores[name] = Store(version=version)
        else:
            self.stores[name].version = version

    def remove(self, name):
        del self.stores[name]

    def update(self, name, updates):
        self.stores[name].update(updates)

    def collect(self, identity, heartbeat):
        for name, store in self.stores.items():
            self.collector_message(identity, heartbeat, name, store.version, store.namespace)

    def clear(self):
        for store in self.stores.values():
            store.clear()


class ContributionBuilder(abc.ABC):
    def __init__(self, num_contribs):
        self.num_contribs = num_contribs
        self.pending = {}
        self.contribs = {}

    @abc.abstractmethod
    def _complete(self, eb_key, identity):
        pass

    @abc.abstractmethod
    def _update(self, eb_key, identity, *args, **kwargs):
        pass

    def complete(self, eb_key, identity):
        if eb_key in self.pending:
            self._complete(eb_key, identity)
            del self.pending[eb_key]
            del self.contribs[eb_key]
            logger.debug("Completed key %s", eb_key)

    def mark(self, eb_key, eb_id):
        if 0 <= eb_id < self.num_contribs:
            if eb_key not in self.contribs:
                self.contribs[eb_key] = 0
            self.contribs[eb_key] |= (1 << eb_id)
        else:
            raise ValueError("eb_id of %d is invalid for %d contributors" % (eb_id, self.num_contribs))

    def update(self, eb_key, eb_id, *args, **kwargs):
        if 0 <= eb_id < self.num_contribs:
            self._update(eb_key, eb_id, *args, **kwargs)
            self.mark(eb_key, eb_id)
        else:
            raise ValueError("eb_id of %d is invalid for %d contributors" % (eb_id, self.num_contribs))

    def ready(self, eb_key):
        if eb_key not in self.contribs:
            return False
        return ((1 << self.num_contribs) - 1) == self.contribs[eb_key]


class GraphBuilder(ContributionBuilder):
    def __init__(self, num_contribs, depth, color, completion):
        super().__init__(num_contribs)
        self.depth = depth
        self.color = color
        self.latest = 0
        self.graph = None
        self.pending_graphs = {}
        self.version = None
        self.completion = completion

    def _init(self, name):
        if self.graph is None:
            self.graph = Graph(name)

    def _edit(self, cmd, obj):
        if cmd == "set":
            self.graph = obj
        elif cmd == "add":
            self.graph.add(obj)
        elif cmd == "del":
            for node in obj:
                self.graph.remove(node)

    def _compile(self, args):
        if self.graph:
            self.graph.compile(**args)

    def prune(self, prune_key=None):
        if prune_key is None:
            depth = self.depth
        else:
            depth = self.latest - prune_key
        if len(self.pending) > depth:
            for eb_key in sorted(self.pending.keys(), reverse=True)[depth:]:
                logger.debug("Pruned uncompleted key %d", eb_key)
                del self.pending[eb_key]
                del self.contribs[eb_key]

    def set_graph(self, name, ver_key, args, graph):
        self.pending_graphs[ver_key] = (False, "set", name, args, graph)

    def add_graph(self, name, ver_key, args, nodes):
        self.pending_graphs[ver_key] = (True, "add", name, args, nodes)

    def del_graph(self, name, ver_key, args, nodes):
        self.pending_graphs[ver_key] = (True, "del", name, args, nodes)

    def apply_graph(self, ver_key):
        if self.version is None or ver_key > self.version:
            versions = [ver for ver in sorted(self.pending_graphs) if ver <= ver_key]
            if ver_key in versions:
                for version in versions:
                    init, cmd, name, args, obj = self.pending_graphs[version]
                    self._init(name)
                    self._edit(cmd, obj)
                    self._compile(args)
                    del self.pending_graphs[version]
                self.version = ver_key
                return True
            else:
                return False
        elif ver_key == self.version:
            return True
        else:
            return False

    def _complete(self, eb_key, identity):
        if self.apply_graph(self.pending[eb_key].version):
            contribs = self.pending[eb_key].namespace
            self.pending[eb_key].clear()
            if self.graph:
                for data in contribs.values():
                    self.pending[eb_key].update(self.graph(data, color=self.color))
        else:
            self.pending[eb_key].clear()
        self.completion(eb_key, identity, self.pending[eb_key])

    def _update(self, eb_key, eb_id, ver_key, data):
        if eb_key not in self.pending:
            self.pending[eb_key] = Store(version=ver_key)
            self.contribs[eb_key] = 0
        if eb_key > self.latest:
            self.latest = eb_key
        if ver_key != self.pending[eb_key].version:
            logger.error("Graph version mismatch: heartbeat %s from id %s has version %s when %s was expected",
                         eb_key, eb_id, ver_key, self.pending[eb_key].version)
        else:
            self.pending[eb_key].put(eb_id, data)


class TransitionBuilder(ContributionBuilder, ZmqHandler):
    def __init__(self, num_contribs, addr, ctx=None):
        ContributionBuilder.__init__(self, num_contribs)
        ZmqHandler.__init__(self, addr, ctx)

    def _complete(self, eb_key, identity):
        self.message(MsgTypes.Transition, identity, Transition(eb_key, self.pending[eb_key]))

    def _update(self, eb_key, eb_id, payload):
        if eb_key not in self.pending:
            self.pending[eb_key] = payload
        elif payload != self.pending[eb_key]:
            logger.error("Transition mismatch: %s payload from id %s does not match the other contributers",
                         eb_key, eb_id)


class EventBuilder(ZmqHandler):

    def __init__(self, num_contribs, depth, color, addr, ctx=None):
        super().__init__(addr, ctx)
        self.num_contribs = num_contribs
        self.depth = depth
        self.color = color
        self.builders = {}

    def create(self, name):
        self.builders[name] = GraphBuilder(self.num_contribs,
                                           self.depth,
                                           self.color,
                                           functools.partial(self.completion, name))

    def destroy(self, name):
        del self.builders[name]

    def prune(self, name, prune_key=None):
        self.builders[name].prune(prune_key)

    def set_graph(self, name, ver_key, args, graph):
        if name not in self.builders:
            self.create(name)
        self.builders[name].set_graph(name, ver_key, args, graph)

    def add_graph(self, name, ver_key, args, graph):
        if name not in self.builders:
            self.create(name)
        self.builders[name].add_graph(name, ver_key, args, graph)

    def del_graph(self, name, ver_key, args, graph):
        if name not in self.builders:
            self.create(name)
        self.builders[name].del_graph(name, ver_key, args, graph)

    def purge_graph(self, name, ver_key, args, graph):
        if name in self.builders:
            self.destroy(name)

    def complete(self, name, eb_key, identity):
        self.builders[name].complete(eb_key, identity)

    def completion(self, name, eb_key, identity, payload):
        self.collector_message(identity, eb_key, name, payload.version, payload.namespace)

    def update(self, name, eb_key, eb_id, ver_key, data):
        if name not in self.builders:
            self.create(name)
        self.builders[name].update(eb_key, eb_id, ver_key, data)

    def contribs(self, name):
        return self.builders[name].contribs

    def pending(self, name):
        return self.builders[name].pending

    def pending_graphs(self, name):
        return self.builders[name].pending_graphs

    def graph(self, name):
        return self.builders[name].graph

    def version(self, name):
        return self.builders[name].version

    def latest(self, name):
        return self.builders[name].latest

    def mark(self, name, eb_key, eb_id):
        self.builders[name].mark(eb_key, eb_id)

    def ready(self, name, eb_key):
        return self.builders[name].ready(eb_key)


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

        self.graphs = {}

        self.graph_initialized = False

        self.graph_comm = GraphReceiver(graph_addr, ctx)
        self.graph_comm.add_handler("graph", self.recv_graph)
        self.graph_comm.add_handler("init", self.recv_graph_init)
        self.graph_comm.add_handler("add", self.recv_graph_add)
        self.graph_comm.add_handler("del", self.recv_graph_del)
        self.graph_comm.add_handler("purge", self.recv_graph_purge)

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
    def recv_graph(self, name, version, args, graph):
        """
        An abstract method that subclasses should implement. This method is
        called everytime that a complete graph update is received.

        Args:
            name (str):      the name of the graph that is updated.
            version (int):   the version number of the updated graph.
            args (dict):     the keyword arguments to be used for compilation.
            graph (Graph):   the updated graph.
        """
        pass

    def recv_graph_init(self, name, version, args, graph):
        """
        This method is called everytime that a graph init update is received.
        The init messages are meant only for newly connecting nodes. If the
        graph has never been initialized then the `rech_graph` method is
        called.

        Args:
            name (str):      the name of the graph that is updated.
            version (int):   the version number of the updated graph.
            args (dict):     the keyword arguments to be used for compilation.
            graph (Graph):   the updated graph.
        """
        if not self.graph_initialized:
            self.recv_graph(name, version, args, graph)
            self.graph_initialized = True

    @abc.abstractmethod
    def recv_graph_add(self, name, version, args, nodes):
        """
        An abstract method that subclasses should implement. This method is
        called everytime that a graph addition update is received.

        Args:
            name (str):      the name of the graph that is updated.
            version (int):   the version number of the updated graph.
            args (dict):     the keyword arguments to be used for compilation.
            nodes (object):  the nodes to add to the graph.
        """
        pass

    @abc.abstractmethod
    def recv_graph_del(self, name, version, args, nodes):
        """
        An abstract method that subclasses should implement. This method is
        called everytime that a graph remove update is received.

        Args:
            name (str):      the name of the graph that is updated.
            version (int):   the version number of the updated graph.
            args (dict):     the keyword arguments to be used for compilation.
            nodes (object):  the nodes to remove from the graph.
        """
        pass

    @abc.abstractmethod
    def recv_graph_purge(self, name, version, args, graph):
        """
        An abstract method that subclasses should implement. This method is
        called everytime that a graph purge is received.

        Args:
            name (str):      the name of the graph that should be purged.
            version (int):   the version number of the purged graph.
            args (dict):     the keyword arguments to be used for compilation.
            graph (Graph):   the purged graph.
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
    node's ResultStores.

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
        self.running = True
        self.exitcode = 0

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

        Returns:
            The current value of the exitcode attribute of the class.
        """
        while self.running:
            for sock, flag in self.poller.poll():
                if flag != zmq.POLLIN:
                    continue
                if sock is self.collector:
                    msg = self.collector.recv_pyobj()
                    self.process_msg(msg)
                elif sock in self.handlers:
                    self.handlers[sock]()

        return self.exitcode


class GraphReceiver:
    """Class for handling graph updates from the AMI graph manager.

    This class is intended to handle graph update information published by the
    AMI graph manager. It allows handler functions to be set for certain topics
    or commands published by the graph manager. When a particular topic or
    command is received the corresponding handler function is called.

    Args:
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
        ctx (zmq.Context): optional zmq context for the node to use. If none is
            passed it creates one.
    """

    def __init__(self, addr, ctx=None):
        if ctx is None:
            self.ctx = zmq.Context()
            self.owner = True
        else:
            self.ctx = ctx
            self.owner = False
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, "")
        self.sock.connect(addr)
        self.handlers = {"cmd": self.command}
        self.commands = {}
        self.special = set(self.handlers.keys())

    def close(self):
        """
        Function should be called to clean up zmq resources. All sockets are
        closed and the zmq.Context is destroyed if it is owned by this
        instance.
        """
        self.sock.close()
        if self.owner:
            self.ctx.destroy()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

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
            name, version, args = self.sock.recv_pyobj()
            payload = dill.loads(self.sock.recv())
            if topic in self.handlers:
                self.handlers[topic](name, version, args, payload)


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
            self.owner = True
        else:
            self.ctx = ctx
            self.owner = False
        self.sock = self.ctx.socket(zmq.SUB)
        self.sock.setsockopt_string(zmq.SUBSCRIBE, subscriptions)
        self.sock.connect(addr)

    def close(self):
        """
        Function should be called to clean up zmq resources. All sockets are
        closed and the zmq.Context is destroyed if it is owned by this
        instance.
        """
        self.sock.close()
        if self.owner:
            self.ctx.destroy()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

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

    Args:
        name(str): the name of the graph instance in the manager to use

    Raises:
        TypeError: if `name` is an unacceptable type.
    """

    def __init__(self, name):
        self._name = name
        self._allocated = False
        self._prune_keys = ['condition_needs', 'condition', 'reduction']
        self._expand_keys = ['inputs', 'outputs', 'condition_needs']

        if name is not None and not isinstance(self._name, str):
            raise TypeError("%s only supports graph names of type %s not %s" % (__class__, str, type(name)))

    @abc.abstractmethod
    def close(self):
        """
        This abstact method should be implemented by subclasses to cleanup any
        connected resources. The instance is no longer intended to be used
        after calling close.
        """
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @staticmethod
    def _process(func, value):
        """
        Helper method for post-processing on data returned from the manager

        Args:
            func (function): the post-processing function.
            value (object): the data to pass to the post-processing function.

        Returns:
            The original data if the passed processing function is None,
            otherwise the return value of the function acting on the data is
            returned.

        Raises:
            TypeError: if `func` is not callable or None
        """
        if func is None:
            return value
        elif callable(func):
            return func(value)
        else:
            raise TypeError("The 'func' parameter must be a callable")

    @staticmethod
    def _sources(srcs):
        """
        Helper function for deserializing the type-annotations in the sources
        dictionary.

        Args:
            srcs (dict): the dictionary of sources that needs to be
                         deserialized.

        Returns:
            The deserialized version of sources dictionary.
        """
        if srcs is not None:
            loaded_srcs = {}
            for n, t in srcs.items():
                if isinstance(t, str):
                    loaded_srcs[n] = at.loads(t)
                else:
                    loaded_srcs[n] = t
            return loaded_srcs

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

        return node(**kwargs)

    def _make_view_node(self, name, view_name):
        """
        Constructs a special graph view node of the requested type.

        Args:
            name (str): the name of the input to this view node.
            view_name (str): the name of the output of this view node:

        Returns:
            The constructed graph view node.
        """
        node_name = '%s_view' % view_name

        return self._make_node(gn.PickN, name=node_name, inputs=name, outputs=view_name, N=1)

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
    def active(self):
        """
        A set of the names all the active graphs in the graph manager.

        Returns:
            A set of the names of the active graphs.
        """
        return self._query('list_graphs')

    @property
    def current(self):
        """
        The name of the current graph.

        Returns:
            The name of the current graph
        """
        return self._get_current()

    @property
    def heartbeat(self):
        """
        Fetches the latest heartbeat for which the graph manager has received
        results from the graph.

        Returns:
            The latest heartbeat that the manager has results from the graph.
        """
        return self._request('get_heartbeat')

    @property
    def graph(self):
        """
        Fetches the current graph instance from the manager.

        Returns:
            An object of type `Graph` representing the current analysis graph.
        """
        return self._request_dill('get_graph')

    @property
    def features(self):
        """
        Information on the features currently available in the global feature
        store of the graph.

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
        return self._request('get_sources', processing=self._sources)

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

    def fetch(self, names):
        """
        Attempts to fetch a feature with the requested name from the global
        features of the graph. If the feature is not present in the store then
        None is returned.

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

    def unview(self, names):
        """
        Removes a Pick1 graph node for the requested graph output that was
        previously created by the 'view' method. If no such Pick1 exists then
        nothing is done.

        Args:
            names (str or list): The names of the graph outputs to stop viewing.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        if not isinstance(names, list):
            names = [names]

        return self.remove(["%s_view" % self.auto(name) for name in names])

    def addPickN(self, name, inputs, outputs, N=1, condition_needs=None):
        """
        Adds a PickN graph node to the graph.

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
        Adds a Map graph node to the graph.

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
        Adds a ReduceByKey graph node to the graph.

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
        Adds a Binning graph node to the graph.

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
        Adds a FilterOn graph node to the graph.

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
        Adds a FilterOff graph node to the graph.

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

    def select(self, name):
        """
        Select the graph from the graph manager to use. If the named graph does
        not already exist it will be created.

        Args:
            name (str): the name of the graph to use.

        Returns:
            True if the graph change was successful, False otherwise.

        Raises:
            TypeError: if `name` is an unacceptable type.
        """
        if isinstance(name, str):
            return self._set_current(name)
        else:
            raise TypeError("graph name must be of type %s" % str)

    def create(self):
        """
        Creates a graph instance in the manager if one does not already exist.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._command('create_graph')

    def destroy(self):
        """
        Destroys the graph instance in the manager if one already exists.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._command('destroy_graph')

    def clear(self):
        """
        Clears the current graph instance in the manager.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._command('clear_graph')

    def reset(self):
        """
        Clears all the data currently in the manager's feature store that is
        associated with the current graph instance.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._command('reset_features')

    def update(self, graph):
        """
        Replaces the current graph instance in the manager with the requested
        graph.

        Args:
            graph (Graph): The new graph for the manager to use.

        Returns:
            True if the graph change was successful, False otherwise.
        """
        return self._post_dill('set_graph', graph)

    def save(self, filename):
        """
        Saves the current instance of the graph from the manager to a file.

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
        Loads a graph from a file and replaces the current graph instance in the
        manager with it.

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
    def _query(self, cmd):
        pass

    @abc.abstractmethod
    def _request(self, cmd, check=False, retry=None, processing=None):
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
    def _get_current(self):
        pass

    @abc.abstractmethod
    def _set_current(self):
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
        name (str): the name of the graph instance in the manager to use
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
        async_mode (bool): if True the asyncio version of zmq is used
        ctx (zmq.Context): zmq context for the node to use.
        owner (bool): if True this class is the owner of the context
    """

    def __init__(self, name, addr, ctx, owner):
        super().__init__(name)
        self._ctx = ctx
        self._addr = addr
        self._owner = owner
        self._sock = self._ctx.socket(zmq.REQ)
        self._sock.connect(self._addr)

    def close(self):
        self._sock.close()
        if self._owner:
            self._ctx.destroy()

    @abc.abstractmethod
    def _header(self, cmd, flags=0):
        pass


class AsyncGraphCommHandler(ZmqCommHandler):
    """An asynchronous interface for handling communication with the AMI graph manager.

    Args:
        name (str): the name of the graph instance in the manager to use
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
        ctx (zmq.Context): optional shared zmq context for the node to use.

    Raises:
        TypeError: if `ctx` is an unacceptable type.
    """

    def __init__(self, name, addr, ctx=None):
        if ctx is None:
            ctx = zmq.asyncio.Context()
            owner = True
        elif not isinstance(ctx, zmq.asyncio.Context):
            raise TypeError("%s only supports shared contexts of type %s not %s"
                            % (__class__, zmq.asyncio.Context, type(ctx)))
        else:
            owner = False
        super().__init__(name, addr, ctx, owner)
        self.lock = asyncio.Lock()

    async def _header(self, cmd, flags=0):
        if self._name:
            await self._sock.send_string(cmd, zmq.SNDMORE)
            await self._sock.send_string(self._name, flags)
        else:
            raise ValueError("graph name must be a non-emtpy string")

    async def _command(self, cmd):
        async with self.lock:
            await self._header(cmd)
            return (await self._sock.recv_string()) == 'ok'

    async def _query(self, cmd):
        async with self.lock:
            await self._sock.send_string(cmd)
            return await self._sock.recv_pyobj()

    async def _request(self, cmd, check=False, retry=None, processing=None):
        async with self.lock:
            await self._header(cmd)
            if check:
                reply = await self._sock.recv_string()
                if reply == 'ok':
                    return self._process(processing, await self._sock.recv_pyobj())
                elif retry is not None:
                    await self._header(retry)
                    reply = await self._sock.recv_string()
                    if reply == 'ok':
                        return self._process(processing, await self._sock.recv_pyobj())
            else:
                return self._process(processing, await self._sock.recv_pyobj())

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
            await self._header(cmd)
            return dill.loads(await self._sock.recv())

    async def _post_dill(self, cmd, payload):
        async with self.lock:
            await self._header(cmd, zmq.SNDMORE)
            await self._sock.send(dill.dumps(payload))
            return (await self._sock.recv_string()) == 'ok'

    async def _view(self, names):
        nodes = []
        for name in names:
            nodes.append(self._make_view_node(name, self.auto(name)))

        return await self.add(nodes)

    async def _get_current(self):
        async with self.lock:
            return self._name

    async def _set_current(self, name):
        async with self.lock:
            self._name = name
        if name in await self.active:
            return True
        else:
            return await self.create()

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

    This class is not thread-safe since it uses a single zeromq socket which can
    not be shared between threads. Multiple threads should each use their own
    instance of the class.

    Args:
        name (str): the name of the graph instance in the manager to use
        addr (str): the zmq address of the graph manager (e.g. tcp://localhost:5555)
        ctx (zmq.Context): optional shared zmq context for the node to use.

    Raises:
        TypeError: if `ctx` is an unacceptable type.
    """

    def __init__(self, name, addr, ctx=None):
        if ctx is None:
            ctx = zmq.Context()
            owner = True
        elif not isinstance(ctx, zmq.Context):
            raise TypeError("%s only supports shared contexts of type %s not %s"
                            % (__class__, zmq.Context, type(ctx)))
        else:
            owner = False
        super().__init__(name, addr, ctx, owner)

    def _header(self, cmd, flags=0):
        if self._name:
            self._sock.send_string(cmd, zmq.SNDMORE)
            self._sock.send_string(self._name, flags)
        else:
            raise ValueError("graph name must be a non-emtpy string")

    def _command(self, cmd):
        self._header(cmd)
        return self._sock.recv_string() == 'ok'

    def _query(self, cmd):
        self._sock.send_string(cmd)
        return self._sock.recv_pyobj()

    def _request(self, cmd, check=False, retry=None, processing=None):
        self._header(cmd)
        if check:
            reply = self._sock.recv_string()
            if reply == 'ok':
                return self._process(processing, self._sock.recv_pyobj())
            elif retry is not None:
                self._header(retry)
                reply = self._sock.recv_string()
                if reply == 'ok':
                    return self._process(processing, self._sock.recv_pyobj())
        else:
            return self._process(processing, self._sock.recv_pyobj())

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
        self._header(cmd)
        return dill.loads(self._sock.recv())

    def _post_dill(self, cmd, payload):
        self._header(cmd, zmq.SNDMORE)
        self._sock.send(dill.dumps(payload))
        return self._sock.recv_string() == 'ok'

    def _view(self, names):
        nodes = []
        for name in names:
            nodes.append(self._make_view_node(name, self.auto(name)))

        return self.add(nodes)

    def _get_current(self):
        return self._name

    def _set_current(self, name):
        self._name = name
        if name in self.active:
            return True
        else:
            return self.create()

    def _load(self, filename):
        with open(filename, 'rb') as cnf:
            self.update(dill.load(cnf))

    def _save(self, filename):
        with open(filename, 'wb') as cnf:
            dill.dump(self.graph, cnf)
