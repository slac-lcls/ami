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

    def __init__(
        self,
        name,
        topics,
        terms,
        state={},
        units={},
        redisplay=False,
        geometry=None,
        terminals=None,
        label=None,
        term_labels=None,
    ):
        super().__init__(name)
        self.topics = topics
        self.terms = terms
        self.state = state
        self.units = units
        self.redisplay = redisplay
        self.geometry = geometry
        self.terminals = terminals
        self.label = label
        self.term_labels = term_labels or {}

    def __repr__(self):
        return f"""DisplayNode(name={self.name},
        topics={self.topics},
        terms={self.terms},
        units={self.units},
        redisplay={self.redisplay},
        geometry={self.geometry},
        terminals={self.geometry},
        label={self.label},
        term_labels={self.term_labels})"""


class NodeCheckpoint(NodeMsg):

    def __init__(self, name, state={}, event=None):
        super().__init__(name)
        self.state = state
        self.event = event


class NodeCtrlUpdate(NodeMsg):
    """Push a ctrl parameter update directly to a running NodeProcess window.

    Sent by PvCtrlServer when an EPICS pvput changes a node parameter so the
    visible spinbox/checkbox/combo in the NodeProcess window stays in sync.
    The NodeProcess applies the update with blockSignals so no checkpoint is
    echoed back to the flowchart.
    """

    def __init__(self, name, parameters):
        super().__init__(name)
        self.parameters = parameters  # {param: val} or {group: {param: val}}


class NodeReferencesUpdate(NodeMsg):
    """Push the CSV reference overlays of a plot node to a running NodeProcess window.

    Sent by AmiCli when an agent sets or removes a reference. references is the
    complete desired set ({name: path}); the NodeProcess adds/removes overlays to
    match and checkpoints the new widget state back to the flowchart.
    """

    def __init__(self, name, references):
        super().__init__(name)
        self.references = references


class NodeWidgetStateUpdate(NodeMsg):
    """Push a widget.restoreState() update to a running NodeProcess window.

    Sent by AmiCli when an agent changes a node's widget-level state directly (e.g. PythonEditor
    code via set_python_code). Unlike NodeCtrlUpdate, this is applied with signals left on, so the
    NodeProcess's own on-change handlers fire and a checkpoint is sent back to the flowchart —
    keeping the open window's node state in sync with what's now on screen. This intentionally
    overwrites any unsaved edits the user made directly in the open window.
    """

    def __init__(self, name, state):
        super().__init__(name)
        self.state = state  # passed to widget.restoreState(state)


class NodeScreenshotRequest(NodeMsg):
    """Ask a running NodeProcess window to export its plot as a PNG.

    Sent by AmiCli (render_plot) to a node whose window is already open. The NodeProcess answers
    after its next data_updated, so the image always has live data in it, not a blank plot.
    request_id lets the GUI process match the reply to the caller that's waiting on it.
    """

    def __init__(self, name, request_id):
        super().__init__(name)
        self.request_id = request_id


class NodeScreenshotReply(NodeMsg):
    """Reply to NodeScreenshotRequest, sent on the checkpoint socket (not cached — see
    MessageBroker.handle_checkpoint) directly back to the GUI process.
    """

    def __init__(self, name, request_id, png=None, error=None):
        super().__init__(name)
        self.request_id = request_id
        self.png = png  # PNG bytes, or None on error
        self.error = error  # error string, or None on success


class NodeTermAdded(NodeMsg):

    def __init__(self, name, term, state):
        super().__init__(name)
        self.term = term
        self.state = state


class NodeTermRemoved(NodeMsg):

    def __init__(self, name, term):
        super().__init__(name)
        self.term = term


class NodeTermConnected(NodeMsg):

    def __init__(
        self,
        localNode,
        localNodeIsSource,
        localTerm,
        localTermState,
        remoteNode,
        remoteNodeIsSource,
        remoteTerm,
        remoteTermState,
        remoteNodeLabel="",
    ):
        super().__init__(localNode)
        self.localNode = localNode
        self.localNodeIsSource = localNodeIsSource
        self.localTerm = localTerm
        self.localTermState = localTermState
        self.remoteNode = remoteNode
        self.remoteNodeIsSource = remoteNodeIsSource
        self.remoteTerm = remoteTerm
        self.remoteTermState = remoteTermState
        self.remoteNodeLabel = remoteNodeLabel


class NodeTermDisconnected(NodeMsg):

    def __init__(
        self,
        localNode,
        localNodeIsSource,
        localTerm,
        localTermState,
        remoteNode,
        remoteNodeIsSource,
        remoteTerm,
        remoteTermState,
    ):
        super().__init__(localNode)
        self.localNode = localNode
        self.localNodeIsSource = localNodeIsSource
        self.localTerm = localTerm
        self.localTermState = localTermState
        self.remoteNode = remoteNode
        self.remoteNodeIsSource = remoteNodeIsSource
        self.remoteTerm = remoteTerm
        self.remoteTermState = remoteTermState


class NodeLabelChanged(NodeMsg):

    def __init__(self, name, label):
        super().__init__(name)
        self.label = label
