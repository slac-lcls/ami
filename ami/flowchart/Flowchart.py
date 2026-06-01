# -*- coding: utf-8 -*-
from collections import OrderedDict, defaultdict
from datetime import datetime

from pyqtgraph import FileDialog
from pyqtgraph import dockarea as dockarea
from pyqtgraph.debug import printExc
from qtpy import QtCore, QtGui, QtWidgets

from ami import LogConfig
from ami.asyncqt import asyncSlot
from ami.client import flowchart_messages as fcMsgs
from ami.comm import AsyncGraphCommHandler
from ami.flowchart.FlowchartGraphicsView import ViewManager
from ami.flowchart.library import LIBRARY
from ami.flowchart.library.common import CtrlNode, SourceNode
from ami.flowchart.library.Editors import STYLE
from ami.flowchart.Node import Node, NodeGraphicsItem, find_nearest
from ami.flowchart.NodeLibrary import SourceLibrary
from ami.flowchart.SourceConfiguration import SourceConfiguration
from ami.flowchart.SubgraphLibrary import SubgraphLibrary, SubgraphTemplate
from ami.flowchart.SubgraphNode import SubgraphNode
from ami.flowchart.Terminal import ConnectionItem, Terminal, TerminalGraphicsItem
from ami.flowchart.TypeEncoder import TypeEncoder

try:
    from qtconsole.inprocess import QtInProcessKernelManager
    from qtconsole.rich_jupyter_widget import RichJupyterWidget

    HAS_QTCONSOLE = True
except ImportError:
    HAS_QTCONSOLE = False

import asyncio
import collections
import itertools as it
import json
import logging
import os
import re
import socket
import subprocess
import tempfile
import typing  # noqa

import amitypes
import networkx as nx
import numpy as np
import prometheus_client as pc
import zmq.asyncio

import ami.flowchart.Editor as EditorTemplate

logger = logging.getLogger(LogConfig.get_package_name(__name__))


class Flowchart(QtCore.QObject):
    sigFileLoaded = QtCore.Signal(object)
    sigFileSaved = QtCore.Signal(object)
    sigNodeCreated = QtCore.Signal(object)
    sigNodeChanged = QtCore.Signal(object)
    # called when output is expected to have changed

    def __init__(
        self,
        name=None,
        filePath=None,
        library=None,
        broker_addr="",
        graphmgr_addr="",
        checkpoint_addr="",
        prometheus_dir=None,
        hutch="",
        configure=False,
    ):
        super().__init__(name)
        self.socks = []
        self.library = library or LIBRARY
        self.graphmgr_addr = graphmgr_addr
        self.source_library = None

        self.ctx = zmq.asyncio.Context()
        self.broker = self.ctx.socket(zmq.PUB)  # used to create new node processes
        self.broker.connect(broker_addr)
        self.socks.append(self.broker)

        self.graphinfo = self.ctx.socket(zmq.SUB)
        self.graphinfo.setsockopt_string(zmq.SUBSCRIBE, "")
        self.graphinfo.connect(graphmgr_addr.info)
        self.socks.append(self.graphinfo)

        self.checkpoint = self.ctx.socket(zmq.SUB)  # used to receive ctrlnode updates from processes
        self.checkpoint.setsockopt_string(zmq.SUBSCRIBE, "")
        self.checkpoint.connect(checkpoint_addr)
        self.socks.append(self.checkpoint)

        self.filePath = filePath

        self._graph = nx.MultiDiGraph()
        self._subgraphs = {}  # Track visual-only subgraphs
        self.subgraph_library = SubgraphLibrary()  # Library of subgraph templates

        self.nextZVal = 10
        self._widget = None

        self.deleted_nodes = []

        self.prometheus_dir = prometheus_dir
        self.hutch = hutch

        self.configure = configure

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        for sock in self.socks:
            sock.close(linger=0)
        if self._widget is not None:
            self._widget.graphCommHandler.close()
        self.ctx.term()

    def start_prometheus(self, port):
        while True:
            try:
                pc.start_http_server(port)
                break
            except OSError:
                port += 1

        if self.prometheus_dir:
            if not os.path.exists(self.prometheus_dir):
                os.makedirs(self.prometheus_dir)
            pth = f"drpami_{socket.gethostname()}_{self.hutch}_client.json"
            pth = os.path.join(self.prometheus_dir, pth)
            conf = [{"targets": [f"{socket.gethostname()}:{port}"]}]
            try:
                with open(pth, "w") as f:
                    json.dump(conf, f)
            except PermissionError:
                logging.error("Permission denied: %s", pth)
                pass

    def setLibrary(self, lib):
        self.library = lib
        self.widget().chartWidget.buildMenu()

    def nodes(self, **kwargs):
        return self._graph.nodes(**kwargs)

    def createNode(self, nodeType=None, name=None, pos=None, prompt=False):
        """Create a new Node and add it to this flowchart."""
        if name is None:
            n = 0
            while True:
                name = "%s.%d" % (nodeType, n)
                if name not in self._graph.nodes():
                    break
                n += 1

        # create an instance of the node
        node = self.library.getNodeType(nodeType)(name)
        self.addNode(node, pos)
        if prompt:
            node.onCreate()
        return node

    def addNode(self, node, pos=None):
        """Add an existing Node to this flowchart.

        See also: createNode()
        """
        if pos is None:
            pos = [0, 0]
        if type(pos) in [QtCore.QPoint, QtCore.QPointF]:
            pos = [pos.x(), pos.y()]
        item = node.graphicsItem()
        item.setZValue(self.nextZVal * 2)
        self.nextZVal += 1
        self.viewBox().addItem(item)
        pos = (find_nearest(pos[0]), find_nearest(pos[1]))
        item.moveBy(*pos)
        subset = 1
        mod = node.__module__.split(".")[-1]
        if mod == "common" and isinstance(node, SourceNode):
            subset = 0
        elif mod == "Display":
            subset = 2
        # Don't add visual-only nodes (like SubgraphNode) to self._graph
        if not getattr(node, "is_visual_only", False):
            self._graph.add_node(node.name(), node=node, subset=subset)
        node.sigClosed.connect(self.nodeClosed)
        node.sigTerminalConnected.connect(self.nodeTermConnected)
        node.sigTerminalDisconnected.connect(self.nodeTermDisconnected)
        node.sigNodeEnabled.connect(self.nodeEnabled)
        node.sigNodeLatched.connect(self.nodeLatched)
        node.sigTerminalOptional.connect(self.nodeTermOptional)
        node.sigTerminalAdded.connect(self.nodeTermAdded)
        node.sigTerminalRemoved.connect(self.nodeTermRemoved)
        node.sigLabelChanged.connect(self.nodeLabelChanged)
        node.setGraph(self._graph)

        # if the node is a source, connect the source kwargs interface to the manager
        if node.isSource():
            node.graphicsItem().sigSourceKwargs.connect(self.send_requested_data)

        self.sigNodeCreated.emit(node)
        if node.isChanged(True, True):
            self.sigNodeChanged.emit(node)

        # If we're currently viewing a subgraph, register this node with it
        if self._widget and not getattr(node, "is_visual_only", False):
            vm = self.viewManager()
            sg_name = vm._currentSubgraphName
            if sg_name and sg_name in self._subgraphs:
                sg_data = self._subgraphs[sg_name]
                if node.name() not in sg_data["nodes"]:
                    sg_data["nodes"].append(node.name())
                placeholder = sg_data["placeholder"]
                if node not in placeholder.children:
                    placeholder.children.append(node)

    def replaceSourceNode(self, old_node, replacement_source_name):
        """
        Replace a source node with a different source.

        If replacement source already exists, merge connections into it.
        Otherwise, create new node with replacement source.

        Args:
            old_node: The SourceNode to replace
            replacement_source_name: Name of the replacement source
        """
        # Get the outgoing connections from old node
        old_terminal = old_node.terminals["Out"]
        connections_to_transfer = list(old_terminal.connections().keys())

        # Check if replacement already exists
        if replacement_source_name in self._graph.nodes():
            # Merge: get existing node and transfer connections
            new_node = self._graph.nodes[replacement_source_name]["node"]
            new_terminal = new_node.terminals["Out"]

            # Transfer connections
            for remote_term in connections_to_transfer:
                # Disconnect from old
                old_terminal.disconnectFrom(remote_term)
                # Connect to new (if not already connected)
                if not new_terminal.connectedTo(remote_term):
                    new_terminal.connectTo(remote_term)

            # Remove old node
            old_node.close()

        else:
            # Create new node at same position
            pos = old_node.graphicsItem().pos()
            node_type = self.source_library.getSourceType(replacement_source_name)

            new_node = SourceNode(
                name=replacement_source_name, terminals={"Out": {"io": "out", "ttype": node_type}}, flowchart=self
            )

            self.addNode(node=new_node, pos=[pos.x(), pos.y()])
            new_terminal = new_node.terminals["Out"]

            # Transfer connections
            for remote_term in connections_to_transfer:
                # Disconnect from old
                old_terminal.disconnectFrom(remote_term)
                # Connect to new
                new_terminal.connectTo(remote_term)

            # Remove old node
            old_node.close()

    def _create_subgraph_scaffold(self, name, nodes, pos=None):
        """Create the subgraph placeholder and dedicated view.

        Args:
            name: Name for the subgraph
            nodes: List of nodes that will be in the subgraph
            pos: Position for placeholder (optional)

        Returns:
            (subgraph_node, view): Tuple of SubgraphNode placeholder and FlowchartGraphicsView
        """
        # Create view for this subgraph
        view = self.viewManager().addView(name)

        # Create SubgraphNode placeholder (visual only, not in self._graph)
        subgraphNode = SubgraphNode(name, children=nodes, flowchart=self)
        subgraphNode.sigClosed.connect(self.nodeClosed)
        subgraphNode.setGraph(self._graph)

        # Switch to root view to ensure placeholder is added correctly
        self.viewManager().displayView(name="root")

        # Add placeholder to root view
        placeholder_item = subgraphNode.graphicsItem()
        self.viewBox().addItem(placeholder_item)

        # Position the placeholder
        if pos:
            if isinstance(pos, QtCore.QPointF):
                # Snap to grid
                snapped_pos = (find_nearest(pos.x()), find_nearest(pos.y()))
                placeholder_item.moveBy(*snapped_pos)
            elif isinstance(pos, (list, tuple)):
                # Snap to grid
                snapped_pos = (find_nearest(pos[0]), find_nearest(pos[1]))
                placeholder_item.moveBy(*snapped_pos)
            else:
                placeholder_item.moveBy(*pos)
        elif nodes:
            # Default position based on first node
            first_pos = nodes[0].graphicsItem().pos()
            snapped_pos = (find_nearest(first_pos.x()), find_nearest(first_pos.y()))
            placeholder_item.moveBy(*snapped_pos)

        return subgraphNode, view

    def _move_items_to_subgraph_view(self, nodes, view):
        """Move nodes and their internal connections to the subgraph view.

        Args:
            nodes: List of nodes to move
            view: Target FlowchartGraphicsView

        Returns:
            List of internal ConnectionItems that were moved
        """
        internal_connections = []

        # Move nodes to subgraph view
        for node in nodes:
            # Remove from root view scene (this automatically removes it)
            item = node.graphicsItem()
            if item.scene() is not None:
                item.scene().removeItem(item)

            # Add to subgraph view (will be visible there)
            view.viewBox().addItem(item)

            # Find internal connections (both endpoints inside subgraph)
            for term_name, term in node.terminals.items():
                for remote_term, conn_item in term.connections().items():
                    remote_node = remote_term.node()
                    if remote_node in nodes:
                        # This is an internal connection - move to subgraph view
                        if conn_item not in internal_connections:
                            internal_connections.append(conn_item)

            node.recolor()

        # Move internal connections to subgraph view
        for conn in internal_connections:
            if conn.scene() is not None:
                conn.scene().removeItem(conn)
            view.viewBox().addItem(conn)

        return internal_connections

    def _commit_subgraph(
        self, name, subgraphNode, view, nodes, internal_connections, boundary_connections, description
    ):
        """Register the newly created subgraph in the flowchart's metadata.

        Args:
            name: Name of the subgraph
            subgraphNode: The SubgraphNode placeholder
            view: The FlowchartGraphicsView for the subgraph
            nodes: List of Node objects in the subgraph
            internal_connections: List of ConnectionItems that are internal
            boundary_connections: List of boundary connection dicts
            description: Description text for the subgraph
        """
        # Convert nodes to names
        if nodes and isinstance(nodes[0], str):
            names = nodes
        else:
            names = list(map(lambda node: node.name(), nodes))

        # Store subgraph metadata
        self._subgraphs[name] = {
            "nodes": names,
            "placeholder": subgraphNode,
            "view": view,
            "boundary_connections": boundary_connections,
            "internal_connections": internal_connections,
            "description": description or "",
        }

        # Set tooltip on placeholder to show description
        if description:
            subgraphNode.graphicsItem().setToolTip(description)

        # Add to library
        self._addSubgraphToLibrary(name)

    def moveNodeToSubgraph(self, node_name, subgraph_name):
        """Move a node from root view into an existing subgraph.

        Handles:
        - Moving node graphics item to subgraph view
        - Converting external→node edges to boundary input terminals
        - Converting node→external edges to boundary output terminals
        - Converting previously-boundary edges that become internal

        Args:
            node_name: Name of node to move (must be in root view)
            subgraph_name: Target subgraph name

        Returns:
            Dict with lists of new boundary terminals: {"inputs": [...], "outputs": [...]}
        """
        graph = self._graph
        sg_data = self._subgraphs[subgraph_name]
        subgraphNode = sg_data["placeholder"]
        sg_view = sg_data["view"]
        root_view = self.viewManager().views["root"]
        node_names_in_sg = sg_data["nodes"]

        node_obj = graph.nodes[node_name]["node"]

        # Categorize all edges involving this node
        new_inputs = []  # external → this node (need new boundary input)
        new_outputs = []  # this node → external (need new boundary output)
        internal_from = []  # sg node → this node (was boundary output, becomes internal)
        internal_to = []  # this node → sg node (was boundary input, becomes internal)

        for pred, _, data in graph.in_edges(node_name, data=True):
            if pred in node_names_in_sg:
                internal_from.append((pred, data))
            else:
                new_inputs.append((pred, data))

        for _, succ, data in graph.out_edges(node_name, data=True):
            if succ in node_names_in_sg:
                internal_to.append((succ, data))
            else:
                new_outputs.append((succ, data))

        new_terminals = {"inputs": [], "outputs": []}

        # --- Handle edges from sg nodes → this node (were boundary outputs, now internal) ---
        for pred, data in internal_from:
            terminal_name = f"{pred}.{data['from_term']}"
            # If a boundary output terminal exists for this edge, remove it
            if terminal_name in subgraphNode.outputs():
                pred_node = graph.nodes[pred]["node"]
                pred_term = pred_node.terminals[data["from_term"]]
                node_term = node_obj.terminals[data["to_term"]]
                # Disconnect visual: placeholder → this node (root view)
                placeholder_term = subgraphNode.terminals[terminal_name]
                for remote in list(placeholder_term.dependentTerms()):
                    if remote.node() is node_obj:
                        placeholder_term.disconnectFrom(remote, signal=False)
                # Disconnect SubgraphOutput → pred (subgraph view)
                sg_output_term = subgraphNode.subgraphOutputs.terminals.get(terminal_name)
                if sg_output_term:
                    for remote in list(sg_output_term.inputTerminals()):
                        if remote.node() is pred_node:
                            remote.disconnectFrom(sg_output_term, signal=False)
                # Remove boundary terminal if no other external targets remain
                still_external = any(
                    bc
                    for bc in sg_data["boundary_connections"]
                    if bc["terminal_name"] == terminal_name
                    and bc["type"] == "output"
                    and bc["external_node"] is not node_obj
                )
                if not still_external:
                    subgraphNode.removeTerminal(terminal_name)
                # Create direct visual in subgraph view
                pred_term.connectTo(node_term, signal=False, view=sg_view.viewBox())
                # Remove from boundary_connections
                sg_data["boundary_connections"] = [
                    bc
                    for bc in sg_data["boundary_connections"]
                    if not (
                        bc["terminal_name"] == terminal_name
                        and bc["type"] == "output"
                        and bc["external_node"] is node_obj
                    )
                ]

        # --- Handle edges this node → sg nodes (were boundary inputs, now internal) ---
        for succ, data in internal_to:
            terminal_name = f"{node_name}.{data['from_term']}"
            if terminal_name in subgraphNode.inputs():
                succ_node = graph.nodes[succ]["node"]
                node_term = node_obj.terminals[data["from_term"]]
                succ_term = succ_node.terminals[data["to_term"]]
                # Disconnect visual: this node → placeholder (root view)
                placeholder_term = subgraphNode.terminals[terminal_name]
                for remote in list(placeholder_term.inputTerminals()):
                    if remote.node() is node_obj:
                        remote.disconnectFrom(placeholder_term, signal=False)
                # Disconnect SubgraphInput → succ (subgraph view)
                sg_input_term = subgraphNode.subgraphInputs.terminals.get(terminal_name)
                if sg_input_term:
                    for remote in list(sg_input_term.dependentTerms()):
                        if remote.node() is succ_node:
                            sg_input_term.disconnectFrom(remote, signal=False)
                # Remove boundary terminal
                subgraphNode.removeTerminal(terminal_name)
                # Create direct visual in subgraph view
                node_term.connectTo(succ_term, signal=False, view=sg_view.viewBox())
                sg_data["boundary_connections"] = [
                    bc
                    for bc in sg_data["boundary_connections"]
                    if not (bc["terminal_name"] == terminal_name and bc["type"] == "input")
                ]

        # --- Move node graphics to subgraph view ---
        item = node_obj.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)
        sg_view.viewBox().addItem(item)

        # --- Handle new input boundaries (external → this node) ---
        for pred, data in new_inputs:
            terminal_name = f"{pred}.{data['from_term']}"
            ext_node = graph.nodes[pred]["node"]
            ext_term = ext_node.terminals[data["from_term"]]
            int_term = node_obj.terminals[data["to_term"]]

            # Remove old visual connection (root view)
            ext_term.disconnectFrom(int_term, signal=False)

            if terminal_name not in subgraphNode.inputs():
                # Create boundary terminal (also wires external → placeholder)
                subgraphNode.graphicsItem().addInput(terminal_name, ext_term)
                new_terminals["inputs"].append(terminal_name)

            # Wire SubgraphInput → this node (subgraph view)
            sg_input_term = subgraphNode.subgraphInputs.terminals[terminal_name]
            sg_input_term.connectTo(int_term, signal=False, view=sg_view.viewBox())

            sg_data["boundary_connections"].append(
                {
                    "type": "input",
                    "external_node": ext_node,
                    "external_term": ext_term,
                    "internal_node": node_obj,
                    "internal_term": int_term,
                    "terminal_name": terminal_name,
                }
            )

        # --- Handle new output boundaries (this node → external) ---
        for succ, data in new_outputs:
            terminal_name = f"{node_name}.{data['from_term']}"
            int_term = node_obj.terminals[data["from_term"]]
            ext_node = graph.nodes[succ]["node"]
            ext_term = ext_node.terminals[data["to_term"]]

            # Remove old visual connection (root view)
            int_term.disconnectFrom(ext_term, signal=False)

            if terminal_name not in subgraphNode.outputs():
                subgraphNode.graphicsItem().addOutput(terminal_name, int_term)
                new_terminals["outputs"].append(terminal_name)

            # Wire placeholder → external (root view)
            placeholder_out_term = subgraphNode.terminals[terminal_name]
            placeholder_out_term.connectTo(ext_term, signal=False, view=root_view.viewBox())

            sg_data["boundary_connections"].append(
                {
                    "type": "output",
                    "external_node": ext_node,
                    "external_term": ext_term,
                    "internal_node": node_obj,
                    "internal_term": int_term,
                    "terminal_name": terminal_name,
                }
            )

        # --- Update subgraph tracking ---
        sg_data["nodes"].append(node_name)
        subgraphNode.children.append(node_obj)

        # --- Update graphics ---
        subgraphNode.graphicsItem().updateTerminals()
        if subgraphNode.subgraphInputs.graphicsItem().scene() is not None:
            subgraphNode.subgraphInputs.graphicsItem().updateTerminals()
        if subgraphNode.subgraphOutputs.graphicsItem().scene() is not None:
            subgraphNode.subgraphOutputs.graphicsItem().updateTerminals()

        return new_terminals

    def makeSubgraphFromSelection(self, nodes=None, name=None, pos=None, description=None):
        """Create a visual-only subgraph from selected nodes.

        This creates a visual grouping without modifying self._graph.
        Nodes are moved to a separate view, and a placeholder appears in root view.

        Args:
            nodes: List of nodes to include
            name: Name for the subgraph (if None, prompts user)
            pos: Position for placeholder
            description: Description for the subgraph (if None, prompts user)
        """
        graph = self._graph

        # Generate default name if not provided
        if name is None:
            default_name = self._generateUniqueSubgraphName("subgraph")
        else:
            default_name = name

        # Show dialog for name and description
        if name is None or description is None:
            name, description = self._showExportDialog(default_name, "", isImport=False)
            if not name:
                # User cancelled
                return None

        # Filter out SourceNodes - sources always stay external to subgraphs
        nodes = [n for n in nodes if not isinstance(n, SourceNode)]

        if not nodes:
            logger.warning("No non-source nodes selected for subgraph")
            return None

        # Step 1: Create subgraph scaffold (placeholder and view)
        subgraphNode, view = self._create_subgraph_scaffold(name, nodes, pos)

        names = list(map(lambda node: node.name(), nodes))

        # Analyze connections to find boundary crossings
        boundary_connections = []
        input_pos = None
        output_pos = None
        inputs = set()
        outputs = set()

        # Find input boundary connections (connections coming INTO the subgraph)
        for fnode_name, tnode_name, data in graph.in_edges(names, data=True):
            # Skip internal connections
            if fnode_name in names and tnode_name in names:
                continue

            # This is a boundary connection
            external_node = graph.nodes[fnode_name]["node"]
            internal_node = graph.nodes[tnode_name]["node"]
            external_term = external_node.terminals[data["from_term"]]
            internal_term = internal_node.terminals[data["to_term"]]

            # Create unique terminal name
            terminal_name = ".".join([fnode_name, data["from_term"]])

            # Track unique inputs
            if terminal_name not in inputs:
                # Add input terminal to placeholder
                subgraphNode.addInput(name=terminal_name, ttype=external_term.type())
                inputs.add(terminal_name)

                if input_pos is None:
                    input_pos = external_node.graphicsItem().pos()

            # Store boundary connection info
            boundary_connections.append(
                {
                    "type": "input",
                    "external_node": external_node,
                    "external_term": external_term,
                    "internal_node": internal_node,
                    "internal_term": internal_term,
                    "terminal_name": terminal_name,
                }
            )

        # Find output boundary connections (connections going OUT of the subgraph)
        for fnode_name, tnode_name, data in graph.out_edges(names, data=True):
            # Skip internal connections
            if fnode_name in names and tnode_name in names:
                continue

            # This is a boundary connection
            internal_node = graph.nodes[fnode_name]["node"]
            external_node = graph.nodes[tnode_name]["node"]
            internal_term = internal_node.terminals[data["from_term"]]
            external_term = external_node.terminals[data["to_term"]]

            # Create unique terminal name
            terminal_name = ".".join([fnode_name, data["from_term"]])

            # Track unique outputs
            if terminal_name not in outputs:
                # Add output terminal to placeholder
                subgraphNode.addOutput(name=terminal_name, ttype=internal_term.type())
                outputs.add(terminal_name)

                if output_pos is None:
                    output_pos = external_node.graphicsItem().pos()

            # Store boundary connection info
            boundary_connections.append(
                {
                    "type": "output",
                    "external_node": external_node,
                    "external_term": external_term,
                    "internal_node": internal_node,
                    "internal_term": internal_term,
                    "terminal_name": terminal_name,
                }
            )

        # Position SubgraphInput/Output nodes in subgraph view FIRST
        if inputs and input_pos:
            view.viewBox().addItem(subgraphNode.subgraphInputs.graphicsItem())
            subgraphNode.subgraphInputs.graphicsItem().moveBy(input_pos.x(), input_pos.y())
        if outputs and output_pos:
            view.viewBox().addItem(subgraphNode.subgraphOutputs.graphicsItem())
            subgraphNode.subgraphOutputs.graphicsItem().moveBy(output_pos.x(), output_pos.y())

        # NOW process boundary connections - create visual-only connections
        # Track which root-level visual connections have been made to avoid duplicates.
        # A source terminal connecting to multiple internal nodes shares one placeholder terminal,
        # so the root visual (external → placeholder) only needs to be created once.
        root_visuals_created = {}  # terminal_name -> root_visual ConnectionItem

        for bc in boundary_connections:
            # Disconnect original connection (signal=False preserves _input_vars and graph edges)
            # This frees the input terminal for the new visual connection
            bc["external_term"].disconnectFrom(bc["internal_term"], signal=False)

            # Get the placeholder terminal
            placeholder_term = subgraphNode.terminals[bc["terminal_name"]]

            if bc["type"] == "input":
                # SubgraphInput terminal should have same name as placeholder terminal
                sg_input_term_name = bc["terminal_name"]

                # Check if terminal already exists on SubgraphInputs node
                if sg_input_term_name in subgraphNode.subgraphInputs.terminals:
                    sg_input_term = subgraphNode.subgraphInputs.terminals[sg_input_term_name]
                else:
                    # Only create if it doesn't exist
                    sg_input_term = subgraphNode.subgraphInputs.addOutput(
                        name=sg_input_term_name, ttype=bc["internal_term"].type()
                    )

                # Create visual connection in root view: external → placeholder
                # Only create once per terminal_name (same source may feed multiple internal nodes)
                if bc["terminal_name"] not in root_visuals_created:
                    root_visual = bc["external_term"].connectTo(placeholder_term, signal=False, view=self.viewBox())
                    root_visuals_created[bc["terminal_name"]] = root_visual
                else:
                    root_visual = root_visuals_created[bc["terminal_name"]]

                # Create visual connection in subgraph view: subgraph_input → internal
                sg_visual = sg_input_term.connectTo(bc["internal_term"], signal=False, view=view.viewBox())

            else:  # output
                # SubgraphOutput terminal should have same name as placeholder terminal
                sg_output_term_name = bc["terminal_name"]

                # Check if terminal already exists on SubgraphOutputs node
                if sg_output_term_name in subgraphNode.subgraphOutputs.terminals:
                    sg_output_term = subgraphNode.subgraphOutputs.terminals[sg_output_term_name]
                else:
                    # Only create if it doesn't exist
                    sg_output_term = subgraphNode.subgraphOutputs.addInput(
                        name=sg_output_term_name, ttype=bc["internal_term"].type()
                    )

                # Create visual connection in root view: placeholder → external
                # Only create once per terminal_name (same internal output may feed multiple externals)
                if bc["terminal_name"] not in root_visuals_created:
                    root_visual = placeholder_term.connectTo(bc["external_term"], signal=False, view=self.viewBox())
                    root_visuals_created[bc["terminal_name"]] = root_visual
                else:
                    root_visual = root_visuals_created[bc["terminal_name"]]

                # Create visual connection in subgraph view: internal → subgraph_output
                sg_visual = bc["internal_term"].connectTo(sg_output_term, signal=False, view=view.viewBox())

            # Store visual connection references
            bc["root_visual"] = root_visual
            bc["subgraph_visual"] = sg_visual

        # Step 2: Move nodes and internal connections to subgraph view
        internal_connections = self._move_items_to_subgraph_view(nodes, view)

        # Step 3: Commit the subgraph (store metadata and add to library)
        self._commit_subgraph(name, subgraphNode, view, nodes, internal_connections, boundary_connections, description)

        # Display the subgraph view
        self.viewManager().displayView(name=subgraphNode.name(), autoRange=True)

    def _showExportDialog(self, default_name, default_desc="", isImport=False):
        """Show dialog for entering subgraph name and description

        Returns:
            (name, description) tuple, or (None, None) if cancelled
        """
        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Import Subgraph" if isImport else "Export Subgraph")

        layout = QtWidgets.QVBoxLayout()

        # Name field
        name_label = QtWidgets.QLabel("Name:")
        name_edit = QtWidgets.QLineEdit(default_name)
        layout.addWidget(name_label)
        layout.addWidget(name_edit)

        # Description field
        desc_label = QtWidgets.QLabel("Description:")
        desc_edit = QtWidgets.QTextEdit()
        desc_edit.setPlainText(default_desc)
        desc_edit.setMaximumHeight(100)
        layout.addWidget(desc_label)
        layout.addWidget(desc_edit)

        # Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            return name_edit.text(), desc_edit.toPlainText()
        else:
            return None, None

    def _generateUniqueSubgraphName(self, base_name):
        """Generate unique subgraph name

        Args:
            base_name: Base name for the subgraph

        Returns:
            Unique name that doesn't conflict with existing subgraphs
        """
        if base_name not in self._subgraphs:
            return base_name

        n = 0
        while True:
            name = f"{base_name}.{n}"
            if name not in self._subgraphs:
                return name
            n += 1

    def _generateUniqueNodeName(self, base_name):
        """Generate unique node name

        Args:
            base_name: Base name for the node

        Returns:
            Unique name that doesn't conflict with existing nodes
        """
        if base_name not in self._graph.nodes():
            return base_name

        n = 0
        while True:
            name = f"{base_name}.{n}"
            if name not in self._graph.nodes():
                return name
            n += 1

    def _createSubgraphFromImport(
        self, name, nodes, boundary_inputs, boundary_outputs, node_mapping, pos=None, description=None
    ):
        """Create a subgraph from imported nodes and boundary metadata.

        This creates a VISUAL-ONLY subgraph structure. Helper nodes are visual-only
        and do NOT participate in graph execution. Actual graph edges are created later
        when the user makes runtime connections (via Phase 3 logic in nodeTermConnected).

        Args:
            name: Unique name for the subgraph
            nodes: List of already-restored Node objects
            boundary_inputs: List of dicts with boundary input metadata from .fc file
            boundary_outputs: List of dicts with boundary output metadata from .fc file
            node_mapping: Dict mapping old node names to new node names (for remapping)
            pos: Position for placeholder in root view (optional)
            description: Subgraph description (optional)
        """

        # Step 1: Create subgraph scaffold (placeholder and view)
        subgraphNode, view = self._create_subgraph_scaffold(name, nodes, pos)

        # Move restored nodes (and their internal connections) from root to subgraph view
        self._move_items_to_subgraph_view(nodes, view)

        # Switch to subgraph view for creating helper nodes
        self.viewManager().displayView(name=name)

        # Step 2: Create placeholder terminals and track boundary connections
        boundary_connections = []

        # Process boundary inputs
        for boundary_input in boundary_inputs:
            term_name = boundary_input["placeholder_terminal"]

            # Parse ttype (might be string representation)
            ttype_str = boundary_input["ttype"]
            ttype = eval(ttype_str) if isinstance(ttype_str, str) else ttype_str

            # Add input terminal to placeholder (also creates SubgraphInput terminal)
            subgraphNode.addInput(name=term_name, ttype=ttype)
            sg_input_term = subgraphNode.subgraphInputs.terminals[term_name]

            # Check if this boundary should be visually connected to internal node
            internal_node_name = boundary_input.get("internal_node")
            internal_term_name = boundary_input.get("internal_terminal")

            if internal_node_name and internal_term_name:
                # Remap old node name to new node name
                if internal_node_name not in node_mapping:
                    logger.warning(f"Boundary input references unknown node {internal_node_name}")
                    continue

                new_node_name = node_mapping[internal_node_name]

                if new_node_name not in self._graph.nodes:
                    logger.warning(f"Remapped node {new_node_name} not in graph")
                    continue

                internal_node = self._graph.nodes[new_node_name]["node"]

                # Validate terminal exists
                if internal_term_name not in internal_node.terminals:
                    logger.warning(f"Node {new_node_name} missing terminal {internal_term_name}")
                    continue

                internal_term = internal_node.terminals[internal_term_name]

                # Store boundary connection info (will create visual connection later)
                boundary_connections.append(
                    {
                        "type": "input",
                        "terminal_name": term_name,
                        "internal_node": internal_node,
                        "internal_term": internal_term,
                    }
                )

        # Process boundary outputs (similar to inputs)
        for boundary_output in boundary_outputs:
            term_name = boundary_output["placeholder_terminal"]
            ttype_str = boundary_output["ttype"]
            ttype = eval(ttype_str) if isinstance(ttype_str, str) else ttype_str

            # Add output terminal to placeholder (also creates SubgraphOutput terminal)
            subgraphNode.addOutput(name=term_name, ttype=ttype)
            sg_output_term = subgraphNode.subgraphOutputs.terminals[term_name]

            internal_node_name = boundary_output.get("internal_node")
            internal_term_name = boundary_output.get("internal_terminal")

            if internal_node_name and internal_term_name:
                if internal_node_name not in node_mapping:
                    logger.warning(f"Boundary output references unknown node {internal_node_name}")
                    continue

                new_node_name = node_mapping[internal_node_name]

                if new_node_name not in self._graph.nodes:
                    logger.warning(f"Remapped node {new_node_name} not in graph")
                    continue

                internal_node = self._graph.nodes[new_node_name]["node"]

                if internal_term_name not in internal_node.terminals:
                    logger.warning(f"Node {new_node_name} missing terminal {internal_term_name}")
                    continue

                internal_term = internal_node.terminals[internal_term_name]

                # Store boundary connection info (will create visual connection later)
                boundary_connections.append(
                    {
                        "type": "output",
                        "terminal_name": term_name,
                        "internal_node": internal_node,
                        "internal_term": internal_term,
                    }
                )

        # Step 3: Add helper nodes to subgraph view
        if subgraphNode.inputs():
            view.viewBox().addItem(subgraphNode.subgraphInputs.graphicsItem())
            # Position to the left
            if nodes:
                leftmost_x = min(node.graphicsItem().pos().x() for node in nodes)
                first_y = nodes[0].graphicsItem().pos().y()
                subgraphNode.subgraphInputs.graphicsItem().setPos(leftmost_x - 200, first_y)
            else:
                subgraphNode.subgraphInputs.graphicsItem().setPos(0, 0)

        if subgraphNode.outputs():
            view.viewBox().addItem(subgraphNode.subgraphOutputs.graphicsItem())
            # Position to the right
            if nodes:
                rightmost_x = max(node.graphicsItem().pos().x() for node in nodes)
                first_y = nodes[0].graphicsItem().pos().y()
                subgraphNode.subgraphOutputs.graphicsItem().setPos(rightmost_x + 200, first_y)
            else:
                subgraphNode.subgraphOutputs.graphicsItem().setPos(500, 500)

        # Update all terminal graphics
        subgraphNode.graphicsItem().updateTerminals()
        if subgraphNode.inputs():
            subgraphNode.subgraphInputs.graphicsItem().updateTerminals()
        if subgraphNode.outputs():
            subgraphNode.subgraphOutputs.graphicsItem().updateTerminals()

        # Step 4: Move nodes and internal connections to subgraph view
        internal_connections = self._move_items_to_subgraph_view(nodes, view)

        # Step 5: Create visual ConnectionItems for boundary connections
        # These are in the subgraph view connecting helpers to internal nodes
        # NOW we can create connections since everything is in the view
        for bc in boundary_connections:
            internal_term = bc["internal_term"]

            if bc["type"] == "input":
                # SubgraphInput → Internal
                sg_input_term = subgraphNode.subgraphInputs.terminals[bc["terminal_name"]]

                # Create visual-only connection (now that nodes are in the view)
                # Use signal=False so it doesn't create graph edges
                # connectTo automatically recolors terminals
                subgraph_visual = sg_input_term.connectTo(internal_term, signal=False)
                bc["subgraph_visual"] = subgraph_visual
            else:  # output
                # Internal → SubgraphOutput
                sg_output_term = subgraphNode.subgraphOutputs.terminals[bc["terminal_name"]]

                # Create visual-only connection (now that nodes are in the view)
                internal_term.connectTo(sg_output_term, signal=False)

                # Get the ConnectionItem that was just created
                conn_item = internal_term.connections().get(sg_output_term)
                if conn_item:
                    bc["subgraph_visual"] = conn_item
                    sg_output_term.recolor(QtGui.QColor(255, 255, 255))

        # Step 6: Commit the subgraph (store metadata and add to library)
        self._commit_subgraph(name, subgraphNode, view, nodes, internal_connections, boundary_connections, description)

        # Switch back to root view - user sees placeholder and can connect it
        self.viewManager().displayView(name="root")

    def exportSubgraph(self, subgraph_name, fileName=None):
        """Export an existing subgraph to a .fc file

        Args:
            subgraph_name: Name of the subgraph in self._subgraphs
            fileName: Path to save file (optional, shows dialog if None)
        """
        if subgraph_name not in self._subgraphs:
            logger.error(f"Subgraph {subgraph_name} not found")
            return

        # Get subgraph data
        sg_data = self._subgraphs[subgraph_name]

        # Show dialog for name/description (prefill with existing description)
        existing_desc = sg_data.get("description", "")
        name, desc = self._showExportDialog(subgraph_name, existing_desc)
        if not name:
            return

        # Show file dialog if no filename provided
        if fileName is None:
            fileName, _ = FileDialog.getSaveFileName(
                self.widget(), "Export Subgraph", f"{name}.fc", "Flowchart files (*.fc)"
            )
            if not fileName:
                return

        # Collect nodes in subgraph
        nodes = []
        for node_name in sg_data["nodes"]:
            if node_name not in self._graph.nodes:
                continue
            node = self._graph.nodes[node_name]["node"]
            nodes.append({"class": type(node).__name__, "name": node_name, "state": node.saveState()})

        # Collect internal connections only
        connects = []
        for from_node, to_node, data in self._graph.edges(data=True):
            if from_node in sg_data["nodes"] and to_node in sg_data["nodes"]:
                connects.append((from_node, data["from_term"], to_node, data["to_term"]))

        # Collect boundary input metadata
        boundary_inputs = []
        sg_placeholder = sg_data["placeholder"]

        # Build mapping of placeholder terminal names to boundary connections
        input_bc_map = {}
        output_bc_map = {}

        for bc in sg_data["boundary_connections"]:
            term_name = bc["terminal_name"]
            if bc["type"] == "input":
                if term_name not in input_bc_map:
                    input_bc_map[term_name] = []
                input_bc_map[term_name].append(bc)
            else:  # output
                if term_name not in output_bc_map:
                    output_bc_map[term_name] = []
                output_bc_map[term_name].append(bc)

        # Export boundary inputs
        for input_term_name in sg_placeholder.inputs():
            placeholder_term = sg_placeholder.terminals[input_term_name]
            ttype = placeholder_term.type()  # Keep as class object - TypeEncoder will serialize it

            # Check if this terminal has boundary connections
            if input_term_name in input_bc_map:
                # Export each boundary connection
                for bc in input_bc_map[input_term_name]:
                    boundary_inputs.append(
                        {
                            "placeholder_terminal": input_term_name,
                            "internal_node": bc["internal_node"].name(),
                            "internal_terminal": bc["internal_term"].name(),
                            "ttype": ttype,
                        }
                    )
            else:
                # No boundary connection - export disconnected
                boundary_inputs.append(
                    {
                        "placeholder_terminal": input_term_name,
                        "internal_node": None,
                        "internal_terminal": None,
                        "ttype": ttype,
                    }
                )

        # Export boundary outputs
        boundary_outputs = []
        for output_term_name in sg_placeholder.outputs():
            placeholder_term = sg_placeholder.terminals[output_term_name]
            ttype = placeholder_term.type()  # Keep as class object - TypeEncoder will serialize it

            if output_term_name in output_bc_map:
                for bc in output_bc_map[output_term_name]:
                    boundary_outputs.append(
                        {
                            "placeholder_terminal": output_term_name,
                            "internal_node": bc["internal_node"].name(),
                            "internal_terminal": bc["internal_term"].name(),
                            "ttype": ttype,
                        }
                    )
            else:
                boundary_outputs.append(
                    {
                        "placeholder_terminal": output_term_name,
                        "internal_node": None,
                        "internal_terminal": None,
                        "ttype": ttype,
                    }
                )

        # Create state dict
        state = {
            "subgraph_metadata": {
                "name": name,
                "description": desc,
                "boundary_inputs": boundary_inputs,
                "boundary_outputs": boundary_outputs,
            },
            "nodes": nodes,
            "connects": connects,
            "views": {"root": sg_data["view"].viewBox().saveState()},
        }

        # Save to file
        with open(fileName, "w") as f:
            json.dump(state, f, indent=2, cls=TypeEncoder)

        if self._widget:
            self.widget().chartWidget.updateStatus(f"Exported subgraph to: {fileName}")

    def importSubgraphFromFile(self, fileName, pos=None):
        """Import a .fc file and create a subgraph instance

        Args:
            fileName: Path to .fc file or state dict
            pos: Position for subgraph placeholder (optional)

        Returns:
            subgraph_name: Name of created subgraph, or None if cancelled
        """
        # Load file or use provided dict
        if isinstance(fileName, str):
            with open(fileName, "r") as f:
                state = json.load(f)
        else:
            state = fileName  # Already a dict

        # Generate unique subgraph name
        base_name = state.get("subgraph_metadata", {}).get("name", "imported")
        if isinstance(fileName, str):
            base_name = base_name or os.path.splitext(os.path.basename(fileName))[0]
        name = self._generateUniqueSubgraphName(base_name)

        # Restore nodes with unique names (will be created in current view)
        node_mapping = {}  # old_name -> new_name
        restored_nodes = []

        # Track skipped sources for boundary derivation
        skipped_sources = {}  # {old_name: {term_name: ttype, ...}}

        for node_state in state.get("nodes", []):
            old_name = node_state.get("name")

            # Skip SourceNodes - they become boundary inputs instead
            if node_state["class"] == "SourceNode":
                terminals = node_state.get("state", {}).get("terminals", {})
                source_terms = {}
                for term_name, term_info in terminals.items():
                    ttype = term_info.get("ttype")
                    if isinstance(ttype, str):
                        ttype = eval(ttype)
                    source_terms[term_name] = ttype
                skipped_sources[old_name] = source_terms
                continue

            new_name = self._generateUniqueNodeName(old_name)

            try:
                node = self.createNode(node_state["class"], name=new_name, prompt=False)

                if node:
                    node_mapping[old_name] = node.name()
                    node.blockSignals(True)
                    node.restoreState(node_state.get("state", {}))
                    node.blockSignals(False)
                    restored_nodes.append(node)
            except Exception:
                printExc(f"Error creating node {old_name}: (continuing anyway)")
                continue

        # Auto-derive boundary inputs from skipped source connections
        auto_boundary_inputs = []
        for conn in state.get("connects", []):
            if len(conn) < 4:
                continue
            from_node, from_term, to_node, to_term = conn[0], conn[1], conn[2], conn[3]

            if from_node in skipped_sources:
                ttype = skipped_sources[from_node].get(from_term)
                placeholder_terminal = f"{from_node}.{from_term}"
                auto_boundary_inputs.append(
                    {
                        "placeholder_terminal": placeholder_terminal,
                        "internal_node": to_node,
                        "internal_terminal": to_term,
                        "ttype": ttype,
                    }
                )

        if skipped_sources:
            logger.info(
                f"Excluded {len(skipped_sources)} source node(s) from subgraph import: {list(skipped_sources.keys())}"
            )

        # Restore connections with mapped names
        for conn in state.get("connects", []):
            if len(conn) < 4:
                continue
            from_node, from_term, to_node, to_term = conn[0], conn[1], conn[2], conn[3]

            # Skip connections involving skipped sources (they become boundary inputs)
            if from_node in skipped_sources or to_node in skipped_sources:
                continue

            if from_node not in node_mapping or to_node not in node_mapping:
                continue

            try:
                from_node_obj = self._graph.nodes[node_mapping[from_node]]["node"]
                to_node_obj = self._graph.nodes[node_mapping[to_node]]["node"]

                if from_term not in from_node_obj.terminals or to_term not in to_node_obj.terminals:
                    continue

                term1 = from_node_obj.terminals[from_term]
                term2 = to_node_obj.terminals[to_term]
                # IMPORTANT: Use signal=True to populate _input_vars which is required
                # for node compilation via to_operation(inputs=...). Only helper boundary
                # connections should use signal=False.
                term1.connectTo(term2, signal=True)

                # Add edge to graph
                self._graph.add_edge(
                    node_mapping[from_node],
                    node_mapping[to_node],
                    key=f"{node_mapping[from_node]}.{from_term}->{node_mapping[to_node]}.{to_term}",
                    from_term=from_term,
                    to_term=to_term,
                )
            except Exception:
                printExc(f"Error connecting {from_node}.{from_term} to {to_node}.{to_term}")
                continue

        if not restored_nodes:
            logger.error("No nodes were successfully restored")
            return None

        # Create subgraph using import-specific function
        metadata = state.get("subgraph_metadata", {})
        metadata_boundary_inputs = metadata.get("boundary_inputs", [])
        combined_boundary_inputs = auto_boundary_inputs + metadata_boundary_inputs

        self._createSubgraphFromImport(
            name=name,
            nodes=restored_nodes,
            boundary_inputs=combined_boundary_inputs,
            boundary_outputs=metadata.get("boundary_outputs", []),
            node_mapping=node_mapping,
            pos=pos,
            description=metadata.get("description", ""),
        )

        # Switch back to root view
        self.viewManager().displayView(name="root")

        if self._widget:
            self.widget().chartWidget.updateStatus(f"Imported subgraph: {name}")

        return name

    def instantiateSubgraphFromLibrary(self, template_name, pos=None):
        """Create a new instance of a subgraph from the library

        Args:
            template_name: Name of template in library
            pos: Position for placeholder (tuple or QPointF)

        Returns:
            subgraph_name: Name of created subgraph, or None if error
        """
        # Get template
        template = self.subgraph_library.getSubgraph(template_name)
        if not template:
            logger.error(f"Subgraph template {template_name} not found in library")
            return None

        # Create state dict from template
        state = {
            "subgraph_metadata": {
                "name": template.name,
                "description": template.description,
                "boundary_inputs": template.boundary_inputs,
                "boundary_outputs": template.boundary_outputs,
            },
            "nodes": template.nodes,
            "connects": template.connects,
        }

        # Use import logic to create instance
        return self.importSubgraphFromFile(state, pos=pos)

    def _addSubgraphToLibrary(self, subgraph_name, update=False):
        """Add a single subgraph to the library and update UI

        Args:
            subgraph_name: Name of the subgraph in self._subgraphs
            update: If True, update existing template; if False, skip if exists
        """
        if not self._widget or subgraph_name not in self._subgraphs:
            return

        # Skip if already in library (unless updating)
        if self.subgraph_library.hasSubgraph(subgraph_name) and not update:
            return

        sg_data = self._subgraphs[subgraph_name]

        # Collect nodes in subgraph
        nodes = []
        for node_name in sg_data["nodes"]:
            if node_name not in self._graph.nodes:
                continue
            node = self._graph.nodes[node_name]["node"]
            nodes.append({"class": type(node).__name__, "name": node_name, "state": node.saveState()})

        # Collect internal connections only
        connects = []
        for from_node, to_node, data in self._graph.edges(data=True):
            if from_node in sg_data["nodes"] and to_node in sg_data["nodes"]:
                connects.append((from_node, data["from_term"], to_node, data["to_term"]))

        # Collect boundary metadata (for SubgraphTemplate)
        placeholder = sg_data["placeholder"]
        boundary_inputs = []
        boundary_outputs = []

        for bc in sg_data.get("boundary_connections", []):
            if bc["type"] == "input":
                term = placeholder.terminals.get(bc["terminal_name"])
                if term:
                    boundary_inputs.append(
                        {
                            "placeholder_terminal": bc["terminal_name"],
                            "internal_node": bc["internal_node"].name(),
                            "internal_terminal": bc["internal_term"].name(),
                            "ttype": term.type(),
                        }
                    )
            else:  # output
                term = placeholder.terminals.get(bc["terminal_name"])
                if term:
                    boundary_outputs.append(
                        {
                            "placeholder_terminal": bc["terminal_name"],
                            "internal_node": bc["internal_node"].name(),
                            "internal_terminal": bc["internal_term"].name(),
                            "ttype": term.type(),
                        }
                    )

        # Create state dict with boundary metadata
        state = {
            "nodes": nodes,
            "connects": connects,
            "subgraph_metadata": {
                "name": subgraph_name,
                "description": sg_data.get("description", ""),
                "boundary_inputs": boundary_inputs,
                "boundary_outputs": boundary_outputs,
            },
        }

        # Create template
        description = sg_data.get("description", "") or "Subgraph created in flowchart"
        template = SubgraphTemplate(name=subgraph_name, description=description, state=state, source_file=None)

        # Add to library
        self.subgraph_library.addSubgraph(subgraph_name, template)

        # Update the UI tree
        self._updateSubgraphLibraryUI()

        # Show status message
        if self._widget:
            action = "Updated" if update else "Added"
            self.widget().chartWidget.updateStatus(f"{action} subgraph template: {subgraph_name}")

    def _updateSubgraphLibraryUI(self):
        """Update the subgraph library tree in the UI (hierarchical by source file)"""
        if not self._widget:
            return

        ctrl = self.widget()

        # Check if UI has subgraph_tree attribute
        if not hasattr(ctrl.ui, "subgraph_tree"):
            logger.debug("UI does not have subgraph_tree, skipping library update")
            return

        # Clear the tree
        ctrl.ui.clear_model(ctrl.ui.subgraph_tree)

        # Group subgraphs by source file
        by_file = defaultdict(list)

        for sg_name in sorted(self.subgraph_library.getNames()):
            template = self.subgraph_library.getSubgraph(sg_name)
            if template:
                # Group by source file
                if template.source_file:
                    # Use just the filename without extension as the key
                    filename = os.path.basename(template.source_file)
                    file_key = os.path.splitext(filename)[0]
                else:
                    file_key = "Root"

                by_file[file_key].append((sg_name, template))

        # Build hierarchical tree data
        tree_data = {}
        for file_key in sorted(by_file.keys()):
            # Create file-level entry with children
            children = {}
            for sg_name, template in sorted(by_file[file_key], key=lambda x: x[0]):
                node_count = len(template.nodes)
                desc = template.description or "No description"
                children[sg_name] = f"{desc} ({node_count} nodes)"

            tree_data[file_key] = children

        if tree_data:
            # Update tree model with hierarchical data
            ctrl.ui.create_model(ctrl.ui.subgraph_tree, tree_data, typ="SubgraphTree")
            logger.debug(f"Updated subgraph library UI with {sum(len(v) for v in tree_data.values())} templates")

    def removeSubgraphFromLibrary(self, template_name):
        """Remove a subgraph template from the library and delete all live instances.

        Args:
            template_name: Name of the template in the subgraph library
        """
        # Find live instances matching this template (same name or name.N pattern)
        matching = [
            name
            for name in list(self._subgraphs.keys())
            if name == template_name or name.startswith(f"{template_name}.")
        ]

        # Confirmation dialog
        msg = f"Remove template '{template_name}'"
        if matching:
            msg += f" and {len(matching)} live instance(s)?"
        else:
            msg += "?"

        reply = QtWidgets.QMessageBox.question(
            self.widget(), "Remove Subgraph", msg, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        # Delete live instances by closing their placeholders
        for sg_name in matching:
            sg_data = self._subgraphs.get(sg_name)
            if sg_data and sg_data.get("placeholder"):
                sg_data["placeholder"].close(emit=True)

        # Remove from library
        self.subgraph_library.removeSubgraph(template_name)
        self._updateSubgraphLibraryUI()

    def _addRestoredSubgraphsToLibrary(self):
        """Add all subgraphs in the current flowchart to the library

        Called after restoring a flowchart to make the subgraphs available
        in the library tree for drag-and-drop.
        """
        if not self._widget:
            return

        for sg_name, sg_data in self._subgraphs.items():
            # Skip if already in library
            if self.subgraph_library.hasSubgraph(sg_name):
                continue

            # Collect nodes in subgraph
            nodes = []
            for node_name in sg_data["nodes"]:
                if node_name not in self._graph.nodes:
                    continue
                node = self._graph.nodes[node_name]["node"]
                nodes.append({"class": type(node).__name__, "name": node_name, "state": node.saveState()})

            # Collect internal connections only
            connects = []
            for from_node, to_node, data in self._graph.edges(data=True):
                if from_node in sg_data["nodes"] and to_node in sg_data["nodes"]:
                    connects.append((from_node, data["from_term"], to_node, data["to_term"]))

            # Create state dict
            state = {"nodes": nodes, "connects": connects}

            # Create template
            template = SubgraphTemplate(
                name=sg_name,
                description=sg_data.get("description", "Subgraph from flowchart"),
                state=state,
                source_file=None,
            )

            # Add to library
            self.subgraph_library.addSubgraph(sg_name, template)

    @asyncSlot(object)
    async def send_requested_data(self, requested_data):
        ctrl = self.widget()
        await ctrl.graphCommHandler.update_requested_data(requested_data)

    @asyncSlot(object, object)
    async def nodeClosed(self, node, input_vars):
        # NEW: Handle nodes inside subgraphs
        node_name = node.name()

        # Check all subgraphs for this node
        for sg_name, sg_data in list(self._subgraphs.items()):
            if node_name in sg_data["nodes"]:
                # Remove from subgraph
                sg_data["nodes"].remove(node_name)
                # Also remove from placeholder's children list
                placeholder = sg_data["placeholder"]
                if node in placeholder.children:
                    placeholder.children.remove(node)

                # Auto-delete empty subgraphs
                if not sg_data["nodes"]:
                    # This will trigger SubgraphNode.close()
                    sg_data["placeholder"].close()
                    # Will be removed from self._subgraphs by close()
                    continue

                # Update boundary connections (remove connections involving this node)
                sg_data["boundary_connections"] = [
                    bc for bc in sg_data["boundary_connections"] if bc["internal_term"].node().name() != node_name
                ]

        # Handle SubgraphNode deletion
        if isinstance(node, SubgraphNode):
            # View already removed by SubgraphNode.close()
            # Just return to skip normal deletion
            return

        self._graph.remove_node(node.name())
        await self.broker.send_string(node.name(), zmq.SNDMORE)
        await self.broker.send_pyobj(fcMsgs.CloseNode())
        ctrl = self.widget()
        name = node.name()

        if hasattr(node, "to_operation"):
            self.deleted_nodes.append(name)
            self.sigNodeChanged.emit(node)
            if ctrl.features.remove_plot(name):
                await ctrl.graphCommHandler.updatePlots(ctrl.features.plots)
        elif isinstance(node, SourceNode):
            await ctrl.features.discard(name, name)
            await ctrl.graphCommHandler.unview(name)
            await ctrl.graphCommHandler.updatePlots(ctrl.features.plots)
        elif node.viewable():
            views = []
            for term, in_var in input_vars.items():
                discarded = await ctrl.features.discard(name, in_var)
                if discarded:
                    views.append(in_var)
            if views:
                await ctrl.graphCommHandler.unview(views)
                await ctrl.graphCommHandler.updatePlots(ctrl.features.plots)
        elif node.exportable():
            if "eventid" in input_vars:
                await ctrl.graphCommHandler.unexport(
                    [input_vars["In"], input_vars["eventid"]], [node.values["alias"], "_timestamp"]
                )
            elif "Timestamp" in input_vars:
                await ctrl.graphCommHandler.unexport(
                    [input_vars["In"], input_vars["Timestamp"]], [node.values["alias"], "_timestamp"]
                )

    @asyncSlot(object, object)
    async def nodeTermAdded(self, node, term):
        name = node.name()
        state = term.saveState()
        msg = fcMsgs.NodeTermAdded(name, term.name(), state)
        await self.broker.send_string(name, zmq.SNDMORE)
        await self.broker.send_pyobj(msg)

    @asyncSlot(object, object)
    async def nodeTermRemoved(self, node, term):
        name = node.name()
        msg = fcMsgs.NodeTermRemoved(name, term.name())
        await self.broker.send_string(name, zmq.SNDMORE)
        await self.broker.send_pyobj(msg)

    @asyncSlot(object, object)
    async def nodeTermConnected(self, localTerm, remoteTerm):
        # Handle case where remoteTerm is None (e.g., SubgraphInput without source)
        if not remoteTerm or not localTerm:
            return

        if remoteTerm.isOutput():
            t = remoteTerm
            remoteTerm = localTerm
            localTerm = t

        localNode = localTerm.node().name()
        remoteNode = remoteTerm.node().name()
        key = localNode + "." + localTerm.name() + "->" + remoteNode + "." + remoteTerm.name()

        # Check if connecting FROM SubgraphInput helper TO internal node
        if hasattr(remoteTerm.node(), "isSubgraphInput") and remoteTerm.node().isSubgraphInput:
            sg_input_node = remoteTerm.node()
            placeholder = sg_input_node.rootNode
            terminal_name = remoteTerm.name()

            # Find which external node is connected to this SubgraphInput terminal
            # by looking at the placeholder's corresponding input terminal
            placeholder_term = placeholder.terminals.get(terminal_name)
            if placeholder_term:
                external_terms = placeholder_term.inputTerminals()
                if external_terms:
                    # Found external connection(s)
                    external_term = external_terms[0]  # Take first one
                    external_node = external_term.node()

                    # Create DIRECT graph edge: External -> Internal (localNode is the internal node)
                    edge_key = f"{external_node.name()}.{external_term.name()}->{localNode}.{localTerm.name()}"

                    self._graph.add_edge(
                        external_node.name(),
                        localNode,
                        key=edge_key,
                        from_term=external_term.name(),
                        to_term=localTerm.name(),
                    )

                    # CRITICAL: Update internal node's _input_vars
                    localTerm.node().connected(localTerm, external_term)

                    self.sigNodeChanged.emit(localTerm.node())
                    return
                else:
                    # No external connection yet, just create normal edge for now
                    pass

        # Check if connecting to/from a subgraph placeholder
        if hasattr(remoteTerm.node(), "isSubgraph") and remoteTerm.node().isSubgraph:
            subgraph = remoteTerm.node()
            sg_data = self._subgraphs[subgraph.name()]

            if remoteTerm.isInput():
                # External -> Placeholder Input
                # Find matching boundary connection
                for bc in sg_data["boundary_connections"]:
                    if bc["terminal_name"] == remoteTerm.name() and bc["type"] == "input":
                        internal_node = bc["internal_node"]
                        internal_term = bc["internal_term"]

                        # Create DIRECT graph edge: External -> Internal
                        edge_key = f"{localNode}.{localTerm.name()}->{internal_node.name()}.{internal_term.name()}"

                        self._graph.add_edge(
                            localNode,
                            internal_node.name(),
                            key=edge_key,
                            from_term=localTerm.name(),
                            to_term=internal_term.name(),
                        )

                        # CRITICAL: Update internal node's _input_vars
                        internal_node.connected(internal_term, localTerm)

                        self.sigNodeChanged.emit(localTerm.node())
                        return

            elif remoteTerm.isOutput():
                # Placeholder Output -> External
                # Find matching boundary connection
                for bc in sg_data["boundary_connections"]:
                    if bc["terminal_name"] == remoteTerm.name() and bc["type"] == "output":
                        internal_node = bc["internal_node"]
                        internal_term = bc["internal_term"]

                        # Create DIRECT graph edge: Internal -> External
                        edge_key = f"{internal_node.name()}.{internal_term.name()}->{localNode}.{localTerm.name()}"

                        self._graph.add_edge(
                            internal_node.name(),
                            localNode,
                            key=edge_key,
                            from_term=internal_term.name(),
                            to_term=localTerm.name(),
                        )

                        # Update external node's _input_vars
                        localTerm.node().connected(localTerm, internal_term)

                        self.sigNodeChanged.emit(internal_node)
                        return

        if not self._graph.has_edge(localNode, remoteNode, key=key):
            self._graph.add_edge(localNode, remoteNode, key=key, from_term=localTerm.name(), to_term=remoteTerm.name())

            msg = fcMsgs.NodeTermConnected(
                localNode,
                isinstance(localTerm.node(), SourceNode),
                localTerm.name(),
                localTerm.saveState(),
                remoteNode,
                isinstance(remoteTerm.node(), SourceNode),
                remoteTerm.name(),
                remoteTerm.saveState(),
            )
            localTerm.node().terminalConnected(msg)
            await self.broker.send_string(localNode, zmq.SNDMORE)
            await self.broker.send_pyobj(msg)

            msg = fcMsgs.NodeTermConnected(
                remoteNode,
                isinstance(remoteTerm.node(), SourceNode),
                remoteTerm.name(),
                remoteTerm.saveState(),
                localNode,
                isinstance(localTerm.node(), SourceNode),
                localTerm.name(),
                localTerm.saveState(),
            )
            remoteTerm.node().terminalConnected(msg)
            await self.broker.send_string(remoteNode, zmq.SNDMORE)
            await self.broker.send_pyobj(msg)

        self.sigNodeChanged.emit(localTerm.node())

    @asyncSlot(object, object)
    async def nodeTermDisconnected(self, localTerm, remoteTerm):
        if remoteTerm.isOutput():
            t = remoteTerm
            remoteTerm = localTerm
            localTerm = t

        localNode = localTerm.node().name()
        remoteNode = remoteTerm.node().name()
        key = localNode + "." + localTerm.name() + "->" + remoteNode + "." + remoteTerm.name()

        # Check if disconnecting from a subgraph placeholder
        if hasattr(remoteTerm.node(), "isSubgraph") and remoteTerm.node().isSubgraph:
            subgraph = remoteTerm.node()
            if subgraph.name() not in self._subgraphs:
                return
            sg_data = self._subgraphs[subgraph.name()]

            if remoteTerm.isInput():
                # Disconnecting External -> Placeholder Input
                # Find matching boundary connection
                for bc in sg_data["boundary_connections"]:
                    if bc["terminal_name"] == remoteTerm.name() and bc["type"] == "input":
                        internal_node = bc["internal_node"]
                        internal_term = bc["internal_term"]

                        edge_key = f"{localNode}.{localTerm.name()}->{internal_node.name()}.{internal_term.name()}"

                        if self._graph.has_edge(localNode, internal_node.name(), key=edge_key):
                            self._graph.remove_edge(localNode, internal_node.name(), key=edge_key)

                        # Update internal node's _input_vars
                        internal_node.disconnected(internal_term, localTerm)

                        self.sigNodeChanged.emit(localTerm.node())
                        return

            elif remoteTerm.isOutput():
                # Disconnecting Placeholder Output -> External
                # Find matching boundary connection
                for bc in sg_data["boundary_connections"]:
                    if bc["terminal_name"] == remoteTerm.name() and bc["type"] == "output":
                        internal_node = bc["internal_node"]
                        internal_term = bc["internal_term"]

                        edge_key = f"{internal_node.name()}.{internal_term.name()}->{localNode}.{localTerm.name()}"

                        if self._graph.has_edge(internal_node.name(), localNode, key=edge_key):
                            self._graph.remove_edge(internal_node.name(), localNode, key=edge_key)

                        # Update external node's _input_vars
                        localTerm.node().disconnected(localTerm, internal_term)

                        self.sigNodeChanged.emit(internal_node)
                        return

        if self._graph.has_edge(localNode, remoteNode, key=key):
            self._graph.remove_edge(localNode, remoteNode, key=key)

            msg = fcMsgs.NodeTermDisconnected(
                localNode,
                isinstance(localTerm.node(), SourceNode),
                localTerm.name(),
                localTerm.saveState(),
                remoteNode,
                isinstance(remoteTerm.node(), SourceNode),
                remoteTerm.name(),
                remoteTerm.saveState(),
            )
            localTerm.node().terminalDisconnected(msg)
            await self.broker.send_string(localNode, zmq.SNDMORE)
            await self.broker.send_pyobj(msg)

            msg = fcMsgs.NodeTermDisconnected(
                remoteNode,
                isinstance(remoteTerm.node(), SourceNode),
                remoteTerm.name(),
                remoteTerm.saveState(),
                localNode,
                isinstance(localTerm.node(), SourceNode),
                localTerm.name(),
                localTerm.saveState(),
            )
            remoteTerm.node().terminalDisconnected(msg)
            await self.broker.send_string(remoteNode, zmq.SNDMORE)
            await self.broker.send_pyobj(msg)

        self.sigNodeChanged.emit(localTerm.node())

    def nodeTermOptional(self, node, term):
        node.changed = True
        self.sigNodeChanged.emit(node)

    def nodeLatched(self, node):
        node.changed = True
        self.sigNodeChanged.emit(node)

    @asyncSlot(object, object)
    async def nodeLabelChanged(self, node, label):
        """Handle label change events from nodes and forward to NodeProcess"""
        name = node.name()
        msg = fcMsgs.NodeLabelChanged(name, label)
        await self.broker.send_string(name, zmq.SNDMORE)
        await self.broker.send_pyobj(msg)

    @asyncSlot(object)
    async def nodeEnabled(self, root):
        enabled = root._enabled

        outputs = [n for n, d in self._graph.out_degree() if d == 0]
        sources_targets = list(it.product([root.name()], outputs))
        ctrl = self.widget()
        views = []

        for s, t in sources_targets:
            paths = list(nx.algorithms.all_simple_paths(self._graph, s, t))

            for path in paths:
                for node in path:
                    node = self._graph.nodes[node]["node"]
                    name = node.name()
                    node.nodeEnabled(enabled)
                    if not enabled:
                        if hasattr(node, "to_operation"):
                            self.deleted_nodes.append(name)
                        elif node.viewable():
                            for term, in_var in node.input_vars().items():
                                discarded = await ctrl.features.discard(name, in_var)
                                if discarded:
                                    views.append(in_var)
                    else:
                        node.changed = True

        if views:
            await ctrl.graphCommHandler.unview(views)
        await ctrl.applyClicked()

    def widget(self, parent=None):
        """
        Return the control widget for this flowchart.

        This widget provides GUI access to the parameters for each node and a
        graphical representation of the flowchart.
        """
        if self._widget is None:
            self._widget = FlowchartCtrlWidget(self, self.graphmgr_addr, self.configure, parent)
        return self._widget

    def viewBox(self):
        return self.widget().viewBox()

    def viewManager(self):
        return self.widget().viewManager()

    def saveState(self):
        """
        Return a serializable data structure representing the current state of this flowchart.
        """
        state = {}
        state["nodes"] = []
        state["connects"] = []
        state["viewbox"] = self.viewBox().saveState()

        # Save regular nodes (skip visual-only nodes like SubgraphNode)
        for name, node in self.nodes(data="node"):
            # Skip if node is None (shouldn't happen, but be defensive)
            if node is None:
                continue
            # Skip visual-only nodes
            if getattr(node, "is_visual_only", False):
                continue

            cls = type(node)
            clsName = cls.__name__
            ns = {"class": clsName, "name": name, "state": node.saveState()}
            state["nodes"].append(ns)

        for from_node, to_node, data in self._graph.edges(data=True):
            from_term = data["from_term"]
            to_term = data["to_term"]
            state["connects"].append((from_node, from_term, to_node, to_term))

        # NEW: Save subgraphs (visual-only metadata)
        state["subgraphs"] = []
        for sg_name, sg_data in self._subgraphs.items():
            placeholder_pos = sg_data["placeholder"].graphicsItem().pos()
            state["subgraphs"].append(
                {
                    "name": sg_name,
                    "nodes": sg_data["nodes"],
                    "placeholder_pos": (placeholder_pos.x(), placeholder_pos.y()),
                    "description": sg_data.get("description", ""),
                }
            )

        # NEW: Save all view states (not just root)
        state["views"] = {}
        for view_name, view in self.viewManager().views.items():
            state["views"][view_name] = view.viewBox().saveState()

        state["source_configuration"] = self.widget().sourceConfigure.saveState()
        state["library"] = self.widget().libraryEditor.saveState()
        return state

    def restoreState(self, state):
        """
        Restore the state of this flowchart from a previous call to `saveState()`.
        """
        if "source_configuration" in state:
            src_cfg = state["source_configuration"]
            self.widget().sourceConfigure.restoreState(src_cfg)
            if src_cfg["files"]:
                self.widget().sourceConfigure.applyClicked()

        if "library" in state:
            lib_cfg = state["library"]
            self.widget().libraryEditor.restoreState(lib_cfg)
            self.widget().libraryEditor.applyClicked()

        if "viewbox" in state:
            self.viewBox().restoreState(state["viewbox"])

        nodes = state["nodes"]
        nodes.sort(key=lambda a: a["state"]["pos"][0])
        for n in nodes:
            if n["class"] == "SourceNode":
                try:
                    ttype = eval(n["state"]["terminals"]["Out"]["ttype"])
                    n["state"]["terminals"]["Out"]["ttype"] = ttype
                    node = SourceNode(name=n["name"], terminals=n["state"]["terminals"], flowchart=self)
                    self.addNode(node=node)
                except Exception:
                    printExc("Error creating node %s: (continuing anyway)" % n["name"])
            else:
                try:
                    node = self.createNode(n["class"], name=n["name"], prompt=False)
                except Exception:
                    printExc("Error creating node %s: (continuing anyway)" % n["name"])

            node.blockSignals(True)

            if hasattr(node, "display"):
                node.display(topics=None, terms=None, addr=None, win=None)

            node.restoreState(n["state"])

            node.blockSignals(False)

        connections = {}
        edges = {}
        checked = []

        with tempfile.NamedTemporaryFile(mode="w") as type_file:
            type_file.write("from typing import *\n")
            type_file.write("from mypy_extensions import TypedDict\n")
            type_file.write("import numbers\n")
            type_file.write("import builtins\n")
            type_file.write("import amitypes\n")
            type_file.write("T = TypeVar('T')\n\n")

            nodes = self.nodes(data="node")

            for n1, t1, n2, t2 in state["connects"]:
                try:
                    node1 = nodes[n1]
                    term1 = node1[t1]
                    node2 = nodes[n2]
                    term2 = node2[t2]

                    term1.connectTo(term2, type_file=type_file, checked=checked)
                    if term1.isInput():
                        in_name = node1.name() + "_" + term1.name()
                        in_name = in_name.replace(".", "_")
                        out_name = node2.name() + "_" + term2.name()
                        out_name = out_name.replace(".", "_")
                        edge = (
                            (node2.name(), node1.name()),
                            f"{node2.name()}.{term2.name()}->{node1.name()}.{term1.name()}",
                            term2.name(),
                            term1.name(),
                        )
                        edges[(in_name, out_name)] = edge
                    else:
                        in_name = node2.name() + "_" + term2.name()
                        in_name = in_name.replace(".", "_")
                        out_name = node1.name() + "_" + term1.name()
                        out_name = out_name.replace(".", "_")
                        edge = (
                            (node1.name(), node2.name()),
                            f"{node1.name()}.{term1.name()}->{node2.name()}.{term2.name()}",
                            term1.name(),
                            term2.name(),
                        )
                        edges[(in_name, out_name)] = edge

                    connections[(in_name, out_name)] = (term1, term2)
                except Exception:
                    print(node1.terminals)
                    print(node2.terminals)
                    printExc("Error connecting terminals %s.%s - %s.%s:" % (n1, t1, n2, t2))

            type_file.flush()
            dmypy_status = os.environ["DMYPY_STATUS_FILE"]
            status = subprocess.run(
                ["dmypy", "--status-file", dmypy_status, "check", type_file.name], capture_output=True, text=True
            )

            if status.returncode != 0:
                lines = status.stdout.split("\n")[:-1]
                for line in lines:
                    m = re.search(r"\"+(\w+)\"+", line)
                    if m:
                        m = m.group().replace('"', "")
                        for i in connections:
                            if i[0] == m:
                                term1, term2 = connections[i]
                                term1.disconnectFrom(term2)
                                if i in edges:
                                    del edges[i]
                                break
                            elif i[1] == m:
                                term1, term2 = connections[i]
                                term1.disconnectFrom(term2)
                                if i in edges:
                                    del edges[i]
                                break

            for _, edge in edges.items():
                localNode_remoteNode, key, localTerm, remoteTerm = edge
                localNode, remoteNode = localNode_remoteNode
                self._graph.add_edge(localNode, remoteNode, key=key, from_term=localTerm, to_term=remoteTerm)

        # NEW: Restore subgraphs (MUST BE AFTER nodes and connections)
        if "subgraphs" in state:
            for sg_state in state["subgraphs"]:
                # Get node objects from names
                node_objects = []
                for node_name in sg_state["nodes"]:
                    if node_name in self._graph.nodes:
                        node_objects.append(self._graph.nodes[node_name]["node"])
                    else:
                        logger.warning(f"Node {node_name} not found for subgraph {sg_state['name']}")

                # Only create if we have valid nodes
                if node_objects:
                    self.makeSubgraphFromSelection(
                        nodes=node_objects,
                        name=sg_state["name"],
                        pos=sg_state.get("placeholder_pos"),
                        description=sg_state.get("description", ""),
                    )
                else:
                    logger.warning(f"Skipping empty subgraph {sg_state['name']}")

            # Switch back to root view after restoring all subgraphs
            self.viewManager().displayView(name="root")

            # Automatically add restored subgraphs to the library
            self._addRestoredSubgraphsToLibrary()

        # NEW: Restore view states
        if "views" in state:
            for view_name, view_state in state["views"].items():
                if view_name in self.viewManager().views:
                    self.viewManager().views[view_name].viewBox().restoreState(view_state)

    @asyncSlot(str)
    async def loadFile(self, fileName=None):
        """
        Load a flowchart (*.fc) file.
        """
        if not os.path.exists(fileName):
            msg = QtWidgets.QMessageBox()
            msg.setText(f"File {fileName} does not exist!")
            msg.show()
            return

        with open(fileName, "r") as f:
            state = json.load(f)

        ctrl = self.widget()
        await ctrl.clear()
        self.restoreState(state)
        self.viewBox().autoRange()
        self.sigFileLoaded.emit(fileName)
        await ctrl.applyClicked(build_views=False)

        nodes = []
        for name, node in self.nodes(data="node"):
            if node.viewed or node.exportable():
                nodes.append(node)
            node.blockSignals(False)

        await ctrl.chartWidget.build_views(nodes, ctrl=True, export=True)

    def saveFile(self, fileName=None, startDir=None, suggestedFileName="flowchart.fc"):
        """
        Save this flowchart to a .fc file
        """
        if fileName is None:
            if startDir is None:
                startDir = self.filePath
            if startDir is None:
                startDir = "."
            self.fileDialog = FileDialog(None, "Save Flowchart..", startDir, "Flowchart (*.fc)")
            self.fileDialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)

            if self.fileDialog.exec():
                fileName = self.fileDialog.selectedFiles()[0]
            else:
                return

        if not fileName.endswith(".fc"):
            fileName += ".fc"

        state = self.saveState()
        state = json.dumps(state, indent=2, separators=(",", ": "), sort_keys=False, cls=TypeEncoder)

        with open(fileName, "w") as f:
            f.write(state)
            f.write("\n")

        ctrl = self.widget()
        ctrl.graph_info.labels(self.hutch, ctrl.graph_name).info({"graph": state})
        ctrl.chartWidget.updateStatus(f"Saved graph to: {fileName}")
        self.sigFileSaved.emit(fileName)

    async def clear(self):
        """
        Remove all nodes from this flowchart except the original input/output nodes.
        """
        # Switch to root view before clearing (in case we're on a subgraph view)
        self.viewManager().displayView(name="root")

        # Step 1: Clean up regular nodes (including nodes inside subgraphs)
        for name, node in self._graph.nodes(data="node"):
            if node is None:
                continue

            await self.broker.send_string(name, zmq.SNDMORE)
            await self.broker.send_pyobj(fcMsgs.CloseNode())
            node.close(emit=False)

        self._graph = nx.MultiDiGraph()

        # Step 2: Clean up subgraph placeholders and views
        # (Now that their children are already closed)
        subgraph_names = list(self._subgraphs.keys())
        for sg_name in subgraph_names:
            if sg_name not in self._subgraphs:
                continue  # Safety check (should not happen, but defensive)

            sg_data = self._subgraphs[sg_name]
            placeholder = sg_data["placeholder"]

            # Remove view and toolbar button
            self.viewManager().removeView(sg_name)

            # Remove placeholder graphics from root view
            item = placeholder.graphicsItem()
            if item.scene() is not None:
                item.scene().removeItem(item)

            # Clean up helper nodes (SubgraphInputs/Outputs)
            placeholder._subgraphInputs.close(emit=False)
            placeholder._subgraphOutputs.close(emit=False)

            # Clean up boundary connections (visual-only)
            for bc in sg_data.get("boundary_connections", []):
                root_visual = bc.get("root_visual")
                if root_visual and hasattr(root_visual, "close"):
                    root_visual.close()
                sg_visual = bc.get("subgraph_visual")
                if sg_visual and hasattr(sg_visual, "close"):
                    sg_visual.close()

            # Remove from tracking
            del self._subgraphs[sg_name]

        # Clear the subgraph library (templates don't persist across New)
        self.subgraph_library.clear()
        self._updateSubgraphLibraryUI()

    async def updateState(self):
        while True:
            await self.checkpoint.recv_string()
            msg = await self.checkpoint.recv_pyobj()
            node_name = msg.name
            new_node_state = msg.state

            if node_name not in self._graph.nodes:
                continue

            node = self._graph.nodes[node_name]["node"]
            current_node_state = node.saveState()
            restore_ctrl = False
            restore_widget = False

            if "ctrl" in new_node_state:
                if current_node_state["ctrl"] != new_node_state["ctrl"]:
                    current_node_state["ctrl"] = new_node_state["ctrl"]
                    restore_ctrl = True

            if "widget" in new_node_state:
                if current_node_state["widget"] != new_node_state["widget"]:
                    restore_widget = True
                    current_node_state["widget"] = new_node_state["widget"]

            if "geometry" in new_node_state:
                node.geometry = QtCore.QByteArray.fromHex(bytes(new_node_state["geometry"], "ascii"))

            if restore_ctrl or restore_widget:
                node.blockSignals(True)
                node.restoreState(current_node_state)
                node.blockSignals(False)
                if node.isChanged(restore_ctrl, restore_widget):
                    node.changed = True
                    self.sigNodeChanged.emit(node)

            node.viewed = new_node_state["viewed"]

            # Update state panel if this node is currently displayed
            ctrl_widget = self.widget()
            if ctrl_widget.chartWidget.current_displayed_node == node:
                ctrl_widget.chartWidget.refreshStatePanel(node)

    async def updateSources(self, init=False):
        num_workers = None

        while True:
            topic = await self.graphinfo.recv_string()
            source = await self.graphinfo.recv_string()
            msg = await self.graphinfo.recv_pyobj()

            if topic == "sources":
                source_library = SourceLibrary()
                for source, node_type in msg.items():
                    pth = []
                    if ":" in source:
                        for part in source.split(":")[:-1]:
                            if pth:
                                part = ":".join((pth[-1], part))
                            pth.append(part)
                    elif "_" in source:
                        for part in source.split("_")[:-1]:
                            if pth:
                                part = "_".join((pth[-1], part))
                            pth.append(part)
                    source_library.addNodeType(source, amitypes.loads(node_type), [pth])

                self.source_library = source_library

                if init:
                    break

                ctrl = self.widget()
                tree = ctrl.ui.source_tree
                ctrl.ui.clear_model(tree)
                ctrl.ui.create_model(ctrl.ui.source_tree, self.source_library.getLabelTree(), typ="SourceTree")

                ctrl.chartWidget.updateStatus("Updated sources.")

            elif topic == "event_rate":
                if num_workers is None:
                    ctrl = self.widget()
                    compiler_args = await ctrl.graphCommHandler.compilerArgs
                    num_workers = compiler_args["num_workers"]
                    events_per_second = [None] * num_workers
                    total_events = [None] * num_workers

                if ctrl.graph_name not in msg:
                    continue
                time_per_event = msg[ctrl.graph_name]
                worker = int(re.search(r"(\d)+", source).group())
                events_per_second[worker] = len(time_per_event) / (time_per_event[-1][1] - time_per_event[0][0])
                total_events[worker] = msg["num_events"]

                if all(events_per_second):
                    events_per_second = int(np.average(events_per_second))
                    total_num_events = int(np.sum(total_events))
                    ctrl = self.widget()
                    ctrl.ui.rateLbl.setText(f"Num Events: {total_num_events} Avg Events/Sec: {events_per_second}")
                    events_per_second = [None] * num_workers
                    total_events = [None] * num_workers
            elif topic == "warning":
                ctrl = self.widget()
                if hasattr(msg, "node_name"):
                    if msg.graph_name != ctrl.graph_name:
                        continue
                    node_name = ""
                    if msg.node_name in ctrl.metadata:
                        node_name = ctrl.metadata[msg.node_name]["parent"]
                    if node_name in self.nodes(data="node"):
                        node = self.nodes(data="node")[node_name]
                        if node.exception is None:
                            node.setException(msg, "warning")
                            ctrl.chartWidget.updateStatus(f"WARNING: {source} {node.name()}: {msg}", color="orange")
                            logger.warning(f"{source} {node.name()}: {msg}")
            elif topic == "error":
                ctrl = self.widget()
                if hasattr(msg, "node_name"):
                    if msg.graph_name != ctrl.graph_name:
                        continue
                    node_name = ctrl.metadata[msg.node_name]["parent"]
                    node = self.nodes(data="node")[node_name]
                    node.setException(msg)
                    ctrl.chartWidget.updateStatus(f"ERROR: {source} {node.name()}: {msg}", color="red")
                    logger.error(f"{source} {node.name()}: {msg}")
                else:
                    ctrl.chartWidget.updateStatus(f"ERROR: {source}: {msg}", color="red")
                    logger.error(f"{source}: {msg}")

    async def run(self, load=None):
        tasks = [asyncio.create_task(self.updateState()), asyncio.create_task(self.updateSources())]

        if load:
            await self.loadFile(load)

        await asyncio.gather(*tasks)


class FlowchartCtrlWidget(QtWidgets.QWidget):
    """
    The widget that contains the list of all the nodes in a flowchart and their controls,
    as well as buttons for loading/saving flowcharts.

    Args
        chart (ami.flowchart.Flowchart.Flowchart):
        graphmgr_addr (ami.client.GraphMgrAddress):
        configure (bool):
    """

    def __init__(self, chart, graphmgr_addr, configure, parent=None):
        super().__init__(parent)

        self.graphmgr_addr = graphmgr_addr
        self.graphCommHandler = AsyncGraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm, ctx=chart.ctx)
        self.graph_name = graphmgr_addr.name
        self.metadata = None

        self.currentFileName = None
        self.unsaved_changes = False
        self.chart = chart
        self.chartWidget = FlowchartWidget(chart, self)

        self.ui = EditorTemplate.Ui_Toolbar()
        self.ui.setupUi(parent=self, chart=self.chartWidget, configure=configure)
        self.ui.create_model(self.ui.node_tree, self.chart.library.getLabelTree())
        self.ui.create_model(self.ui.source_tree, self.chart.source_library.getLabelTree(), typ="SourceTree")

        self.chart.sigNodeChanged.connect(self.ui.setPending)
        self.chart.sigNodeChanged.connect(self._markUnsaved)

        self.features = Features(self.graphCommHandler)

        self.ui.actionNew.triggered.connect(self.clear)
        self.ui.actionOpen.triggered.connect(self.openClicked)
        self.ui.actionSave.triggered.connect(self.saveClicked)
        self.ui.actionSaveAs.triggered.connect(self.saveAsClicked)

        if configure:
            self.ui.actionConfigure.triggered.connect(self.configureClicked)
        self.ui.actionApply.triggered.connect(self.applyClicked)
        self.ui.actionReset.triggered.connect(self.resetClicked)
        if HAS_QTCONSOLE:
            self.ui.actionConsole.triggered.connect(self.consoleClicked)
        self.ui.actionAgent.triggered.connect(self.agentClicked)

        self.ui.actionHome.triggered.connect(self.homeClicked)
        self.ui.actionArrange.triggered.connect(self.arrangeClicked)
        self.ui.navGroup.triggered.connect(self.navClicked)

        self.chart.sigFileLoaded.connect(self.setCurrentFile)
        self.chart.sigFileSaved.connect(self.setCurrentFile)

        self.sourceConfigure = SourceConfiguration(parent=self)
        self.sourceConfigure.sigApply.connect(self.configureApply)

        self.libraryEditor = EditorTemplate.LibraryEditor(self, chart.library, chart.subgraph_library)
        self.libraryEditor.sigApplyClicked.connect(self.libraryUpdated)
        self.libraryEditor.sigReloadClicked.connect(self.libraryReloaded)
        self.ui.libraryConfigure.clicked.connect(self.libraryEditor.show)

        self.ui.subgraph_tree.customContextMenuRequested.connect(self._onSubgraphTreeContextMenu)

        self.ipython_widget = None
        self.graph_info = pc.Info("ami_graph", "AMI Client graph", ["hutch", "name"])
        self.graph_version = pc.Gauge("ami_graph_version", "AMI Client graph version", ["hutch", "name"])

        # Eager AmiCli initialization for MCP server
        from ami.amicli import AmiCli
        from ami.comm import GraphCommHandler

        graphCommHandler = GraphCommHandler(self.graphmgr_addr.name, self.graphmgr_addr.comm)
        self.amicli = AmiCli(self, self.chartWidget, self.chart, graphCommHandler)

        # Start MCP server now that amicli exists
        self.chartWidget._start_mcp_server(self.amicli)

    @asyncSlot()
    async def applyClicked(self, build_views=True):
        graph_nodes = []
        disconnectedNodes = []
        displays = set()

        msg = QtWidgets.QMessageBox(parent=self)
        msg.setText("Failed to submit graph! See status.")

        if self.chart.deleted_nodes:
            await self.graphCommHandler.remove(self.chart.deleted_nodes)
            self.chart.deleted_nodes = []

        # detect if the manager has no graph (e.g. from a purge on failure)
        if await self.graphCommHandler.graphVersion == 0:
            # mark all the nodes as changed to force a resubmit of the whole graph
            for name, node in self.chart._graph.nodes(data="node"):
                if node is None:
                    continue
                node.changed = True

            # reset reference counting on views
            await self.features.reset()

        changed_nodes = set()
        failed_nodes = set()
        seen = set()

        for name, gnode in self.chart._graph.nodes(data="node"):
            if gnode is None or not gnode.enabled():
                continue

            if not gnode.hasInput():
                disconnectedNodes.append(gnode)
                continue
            elif gnode.exception:
                gnode.clearException()
                gnode.recolor()

            if gnode.changed and gnode not in changed_nodes:
                changed_nodes.add(gnode)

                if not hasattr(gnode, "to_operation"):
                    if gnode.viewable() and gnode.viewed:
                        displays.add(gnode)
                    elif gnode.exportable():
                        try:
                            assert gnode.values["alias"]
                        except AssertionError:
                            gnode.setException("set alias!")
                            self.chartWidget.updateStatus(f"{gnode.name()} set alias!", color="red")
                            continue
                        try:
                            assert gnode.values["alias"] != gnode.input_vars()["In"]
                        except AssertionError:
                            gnode.setException("alias name cannot be same as input!")
                            self.chartWidget.updateStatus(
                                f"{gnode.name()} alias name cannot be same as input!", color="red"
                            )
                            continue
                        displays.add(gnode)

                    continue

                outputs = [name]
                outputs.extend(nx.algorithms.dag.descendants(self.chart._graph, name))

                for output in outputs:
                    gnode = self.chart._graph.nodes[output]
                    node = gnode["node"]

                    if hasattr(node, "to_operation") and node not in seen:
                        try:
                            nodes = node.to_operation(
                                inputs=node.input_vars(),
                                outputs=node.output_vars(),
                                parent=node.name(),
                                latched=node.latched,
                            )
                        except Exception as e:
                            self.chartWidget.updateStatus(f"{node.name()} {e}!", color="red")
                            printExc(f"{node.name()} raised exception! See console for stacktrace.")
                            node.setException(str(e))
                            failed_nodes.add(node)
                            continue

                        seen.add(node)

                        if type(nodes) is list:
                            graph_nodes.extend(nodes)
                        else:
                            graph_nodes.append(nodes)

                    if (node.viewable() or node.buffered()) and node.viewed:
                        displays.add(node)

        if disconnectedNodes:
            for node in disconnectedNodes:
                self.chartWidget.updateStatus(f"{node.name()} disconnected!", color="red")
                node.setException("disconnected!")
            msg.show()
            return

        if failed_nodes:
            self.chartWidget.updateStatus("failed to submit graph", color="red")
            msg.exec()
            return

        if graph_nodes:
            await self.graphCommHandler.add(graph_nodes)
            node_names = ", ".join(set(map(lambda node: node.parent, graph_nodes)))
            self.chartWidget.updateStatus(f"Submitted {node_names}")

        node_names = ", ".join(set(map(lambda node: node.name(), displays)))
        if displays and build_views:
            self.chartWidget.updateStatus(f"Redisplaying {node_names}")
            await self.chartWidget.build_views(displays, export=True, redisplay=True)

        for node in changed_nodes:
            node.changed = False

        self.metadata = await self.graphCommHandler.metadata
        self.ui.setPendingClear()
        version = str(await self.graphCommHandler.graphVersion)
        state = self.chart.saveState()
        state = json.dumps(state, indent=2, separators=(",", ": "), sort_keys=False, cls=TypeEncoder)

        ts = datetime.now().strftime("%d%m%Y_%H%M%S")
        with open(os.path.expanduser(f"~/.cache/ami/autosave_{ts}.fc"), "w") as f:
            f.write(state)
            f.write("\n")

        self.graph_info.labels(self.chart.hutch, self.graph_name).info({"graph": state, "version": version})
        self.graph_version.labels(self.chart.hutch, self.graph_name).set(version)

    def openClicked(self):
        startDir = self.chart.filePath
        if startDir is None:
            startDir = "."
        self.fileDialog = FileDialog(None, "Load Flowchart..", startDir, "Flowchart (*.fc)")
        self.fileDialog.show()
        self.fileDialog.fileSelected.connect(self.chart.loadFile)

    def saveClicked(self):
        if self.currentFileName is None:
            self.saveAsClicked()
        else:
            try:
                self.chart.saveFile(self.currentFileName)
            except Exception as e:
                raise e

    def saveAsClicked(self):
        try:
            if self.currentFileName is None:
                self.chart.saveFile()
            else:
                self.chart.saveFile(suggestedFileName=self.currentFileName)
        except Exception as e:
            raise e

    def setCurrentFile(self, fileName):
        self.currentFileName = fileName
        if fileName is not None:
            self.unsaved_changes = False

    def _markUnsaved(self, node=None):
        self.unsaved_changes = True

    def homeClicked(self):
        children = self.viewBox().allChildren()
        self.viewBox().autoRange(items=children)

    def arrangeClicked(self):
        """Auto-arrange nodes using topological layered layout."""
        vm = self.viewManager()
        sg_name = vm._currentSubgraphName

        if sg_name and sg_name in self.chart._subgraphs:
            # Subgraph view
            sg_data = self.chart._subgraphs[sg_name]
            node_names = set(sg_data["nodes"])
            subgraph = self.chart._graph.subgraph(node_names)
            placeholder = sg_data["placeholder"]
        else:
            # Root view: exclude nodes inside subgraphs
            subgraph_nodes = set()
            for sg_data in self.chart._subgraphs.values():
                subgraph_nodes.update(sg_data["nodes"])
            root_nodes = set(self.chart._graph.nodes()) - subgraph_nodes
            subgraph = self.chart._graph.subgraph(root_nodes)
            placeholder = None

        if len(subgraph.nodes()) == 0:
            return

        # Assign layers via longest path (topological sort)
        layers = {node: 0 for node in subgraph.nodes()}
        try:
            for node in nx.topological_sort(subgraph):
                for successor in subgraph.successors(node):
                    layers[successor] = max(layers[successor], layers[node] + 1)
        except nx.NetworkXUnfeasible:
            from collections import deque

            sources = [n for n in subgraph.nodes() if subgraph.in_degree(n) == 0]
            if not sources:
                sources = list(subgraph.nodes())
            visited = set()
            queue = deque((s, 0) for s in sources)
            while queue:
                node, depth = queue.popleft()
                if node in visited:
                    layers[node] = max(layers[node], depth)
                    continue
                visited.add(node)
                layers[node] = depth
                for succ in subgraph.successors(node):
                    queue.append((succ, depth + 1))

        # Group by layer and position nodes
        layer_groups = {}
        for node, layer in layers.items():
            layer_groups.setdefault(layer, []).append(node)

        x_spacing = 300
        y_spacing = 200
        for layer_idx, nodes in sorted(layer_groups.items()):
            x = layer_idx * x_spacing
            y_offset = -(len(nodes) - 1) * y_spacing / 2
            for i, node_name in enumerate(nodes):
                y = y_offset + i * y_spacing
                p = (find_nearest(x), find_nearest(y))
                node = self.chart._graph.nodes[node_name]["node"]
                node.graphicsItem().setPos(*p)

        # Position visual boundary nodes for subgraph views
        if placeholder:
            max_layer = max(layer_groups.keys()) if layer_groups else 0
            if hasattr(placeholder, "subgraphInputs") and placeholder.subgraphInputs.graphicsItem().scene():
                placeholder.subgraphInputs.graphicsItem().setPos(find_nearest(-x_spacing), find_nearest(0))
            if hasattr(placeholder, "subgraphOutputs") and placeholder.subgraphOutputs.graphicsItem().scene():
                placeholder.subgraphOutputs.graphicsItem().setPos(
                    find_nearest((max_layer + 1) * x_spacing), find_nearest(0)
                )

        children = self.viewBox().allChildren()
        self.viewBox().autoRange(items=children)

    def navClicked(self, action):
        if action == self.ui.actionPan:
            self.viewBox().setMouseMode("Pan")
        elif action == self.ui.actionSelect:
            self.viewBox().setMouseMode("Select")
        elif action == self.ui.actionComment:
            self.viewBox().setMouseMode("Comment")

    @asyncSlot()
    async def resetClicked(self):
        await self.graphCommHandler.destroy()

        for name, gnode in self.chart._graph.nodes(data="node"):
            if gnode is None:
                continue
            gnode.changed = True

        await self.applyClicked()

    def scene(self):
        # returns the GraphicsScene object
        return self.chartWidget.scene()

    def viewBox(self):
        return self.chartWidget.viewBox()

    def viewManager(self):
        return self.chartWidget.viewManager

    def chartWidget(self):
        return self.chartWidget

    @asyncSlot()
    async def clear(self):
        await self.graphCommHandler.destroy()
        await self.chart.clear()
        self.chartWidget.clear()
        self.setCurrentFile(None)
        self.unsaved_changes = False
        self.chart.sigFileLoaded.emit(None)
        self.features = Features(self.graphCommHandler)
        await self.graphCommHandler.updatePlots(self.features.plots)

    def configureClicked(self):
        self.sourceConfigure.show()

    if HAS_QTCONSOLE:

        def consoleClicked(self):
            if self.ipython_widget is None:
                kernel_manager = QtInProcessKernelManager()
                kernel_manager.start_kernel(show_banner=False)
                kernel = kernel_manager.kernel
                kernel.gui = "qt"

                kernel_client = kernel_manager.client()
                kernel_client.start_channels()

                self.ipython_widget = RichJupyterWidget()
                self.ipython_widget.setWindowTitle("AMI Console")
                self.ipython_widget.kernel_manager = kernel_manager
                self.ipython_widget.kernel_client = kernel_client

            # Use the eagerly-initialized amicli from __init__
            self.ipython_widget.kernel_manager.kernel.shell.push({"amicli": self.amicli})
            win = QtWidgets.QMainWindow(parent=self)
            win.setCentralWidget(self.ipython_widget)
            win.show()

        def agentClicked(self):
            """Spawn external agent harness connected to AMI's MCP server."""
            import shutil
            import subprocess

            mcp_thread = getattr(self.chartWidget, "mcp_thread", None)
            if not mcp_thread or not hasattr(mcp_thread, "_tmpdir"):
                logger.error("MCP server not running - cannot spawn agent")
                return

            # Find available terminal emulator
            terminal_cmd = None
            for cmd in [
                ["xterm", "-e"],
                ["gnome-terminal", "--"],
                ["konsole", "-e"],
                ["xfce4-terminal", "-e"],
            ]:
                if shutil.which(cmd[0]):
                    terminal_cmd = cmd
                    break

            if not terminal_cmd:
                logger.error("No terminal emulator found (tried xterm, gnome-terminal, konsole, xfce4-terminal)")
                return

            # Spawn terminal running OpenCode pointed at temp dir with config
            try:
                subprocess.Popen(
                    [*terminal_cmd, "opencode", mcp_thread._tmpdir.name],
                )
                logger.info(f"Spawned agent in {mcp_thread._tmpdir.name}")
            except Exception as e:
                logger.error(f"Failed to spawn agent terminal: {e}")

    @asyncSlot(object)
    async def configureApply(self, src_cfg):
        missing = []

        if "files" in src_cfg:
            for f in src_cfg["files"]:
                if not os.path.exists(f):
                    missing.append(f)

        if not missing:
            await self.graphCommHandler.updateSources(src_cfg)
        else:
            missing = " ".join(missing)
            self.chartWidget.updateStatus(f"Missing {missing}!", color="red")

    @asyncSlot()
    async def libraryUpdated(self):
        await self.chart.broker.send_string("library", zmq.SNDMORE)
        await self.chart.broker.send_pyobj(fcMsgs.Library(name=self.graph_name, paths=self.libraryEditor.node_paths))
        dirs = set(map(os.path.dirname, self.libraryEditor.node_paths))
        await self.graphCommHandler.updatePath(dirs)

        self.chartWidget.updateStatus("Loaded modules.")

    @asyncSlot(object)
    async def libraryReloaded(self, mods):
        smods = set(map(lambda mod: mod.__name__, mods))

        for name, node in self.chart._graph.nodes(data="node"):
            if node is None or node.__module__ not in smods:
                continue

            await self.chart.broker.send_string(node.name(), zmq.SNDMORE)
            await self.chart.broker.send_pyobj(fcMsgs.ReloadLibrary(name=node.name(), mods=smods))
            self.chartWidget.updateStatus(f"Reloaded {node.name()}.")

    def _onSubgraphTreeContextMenu(self, pos):
        """Show context menu for subgraph library tree items."""
        tree = self.ui.subgraph_tree
        index = tree.indexAt(pos)
        if not index.isValid():
            return

        template_name = index.data()
        if not self.chart.subgraph_library.hasSubgraph(template_name):
            return  # Clicked on a group header, not a template

        menu = QtWidgets.QMenu()
        remove_action = menu.addAction("Remove from Library")
        action = menu.exec_(tree.viewport().mapToGlobal(pos))

        if action == remove_action:
            self.chart.removeSubgraphFromLibrary(template_name)


class FlowchartWidget(dockarea.DockArea):
    """Includes the actual graphical flowchart and debugging interface"""

    def __init__(self, chart, ctrl):
        super().__init__()
        self.chart = chart
        self.ctrl = ctrl
        self.hoverItem = None
        self.current_displayed_node = None  # Track which node is shown in state panel

        #  build user interface (it was easier to do it here than via developer)
        self.viewManager = ViewManager(self, ctrl)
        self.viewManager.sigViewAdded.connect(self.viewAdded)
        self.viewManager.sigMakeSubgraphFromSelection.connect(self.makeSubgraphFromSelection)
        self.viewDock = dockarea.Dock("view", size=(1000, 600))
        self.viewDock.nStyle = ""
        self.viewDock.addWidget(self.viewManager)
        self.viewDock.hideTitleBar()
        self.addDock(self.viewDock)

        self.hoverText = QtWidgets.QTextEdit()
        self.hoverText.setReadOnly(True)
        self.hoverDock = dockarea.Dock("Hover Info", size=(1000, 20))
        self.hoverDock.addWidget(self.hoverText)
        self.addDock(self.hoverDock, "bottom")

        self.statusText = QtWidgets.QTextEdit()
        self.statusText.setReadOnly(True)
        self.statusDock = dockarea.Dock("Status", size=(1000, 20))
        self.statusDock.addWidget(self.statusText)
        self.addDock(self.statusDock, "bottom")

        self.scene().selectionChanged.connect(self.selectionChanged)
        self.scene().sigMouseHover.connect(self.hoverOver)

    def viewAdded(self, view):
        view.scene().selectionChanged.connect(self.selectionChanged)
        view.scene().sigMouseHover.connect(self.hoverOver)

    def makeSubgraphFromSelection(self, nodes):
        self.chart.makeSubgraphFromSelection(nodes)

    def reloadLibrary(self):
        self.operationMenu.triggered.disconnect(self.operationMenuTriggered)
        self.operationMenu = None
        self.subMenus = []
        self.chart.library.reload()
        self.buildMenu()

    def buildOperationMenu(self, pos=None):
        def buildSubMenu(node, rootMenu, subMenus, pos=None):
            for section, node in node.items():
                menu = QtWidgets.QMenu(section)
                rootMenu.addMenu(menu)
                if isinstance(node, OrderedDict):
                    buildSubMenu(node, menu, subMenus, pos=pos)
                    subMenus.append(menu)
                else:
                    act = rootMenu.addAction(section)
                    act.nodeType = section
                    act.pos = pos

        self.operationMenu = QtWidgets.QMenu()
        self.operationSubMenus = []
        buildSubMenu(self.chart.library.getNodeTree(), self.operationMenu, self.operationSubMenus, pos=pos)
        self.operationMenu.triggered.connect(self.operationMenuTriggered)
        return self.operationMenu

    def buildSourceMenu(self, pos=None):
        def buildSubMenu(node, rootMenu, subMenus, pos=None):
            for section, node in node.items():
                menu = QtWidgets.QMenu(section)
                rootMenu.addMenu(menu)
                if isinstance(node, OrderedDict):
                    buildSubMenu(node, menu, subMenus, pos=pos)
                    subMenus.append(menu)
                else:
                    act = rootMenu.addAction(section)
                    act.nodeType = section
                    act.pos = pos

        self.sourceMenu = QtWidgets.QMenu()
        self.sourceSubMenus = []
        buildSubMenu(self.chart.source_library.getSourceTree(), self.sourceMenu, self.sourceSubMenus, pos=pos)
        self.sourceMenu.triggered.connect(self.sourceMenuTriggered)
        return self.sourceMenu

    def scene(self):
        return self.viewManager.scene()  # the GraphicsScene item

    def viewBox(self):
        return self.viewManager.viewBox()  # the viewBox that items should be added to

    def operationMenuTriggered(self, action):
        nodeType = action.nodeType
        pos = self.viewBox().mouse_pos
        pos = (50 * round(pos.x() / 50), 50 * round(pos.y() / 50))
        self.chart.createNode(nodeType, pos=pos, prompt=True)

    def sourceMenuTriggered(self, action):
        node = action.nodeType
        if node not in self.chart._graph:
            pos = self.viewBox().mouse_pos
            pos = (50 * round(pos.x() / 50), 50 * round(pos.y() / 50))
            node_type = self.chart.source_library.getSourceType(node)
            node = SourceNode(name=node, terminals={"Out": {"io": "out", "ttype": node_type}})
            self.chart.addNode(node=node, pos=pos)

    @asyncSlot()
    async def selectionChanged(self):
        # print "FlowchartWidget.selectionChanged called."
        items = self.scene().selectedItems()

        if len(items) != 1:
            return

        item = items[0]
        if not hasattr(item, "node"):
            return

        node = item.node
        self.updateNodeStatePanel(items[0].node)

        if not node.enabled():
            return

        if isinstance(node, SubgraphNode):
            action = self.viewManager.actions[node.name()]
            action.setChecked(True)
            action.triggered.emit()
            return

        if not hasattr(node, "display"):
            return

        if node.viewable():
            inputs = [n for n, d, in self.chart._graph.in_degree() if d == 0]
            seen = set()
            pending = set()

            for in_node in inputs:
                paths = list(nx.algorithms.all_simple_paths(self.chart._graph, in_node, node.name()))
                for path in paths:
                    for gnode in path:
                        gnode = self.chart._graph.nodes[gnode]
                        if "node" not in gnode:
                            continue
                        node = gnode["node"]
                        if node in seen:
                            continue
                        else:
                            seen.add(node)

                        if node.changed:
                            pending.add(node.name())

            if pending:
                pending = ", ".join(pending)
                msg = QtWidgets.QMessageBox(parent=self)
                msg.setText(f"Pending changes for {pending}. Please apply before trying to view.")
                msg.show()
                return

        await self.build_views([node], ctrl=True)
        self.ctrl.metadata = await self.ctrl.graphCommHandler.metadata

    async def build_views(self, nodes, ctrl=False, export=False, redisplay=False):
        views = {}
        display_args = []

        for node in nodes:
            name = node.name()

            node.display(topics=None, terms=None, addr=None, win=None)

            state = {}
            if hasattr(node.widget, "saveState"):
                state = node.widget.saveState()

            args = {
                "name": name,
                "state": state,
                "redisplay": redisplay,
                "geometry": node.geometry,
                "units": node.input_units(),
                "terminals": node.saveTerminals(),
                "label": node._label,
            }

            if node.buffered():
                # buffered nodes are allowed to override their topics/terms
                # this is done because they may want to view intermediate values
                args["topics"] = node.buffered_topics()
                args["terms"] = node.buffered_terms()
                self.ctrl.features.add_plot(node, **args)

            elif isinstance(node, SourceNode) and node.viewable():
                new, topic = await self.ctrl.features.get(name, name)

                args["terms"] = node.input_vars()
                args["topics"] = {name: topic}

                if new:
                    views[name] = name
                    self.ctrl.features.add_plot(node, **args)

            elif isinstance(node, Node) and node.viewable():
                topics = {}

                if len(node.inputs()) != len(node.input_vars()):
                    continue

                if node.changed:
                    await self.ctrl.features.discard(name)

                new_plot = False
                for term, in_var in node.input_vars().items():
                    new, topic = await self.ctrl.features.get(node.name(), in_var)
                    topics[in_var] = topic
                    if new:
                        views[in_var] = node.name()
                        new_plot = True

                args["terms"] = node.input_vars()
                args["topics"] = topics

                if new_plot:
                    self.ctrl.features.add_plot(node, **args)

            elif isinstance(node, CtrlNode) and ctrl:
                args["terms"] = node.input_vars()
                args["topics"] = {}

            display_args.append(args)

            if node.exportable() and export:
                input_vars = node.input_vars()
                values = node.values
                if "eventid" in input_vars:
                    await self.ctrl.graphCommHandler.export(
                        [input_vars["In"], input_vars["eventid"]], [values["alias"], "_timestamp"], N=values["events"]
                    )
                elif "Timestamp" in input_vars:
                    await self.ctrl.graphCommHandler.export(
                        [input_vars["In"], input_vars["Timestamp"]], [values["alias"], "_timestamp"]
                    )

                if not ctrl:
                    display_args.pop()

            if not node.created:
                state = node.saveState()
                msg = fcMsgs.CreateNode(node.name(), node.__class__.__name__, state=state)
                await self.chart.broker.send_string(node.name(), zmq.SNDMORE)
                await self.chart.broker.send_pyobj(msg)
                node.created = True

        if views:
            await self.ctrl.graphCommHandler.view(views)

        for args in display_args:
            name = args["name"]
            await self.chart.broker.send_string(name, zmq.SNDMORE)
            await self.chart.broker.send_pyobj(fcMsgs.DisplayNode(**args))

        await self.ctrl.graphCommHandler.updatePlots(self.ctrl.features.plots)

    def hoverOver(self, items):
        obj = None

        for item in items:
            if isinstance(item, NodeGraphicsItem):
                obj = item.node
            if isinstance(item, TerminalGraphicsItem):
                obj = item.term
                break
            elif isinstance(item, ConnectionItem):
                obj = item
                break

        text = ""

        if isinstance(obj, Node) and not obj.isSource():
            node = obj

            # Special handling for SubgraphNode - show description
            if hasattr(node, "isSubgraph") and node.isSubgraph:
                subgraph_name = node.name()
                if subgraph_name in self.chart._subgraphs:
                    sg_data = self.chart._subgraphs[subgraph_name]
                    description = sg_data.get("description", "")
                    node_count = len(sg_data.get("nodes", []))

                    doc = f"Subgraph: {subgraph_name}"
                    if description:
                        doc += f"\n{description}"
                    doc += f"\n\nContains {node_count} node(s)"
                else:
                    doc = f"Subgraph: {subgraph_name}"
            else:
                # Regular node handling
                doc = node.__doc__
                doc = doc.lstrip().rstrip()
                doc = re.sub(r"(\t+)|(  )+", "", doc)

            text = [doc]

            if not (hasattr(node, "isSubgraph") and node.isSubgraph) and node.inputs():
                text.append("\nInputs:")

            for name, term in node.inputs().items():
                term = term()
                connections = []
                connections.append(f"{node.name()}.{name}")

                if term.unit():
                    connections.append(f"in {term.unit()}")

                if term.inputTerminals():
                    connections.append("connected to:")
                else:
                    connections.append(f"accepts type: {term.type()}")

                for in_term in term.inputTerminals():
                    connections.append(f"{in_term.node().name()}.{in_term.name()}")
                text.append(" ".join(connections))

            if node.outputs():
                text.append("\nOutputs:")

            for name, term in node.outputs().items():
                term = term()
                connections = []
                connections.append(f"{node.name()}.{name}")

                if term.unit():
                    connections.append(f"in {term.unit()}")

                if term.dependentTerms():
                    connections.append("connected to:")
                else:
                    connections.append(f"emits type: {term.type()}")

                for in_term in term.dependentTerms():
                    connections.append(f"{in_term.node().name()}.{in_term.name()}")
                text.append(" ".join(connections))

            text = "\n".join(text)

        elif isinstance(obj, Terminal):
            term = obj
            node = obj.node()
            text = f"Term: {node.name()}.{term.name()}\nType: {term.type()}"

            if term.unit():
                text += f"\nUnit: {term.unit()}"

            terms = None

            if term.isOutput and term.dependentTerms():
                terms = term.dependentTerms()
            elif term.isInput and term.inputTerminals():
                terms = term.inputTerminals()

            if terms:
                connections = ["Connected to:"]
                for in_term in terms:
                    connections.append(f"{in_term.node().name()}.{in_term.name()}")
                connections = " ".join(connections)
                text = "\n".join([text, connections])
            # self.hoverLabel.setCursorPosition(0)
        elif isinstance(obj, ConnectionItem):
            connection = obj
            source = None
            target = None

            if isinstance(connection.source, TerminalGraphicsItem):
                source = connection.source.term
            if isinstance(connection.target, TerminalGraphicsItem):
                target = connection.target.term

            if source and target:
                prefix = f"from {source.node().name()}.{source.name()} to {target.node().name()}.{target.name()}\n"
                from_node = f"\nfrom: {source.node().name()}.{source.name()} type: {source.type()}"
                if source.unit():
                    from_node += f" unit: {source.unit()}"
                to_node = f"\nto: {target.node().name()}.{target.name()} type: {target.type()}"
                if target.unit():
                    to_node += f" unit: {target.unit()}"
                text = " ".join(["Connection", prefix, from_node, to_node])

        if text:
            self.hoverText.setPlainText(text)

        # Update state panel when hovering over a node
        # Don't clear when hovering off - keep last displayed node
        if isinstance(obj, Node):
            self.updateNodeStatePanel(obj)

    def clear(self):
        self.hoverText.setPlainText("")

    def updateNodeStatePanel(self, node):
        """Update the state panel to show the given node's state.

        Args:
            node: Node instance to display, or None to clear
        """
        # Get reference to state widget
        state_widget = self.ctrl.ui.state_widget

        # Disconnect from previous node's sigStateChanged signal
        if self.current_displayed_node:
            if hasattr(self.current_displayed_node, "sigStateChanged"):
                try:
                    self.current_displayed_node.sigStateChanged.disconnect(self.refreshStatePanel)
                except (TypeError, RuntimeError):
                    pass  # Signal already disconnected or object deleted

        # Update current node reference
        self.current_displayed_node = node

        # Clear or display
        if node is None:
            state_widget.clear()
            return

        # Display the node's state
        state_widget.displayNodeState(node)

        # Connect to sigStateChanged for live updates (CtrlNodes only)
        if hasattr(node, "sigStateChanged"):
            node.sigStateChanged.connect(self.refreshStatePanel)

    def refreshStatePanel(self, node=None):
        """Refresh the state panel for the currently displayed node.

        Args:
            node: Optional node parameter (from signal), uses current_displayed_node if None
        """
        if node is None:
            node = self.current_displayed_node
        if node:
            self.ctrl.ui.state_widget.displayNodeState(node)

    def updateStatus(self, text, color="black"):
        now = datetime.now().strftime("%H:%M:%S")
        if STYLE.get("Theme", None) == "dark" and color == "black":
            color = "#fff"
        self.statusText.insertHtml(f"<font color={color}>[{now}] {text}</font>")
        self.statusText.append("")

    def _start_mcp_server(self, amicli):
        """Start MCP server thread for AI-assisted graph building."""
        import os

        if os.environ.get("AMI_DISABLE_MCP"):
            return
        try:
            from ami.mcp_server import McpServerThread
            from ami.qt_dispatch import QtDispatcher

            self.qt_dispatcher = QtDispatcher()
            self.mcp_thread = McpServerThread(amicli=amicli, qt_dispatch_fn=self.qt_dispatcher.dispatch)
            self.mcp_thread.start()
            self._mcp_port = self.mcp_thread.port
        except ImportError:
            logger.info("MCP package not installed - AI agent support disabled")
        except Exception as e:
            logger.warning(f"Could not start MCP server: {e}")


class Features(object):

    def __init__(self, graphCommHandler):
        self.features_count = collections.defaultdict(set)
        self.features = {}
        self.plots = {}
        self.graphCommHandler = graphCommHandler
        self.lock = asyncio.Lock()

    async def get(self, name, in_var):
        async with self.lock:
            if in_var in self.features:
                topic = self.features[in_var]
                new = False
            else:
                topic = self.graphCommHandler.auto(in_var)
                self.features[in_var] = topic
                new = True

            self.features_count[in_var].add(name)
            return new, topic

    async def discard(self, name, in_var=None):
        async with self.lock:
            if in_var and in_var in self.features_count:
                self.features_count[in_var].discard(name)
                if not self.features_count[in_var]:
                    del self.features[in_var]
                    del self.features_count[in_var]
                    self.plots.pop(name, None)
                return True
            else:
                for in_var, viewers in self.features_count.items():
                    viewers.discard(name)
                    if not viewers and name in self.features:
                        del self.features[name]
                        self.plots.pop(name, None)
                return True

        return False

    def add_plot(self, node, **kwargs):
        self.plots[node.name()] = node.plotMetadata(**kwargs)

    def remove_plot(self, name):
        return self.plots.pop(name, None)

    async def reset(self):
        async with self.lock:
            self.features = {}
            self.features_count = collections.defaultdict(set)
            self.plots = {}
