class Msg(object):

    def __init__(self, name):
        self.name = name


class BrokerMsg(Msg):

    """
    Messages to command the broker to do something.
    """

    def __init__(self, name):
        super().__init__(name)


class NodeMsg(Msg):

    """
    Messages which should be cached and forwarded to node processes.
    """

    def __init__(self, name):
        super().__init__(name)


class CreateNode(BrokerMsg):

    def __init__(self, name, node_type, state={}):
        super().__init__(name)
        self.node_type = node_type
        self.state = state

    def __repr__(self):
        return f"CreateNode(name={self.name}, node_type={self.node_type}, state={self.state})"


class Library(BrokerMsg):

    def __init__(self, name, paths):
        super().__init__(name)
        self.paths = paths


class ReloadLibrary(NodeMsg):

    def __init__(self, name, mods):
        super().__init__(name)
        self.mods = mods


class CloseNode(NodeMsg):

    def __init__(self):
        super().__init__("")


class DisplayNode(NodeMsg):

    def __init__(self, name, topics, terms, state={}, units={}, redisplay=False, geometry=None, terminals=None):
        super().__init__(name)
        self.topics = topics
        self.terms = terms
        self.state = state
        self.units = units
        self.redisplay = redisplay
        self.geometry = geometry
        self.terminals = terminals

    def __repr__(self):
        return f"""DisplayNode(name={self.name},
        topics={self.topics},
        terms={self.terms},
        units={self.units},
        redisplay={self.redisplay},
        geometry={self.geometry},
        terminals={self.geometry})"""


class NodeCheckpoint(NodeMsg):

    def __init__(self, name, state={}, event=None):
        super().__init__(name)
        self.state = state
        self.event = event


class NodeTermAdded(NodeMsg):

    def __init__(self, name, term, state):
        super().__init__(name)
        self.term = term
        self.state = state


class NodeTermRemoved(NodeMsg):

    def __init__(self, name, term, state):
        super().__init__(name)
        self.term = term
        self.state = state


class NodeTermConnected(NodeMsg):

    def __init__(self,
                 localNode, localNodeIsSource,
                 localTerm, localTermState,
                 remoteNode, remoteNodeIsSource,
                 remoteTerm, remoteTermState):
        super().__init__(localNode)
        self.localNode = localNode
        self.localNodeIsSource = localNodeIsSource
        self.localTerm = localTerm
        self.localTermState = localTermState
        self.remoteNode = remoteNode
        self.remoteNodeIsSource = remoteNodeIsSource
        self.remoteTerm = remoteTerm
        self.remoteTermState = remoteTermState


class NodeTermDisconnected(NodeMsg):

    def __init__(self,
                 localNode, localNodeIsSource,
                 localTerm, localTermState,
                 remoteNode, remoteNodeIsSource,
                 remoteTerm, remoteTermState):
        super().__init__(localNode)
        self.localNode = localNode
        self.localNodeIsSource = localNodeIsSource
        self.localTerm = localTerm
        self.localTermState = localTermState
        self.remoteNode = remoteNode
        self.remoteNodeIsSource = remoteNodeIsSource
        self.remoteTerm = remoteTerm
        self.remoteTermState = remoteTermState
