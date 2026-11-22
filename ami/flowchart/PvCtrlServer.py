import logging

from p4p.nt import NTScalar
from p4p.server import Server, StaticProvider
from p4p.server.thread import SharedPV

from ami import LogConfig
from ami.client import flowchart_messages as fcMsgs
from ami.qt_dispatch import QtDispatcher

logger = logging.getLogger(LogConfig.get_package_name(__name__))

# Widget types that cannot be safely exposed as EPICS PVs
_SKIP_TYPES = {"file_in", "file_out", "color"}

# Mapping from uiTemplate widget type to p4p NTScalar type code
_TYPE_TO_NT = {
    "intSpin": "l",  # int64
    "spin": "d",  # float64
    "doubleSpin": "d",
    "check": "?",  # bool
    "combo": "s",  # string
    "text": "s",
}


class _CtrlPutHandler:
    """PUT handler for a single node ctrl parameter PV.

    p4p's thread SharedPV runs put() on a p4p worker thread, NOT the Qt main thread.
    put() only validates the value and answers the client; the GUI update is handed
    to the main thread with the dispatcher.  The node is looked up by name when that
    runs, so a node that was closed or replaced (File > Open) is never written to.
    """

    def __init__(self, node_name, param, group, ptype, opts, chart, dispatcher):
        self.node_name = node_name
        self.param = param
        self.group = group
        self.ptype = ptype
        self.opts = opts
        self.chart = chart
        self.dispatcher = dispatcher

    def put(self, pv, op):
        try:
            raw = op.value()
            val = raw["value"] if hasattr(raw, "__getitem__") else raw
            val = self._validate(val)
            # Post the new value so pvput/pvget see it before op.done() returns.
            pv.post(val)
            op.done()
            # The GUI update must run in the Qt main thread (see class docstring).
            self.dispatcher.post(lambda: self._update_gui(val))
        except Exception as e:
            logger.error("PvCtrlServer PUT error for %s.%s: %s", self.node_name, self.param, e)
            op.done(error=str(e))

    def _validate(self, val):
        if self.ptype == "intSpin":
            val = int(val)
            if "min" in self.opts:
                val = max(val, self.opts["min"])
            if "max" in self.opts:
                val = min(val, self.opts["max"])
        elif self.ptype in ("doubleSpin", "spin"):
            val = float(val)
            if "min" in self.opts:
                val = max(val, self.opts["min"])
            if "max" in self.opts:
                val = min(val, self.opts["max"])
        elif self.ptype == "check":
            val = bool(val)
        else:
            val = str(val)
        return val

    def _update_gui(self, val):
        """Update the ctrl widget spinbox/checkbox/combo and mark the node changed.

        Runs in the Qt main thread (posted by put()).  setState() fires sigStateChanged which triggers
        refreshStatePanel so the inspector panel updates automatically.  sigNodeChanged
        is emitted so the Apply button highlights green.

        Also fires a NodeCtrlUpdate ZMQ message to any open NodeProcess window so the
        visible spinbox there stays in sync with the pvput value.
        """
        try:
            node = self._find_node()
            if node is None:
                logger.warning("PvCtrlServer: node %s no longer exists, ignoring PUT to %s", self.node_name, self.param)
                return
            state = {self.group: {self.param: val}} if self.group else {self.param: val}
            # setState calls setWidget → setValue, which fires valueChanged → sigChanged →
            # state_changed → update() (updates node.values) + sigStateChanged (updates panel).
            node.stateGroup.setState(state)
            if node.isChanged(True, False):
                node.changed = True
                self.chart.sigNodeChanged.emit(node)
            # Push to NodeProcess window if one is open for this node.
            self._push_to_node_process(state)
        except Exception as e:
            logger.error("PvCtrlServer GUI update error for %s.%s: %s", self.node_name, self.param, e)

    def _find_node(self):
        """The node currently in the graph under this name, or None."""
        graph = self.chart._graph
        if self.node_name not in graph:
            return None
        node = graph.nodes[self.node_name].get("node")
        if node is None or getattr(node, "stateGroup", None) is None:
            return None
        return node

    def _push_to_node_process(self, params):
        """Send NodeCtrlUpdate to a running NodeProcess so its ctrl window updates.

        The broker forwards the message only when a NodeProcess is alive for this node.
        The NodeProcess applies setState with blockSignals so no checkpoint echoes back.
        """
        try:
            msg = fcMsgs.NodeCtrlUpdate(self.node_name, params)
            self.chart.sendToBroker(self.node_name, msg)
        except Exception as e:
            logger.debug("PvCtrlServer NodeCtrlUpdate send error for %s: %s", self.node_name, e)


class _ApplyHandler:
    """PUT/RPC handler for the apply trigger PV.

    Like _CtrlPutHandler, called on a p4p worker thread.  The client is answered at
    once; applyClicked() is posted to the Qt main thread (blocking here would hold up
    every other PV, which share one p4p thread).
    """

    def __init__(self, ctrl_widget, dispatcher):
        self.ctrl_widget = ctrl_widget
        self.dispatcher = dispatcher

    def put(self, pv, op):
        try:
            pv.post(0)
            op.done()
            self.dispatcher.post(self.ctrl_widget.applyClicked)
        except Exception as e:
            logger.error("PvCtrlServer apply PUT error: %s", e)
            op.done(error=str(e))

    def rpc(self, pv, op):
        try:
            op.done()
            self.dispatcher.post(self.ctrl_widget.applyClicked)
        except Exception as e:
            logger.error("PvCtrlServer apply RPC error: %s", e)
            op.done(error=str(e))


class _SharedPVHandler:
    """Thin wrapper that holds both a put and an rpc callable, matching p4p's handler protocol."""

    def __init__(self, put=None, rpc=None):
        self._put = put
        self._rpc = rpc

    def put(self, pv, op):
        if self._put is not None:
            self._put(pv, op)

    def rpc(self, pv, op):
        if self._rpc is not None:
            self._rpc(pv, op)


class PvCtrlServer:
    """
    Hosts writable EPICS PVs (PVAccess) for all uiTemplate ctrl parameters of every
    parameterised node in the flowchart graph.

    PV naming::

        {prefix}:ctrl:{graph_name}:{NodeName.instance}:{param_name}
        {prefix}:ctrl:{graph_name}:apply

    where ``prefix = "{hutch}:ami"`` when hutch is set, otherwise ``"ami"``.

    Grouped uiTemplate fields use ``{group}__{param}`` as the final PV name component.

    Workflow
    --------
    1. Write to one or more param PVs — the GUI ctrl widgets update and the Apply
       button highlights green, but the running graph is *not* changed yet.
    2. Write any value to the ``apply`` PV (or issue a PVA RPC call on it) to fire
       ``applyClicked()`` and push the new parameters to the running graph.
    """

    def __init__(self, hutch, graph_name, ctrl_widget, dispatcher=None):
        self.dispatcher = dispatcher if dispatcher is not None else QtDispatcher()
        self.prefix = f"{hutch}:ami" if hutch else "ami"
        self.graph_name = graph_name
        self.ctrl_widget = ctrl_widget
        self.chart = ctrl_widget.chart
        self.provider = None
        self.server = None
        self.pvs = {}  # {full_pv_name: SharedPV}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self.provider = StaticProvider(f"ami_ctrl_{self.graph_name}")
        self.server = Server(providers=[self.provider])
        logger.info(
            "PvCtrlServer started — base prefix: %s:ctrl:%s",
            self.prefix,
            self.graph_name,
        )

    def stop(self):
        if self.server is not None:
            self.server.stop()
            self.server = None
        self.pvs.clear()
        logger.info("PvCtrlServer stopped")

    # ------------------------------------------------------------------
    # Public update methods (called from FlowchartCtrlWidget)
    # ------------------------------------------------------------------

    def update_pvs(self, chart):
        """Diff the current node set against hosted PVs; create/update/remove as needed.

        Called at the end of every ``applyClicked()``.
        """
        if self.provider is None:
            return

        wanted = {}  # {pv_name: (node, param, group, ptype, opts)}
        for node_name, node in chart._graph.nodes(data="node"):
            if node is None:
                continue
            if not hasattr(node, "stateGroup") or node.stateGroup is None:
                continue
            for param, group, ptype, opts in self._iter_node_params(node):
                pv_name = self._param_pv_name(node_name, param, group)
                wanted[pv_name] = (node, param, group, ptype, opts)

        apply_name = self._apply_pv_name()

        # Remove PVs for deleted nodes
        for pv_name in list(self.pvs.keys()):
            if pv_name == apply_name:
                continue
            if pv_name not in wanted:
                self.provider.remove(pv_name)
                del self.pvs[pv_name]
                logger.debug("Removed ctrl PV: %s", pv_name)

        # Create new PVs or post updated values to existing ones
        for pv_name, (node, param, group, ptype, opts) in wanted.items():
            cur_val = self._current_value(node, param, group)
            if cur_val is None:
                continue
            nt = NTScalar(_TYPE_TO_NT[ptype])
            if pv_name not in self.pvs:
                handler = _CtrlPutHandler(node_name, param, group, ptype, opts, self.chart, self.dispatcher)
                pv = SharedPV(nt=nt, initial=cur_val, handler=_SharedPVHandler(put=handler.put))
                self.provider.add(pv_name, pv)
                self.pvs[pv_name] = pv
                logger.debug("Created ctrl PV: %s = %r", pv_name, cur_val)
            else:
                self.pvs[pv_name].post(cur_val)

        # Create the apply PV once any parameterised node exists
        if apply_name not in self.pvs and wanted:
            apply_handler = _ApplyHandler(self.ctrl_widget, self.dispatcher)
            apply_pv = SharedPV(
                nt=NTScalar("i"),
                initial=0,
                handler=_SharedPVHandler(put=apply_handler.put, rpc=apply_handler.rpc),
            )
            self.provider.add(apply_name, apply_pv)
            self.pvs[apply_name] = apply_pv
            logger.debug("Created apply PV: %s", apply_name)
        elif apply_name in self.pvs and not wanted:
            # All parameterised nodes removed — tear down the apply PV too
            self.provider.remove(apply_name)
            del self.pvs[apply_name]

    def push_pv_values(self, node):
        """Post current ctrl values to PVs so EPICS readers stay in sync with the GUI.

        Called on ``sigNodeChanged`` with the specific node that changed.
        Only that node's PVs are updated — ``update_pvs`` handles the full
        graph when Apply is clicked.
        """
        if self.provider is None or node is None:
            return
        if not hasattr(node, "stateGroup") or node.stateGroup is None:
            return
        node_name = node.name()
        for param, group, _ptype, _opts in self._iter_node_params(node):
            pv_name = self._param_pv_name(node_name, param, group)
            if pv_name not in self.pvs:
                continue
            val = self._current_value(node, param, group)
            if val is not None:
                self.pvs[pv_name].post(val)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _param_pv_name(self, node_name, param, group=None):
        parts = [self.prefix, "ctrl", self.graph_name, node_name]
        parts.append(f"{group}__{param}" if group else param)
        return ":".join(parts)

    def _apply_pv_name(self):
        return ":".join([self.prefix, "ctrl", self.graph_name, "apply"])

    @staticmethod
    def _iter_node_params(node):
        """Yield ``(param, group_or_None, ptype, opts)`` for each exposable ctrl field."""
        ui_template = getattr(node.__class__, "uiTemplate", None)
        if not ui_template:
            return
        for entry in ui_template:
            if len(entry) == 2:
                k, t = entry
                o = {}
            elif len(entry) == 3:
                k, t, o = entry
            else:
                continue
            if t in _SKIP_TYPES or t not in _TYPE_TO_NT:
                continue
            yield k, o.get("group"), t, o

    @staticmethod
    def _current_value(node, param, group):
        if group:
            return node.values.get(group, {}).get(param)
        return node.values.get(param)
