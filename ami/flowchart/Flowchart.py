# -*- coding: utf-8 -*-
from datetime import datetime
from qtpy import QtCore, QtWidgets, QtGui
from pyqtgraph import FileDialog
from pyqtgraph.debug import printExc
from pyqtgraph import dockarea as dockarea
from collections import OrderedDict
from ami import LogConfig
from ami.asyncqt import asyncSlot
from ami.flowchart.FlowchartGraphicsView import ViewManager
from ami.flowchart.Terminal import Terminal, TerminalGraphicsItem, ConnectionItem
from ami.flowchart.library import LIBRARY
from ami.flowchart.library.common import SourceNode, CtrlNode
from ami.flowchart.library.Editors import STYLE
from ami.flowchart.Node import Node, NodeGraphicsItem, find_nearest
from ami.flowchart.SubgraphNode import SubgraphNode
from ami.flowchart.SubgraphLibrary import SubgraphLibrary
from ami.flowchart.NodeLibrary import SourceLibrary
from ami.flowchart.SourceConfiguration import SourceConfiguration
from ami.flowchart.TypeEncoder import TypeEncoder
from ami.comm import AsyncGraphCommHandler, GraphCommHandler
from ami.client import flowchart_messages as fcMsgs
try:
    from qtconsole.rich_jupyter_widget import RichJupyterWidget
    from qtconsole.inprocess import QtInProcessKernelManager
    HAS_QTCONSOLE = True
except ImportError:
    HAS_QTCONSOLE = False

import ami.flowchart.Editor as EditorTemplate
import amitypes
import asyncio
import zmq.asyncio
import json
import subprocess
import re
import tempfile
import numpy as np
import networkx as nx
import itertools as it
import collections
import os
import typing  # noqa
import logging
import socket
import prometheus_client as pc


logger = logging.getLogger(LogConfig.get_package_name(__name__))


class Flowchart(QtCore.QObject):
    sigFileLoaded = QtCore.Signal(object)
    sigFileSaved = QtCore.Signal(object)
    sigNodeCreated = QtCore.Signal(object)
    sigNodeChanged = QtCore.Signal(object)
    # called when output is expected to have changed

    def __init__(self, name=None, filePath=None, library=None,
                 broker_addr="", graphmgr_addr="", checkpoint_addr="",
                 prometheus_dir=None, hutch="", configure=False):
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
        self.graphinfo.setsockopt_string(zmq.SUBSCRIBE, '')
        self.graphinfo.connect(graphmgr_addr.info)
        self.socks.append(self.graphinfo)

        self.checkpoint = self.ctx.socket(zmq.SUB)  # used to receive ctrlnode updates from processes
        self.checkpoint.setsockopt_string(zmq.SUBSCRIBE, '')
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
                with open(pth, 'w') as f:
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
        """Create a new Node and add it to this flowchart.
        """
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
        item.setZValue(self.nextZVal*2)
        self.nextZVal += 1
        self.viewBox().addItem(item)
        pos = (find_nearest(pos[0]), find_nearest(pos[1]))
        item.moveBy(*pos)
        subset = 1
        mod = node.__module__.split('.')[-1]
        if mod == 'common' and isinstance(node, SourceNode):
            subset = 0
        elif mod == 'Display':
            subset = 2
        # Don't add visual-only nodes (like SubgraphNode) to self._graph
        if not getattr(node, 'is_visual_only', False):
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
            source_kwargs = node.graphicsItem().source_kwargs
            node.graphicsItem().sigSourceKwargs.connect(self.send_requested_data)

        self.sigNodeCreated.emit(node)
        if node.isChanged(True, True):
            self.sigNodeChanged.emit(node)

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
            n = 0
            while True:
                default_name = f"subgraph.{n}"
                if default_name not in self._graph.nodes():
                    break
                n += 1
        else:
            default_name = name
        
        # Show dialog for name and description
        if name is None or description is None:
            name, description = self._showExportDialog(default_name, '', isImport=False)
            if not name:
                # User cancelled
                return None

        # Create view for this subgraph
        view = self.viewManager().addView(name)
        
        # Create SubgraphNode placeholder (visual only, not in self._graph)
        subgraphNode = SubgraphNode(name, children=nodes, flowchart=self)
        subgraphNode.sigClosed.connect(self.nodeClosed)
        subgraphNode.setGraph(graph)
        
        names = list(map(lambda node: node.name(), nodes))
        
        # Analyze connections to find boundary crossings
        boundary_connections = []
        internal_connections = []
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
            external_node = graph.nodes[fnode_name]['node']
            internal_node = graph.nodes[tnode_name]['node']
            external_term = external_node.terminals[data['from_term']]
            internal_term = internal_node.terminals[data['to_term']]
            
            # Get the original connection object
            original_conn = external_term.connections().get(internal_term)
            if not original_conn:
                continue
            
            # Create unique terminal name
            terminal_name = '.'.join([fnode_name, data['from_term']])
            
            # Track unique inputs
            if terminal_name not in inputs:
                # Add input terminal to placeholder
                subgraphNode.addInput(name=terminal_name, ttype=external_term.type())
                inputs.add(terminal_name)
                
                if input_pos is None:
                    input_pos = external_node.graphicsItem().pos()
            
            # Store boundary connection info
            boundary_connections.append({
                'type': 'input',
                'external_node': external_node,
                'external_term': external_term,
                'internal_node': internal_node,
                'internal_term': internal_term,
                'original_connection': original_conn,
                'terminal_name': terminal_name
            })
        
        # Find output boundary connections (connections going OUT of the subgraph)
        for fnode_name, tnode_name, data in graph.out_edges(names, data=True):
            # Skip internal connections
            if fnode_name in names and tnode_name in names:
                continue
            
            # This is a boundary connection
            internal_node = graph.nodes[fnode_name]['node']
            external_node = graph.nodes[tnode_name]['node']
            internal_term = internal_node.terminals[data['from_term']]
            external_term = external_node.terminals[data['to_term']]
            
            # Get the original connection object
            original_conn = internal_term.connections().get(external_term)
            if not original_conn:
                continue
            
            # Create unique terminal name
            terminal_name = '.'.join([fnode_name, data['from_term']])
            
            # Track unique outputs
            if terminal_name not in outputs:
                # Add output terminal to placeholder
                subgraphNode.addOutput(name=terminal_name, ttype=internal_term.type())
                outputs.add(terminal_name)
                
                if output_pos is None:
                    output_pos = external_node.graphicsItem().pos()
            
            # Store boundary connection info
            boundary_connections.append({
                'type': 'output',
                'external_node': external_node,
                'external_term': external_term,
                'internal_node': internal_node,
                'internal_term': internal_term,
                'original_connection': original_conn,
                'terminal_name': terminal_name
            })
        
        # Add placeholder to root view FIRST (before creating connections to it)
        placeholder_item = subgraphNode.graphicsItem()
        self.viewBox().addItem(placeholder_item)
        if pos:
            placeholder_item.moveBy(*pos)
        else:
            placeholder_item.moveBy(nodes[0].graphicsItem().pos().x(), nodes[0].graphicsItem().pos().y())
        
        # Position SubgraphInput/Output nodes in subgraph view FIRST
        if inputs and input_pos:
            view.viewBox().addItem(subgraphNode.subgraphInputs.graphicsItem())
            subgraphNode.subgraphInputs.graphicsItem().moveBy(input_pos.x(), input_pos.y())
        if outputs and output_pos:
            view.viewBox().addItem(subgraphNode.subgraphOutputs.graphicsItem())
            subgraphNode.subgraphOutputs.graphicsItem().moveBy(output_pos.x(), output_pos.y())
        
        # NOW process boundary connections - create visual-only connections
        # Track which SubgraphInput/Output terminals we've already created
        sg_input_terms_created = {}  # internal_term_name -> terminal
        sg_output_terms_created = {}  # internal_term_name -> terminal
        
        for bc in boundary_connections:
            # Hide the original connection (remove from scene, but keep in Terminal._connections)
            if bc['original_connection'].scene() is not None:
                bc['original_connection'].scene().removeItem(bc['original_connection'])
            
            # Get the placeholder terminal
            placeholder_term = subgraphNode.terminals[bc['terminal_name']]
            
            if bc['type'] == 'input':
                # SubgraphInput terminal should have same name as placeholder terminal
                sg_input_term_name = bc['terminal_name']
                
                # Check if terminal already exists on SubgraphInputs node
                if sg_input_term_name in subgraphNode.subgraphInputs.terminals:
                    sg_input_term = subgraphNode.subgraphInputs.terminals[sg_input_term_name]
                else:
                    # Only create if it doesn't exist
                    sg_input_term = subgraphNode.subgraphInputs.addOutput(
                        name=sg_input_term_name,
                        ttype=bc['internal_term'].type()
                    )
                
                # Always recolor terminal to white (visually connected)
                sg_input_term.recolor(QtGui.QColor(255, 255, 255))
                
                # Create visual connection in root view: external → placeholder
                root_visual = ConnectionItem(
                    bc['external_term'].graphicsItem(),
                    placeholder_term.graphicsItem()
                )
                self.viewBox().addItem(root_visual)
                
                # Create visual connection in subgraph view: subgraph_input → internal
                sg_visual = ConnectionItem(
                    sg_input_term.graphicsItem(),
                    bc['internal_term'].graphicsItem()
                )
                view.viewBox().addItem(sg_visual)
                
                # Recolor placeholder terminal to white (visually connected)
                placeholder_term.recolor(QtGui.QColor(255, 255, 255))
                
            else:  # output
                # SubgraphOutput terminal should have same name as placeholder terminal
                sg_output_term_name = bc['terminal_name']
                
                # Check if terminal already exists on SubgraphOutputs node
                if sg_output_term_name in subgraphNode.subgraphOutputs.terminals:
                    sg_output_term = subgraphNode.subgraphOutputs.terminals[sg_output_term_name]
                else:
                    # Only create if it doesn't exist
                    sg_output_term = subgraphNode.subgraphOutputs.addInput(
                        name=sg_output_term_name,
                        ttype=bc['internal_term'].type()
                    )
                
                # Always recolor terminal to white (visually connected)
                sg_output_term.recolor(QtGui.QColor(255, 255, 255))
                
                # Create visual connection in root view: placeholder → external
                root_visual = ConnectionItem(
                    placeholder_term.graphicsItem(),
                    bc['external_term'].graphicsItem()
                )
                self.viewBox().addItem(root_visual)
                
                # Create visual connection in subgraph view: internal → subgraph_output
                sg_visual = ConnectionItem(
                    bc['internal_term'].graphicsItem(),
                    sg_output_term.graphicsItem()
                )
                view.viewBox().addItem(sg_visual)
                
                # Recolor placeholder terminal to white (visually connected)
                placeholder_term.recolor(QtGui.QColor(255, 255, 255))
            
            # Store visual connection references
            bc['root_visual'] = root_visual
            bc['subgraph_visual'] = sg_visual
        
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
        
        # Store subgraph metadata
        self._subgraphs[name] = {
            'nodes': names,
            'placeholder': subgraphNode,
            'view': view,
            'boundary_connections': boundary_connections,
            'internal_connections': internal_connections,
            'description': description or ''
        }
        
        # Set tooltip on placeholder to show description
        if description:
            subgraphNode.graphicsItem().setToolTip(description)
        
        # Display the subgraph view
        self.viewManager().displayView(name=subgraphNode.name(), autoRange=True)
        
        # Add to library
        self._addSubgraphToLibrary(name)

    def _showExportDialog(self, default_name, default_desc='', isImport=False):
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
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            return name_edit.text(), desc_edit.toPlainText()
        else:
            return None, None

    def _showNestedSubgraphWarning(self, num_subgraphs):
        """Show warning about nested subgraphs not being supported
        
        Returns:
            True if user accepts, False if cancelled
        """
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowTitle("Nested Subgraphs Not Supported")
        msg.setText(
            f"This flowchart contains {num_subgraphs} subgraph(s).\n\n"
            "Nested subgraphs are not yet supported. "
            "The flowchart will be imported as a flat subgraph "
            "with all nodes at the same level.\n\n"
            "Original subgraph structure will be lost."
        )
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
        )
        msg.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        
        return msg.exec_() == QtWidgets.QMessageBox.Ok

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

    def _createSubgraphFromImport(self, name, nodes, boundary_inputs, boundary_outputs, 
                                   node_mapping, pos=None, description=None, view=None):
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
            view: Pre-created subgraph view (if None, creates one)
        """
        from qtpy import QtGui, QtCore
        from ami.flowchart.Terminal import ConnectionItem
        
        # Step 1: Use provided view or create new one
        if view is None:
            view = self.viewManager().addView(name)
        
        subgraphNode = SubgraphNode(name, children=nodes, flowchart=self)
        subgraphNode.sigClosed.connect(self.nodeClosed)
        subgraphNode.setGraph(self._graph)
        
        # Switch to root view to add placeholder there
        self.viewManager().displayView(name='root')
        
        # Add placeholder to root view
        placeholder_item = subgraphNode.graphicsItem()
        self.viewBox().addItem(placeholder_item)
        if pos:
            if isinstance(pos, QtCore.QPointF):
                # Snap to grid
                snapped_pos = (find_nearest(pos.x()), find_nearest(pos.y()))
                placeholder_item.moveBy(*snapped_pos)
            else:
                # Snap to grid
                snapped_pos = (find_nearest(pos[0]), find_nearest(pos[1]))
                placeholder_item.moveBy(*snapped_pos)
        else:
            # Default position based on first node (also snapped to grid)
            if nodes:
                first_pos = nodes[0].graphicsItem().pos()
                snapped_pos = (find_nearest(first_pos.x()), find_nearest(first_pos.y()))
                placeholder_item.moveBy(*snapped_pos)
        
        # Switch back to subgraph view for creating helper nodes
        self.viewManager().displayView(name=name)
        
        # Step 2: Create placeholder terminals and track boundary connections
        boundary_connections = []
        
        # Process boundary inputs
        for boundary_input in boundary_inputs:
            term_name = boundary_input['placeholder_terminal']
            
            # Parse ttype (might be string representation)
            ttype_str = boundary_input['ttype']
            ttype = eval(ttype_str) if isinstance(ttype_str, str) else ttype_str
            
            # Add input terminal to placeholder (also creates SubgraphInput terminal)
            subgraphNode.addInput(name=term_name, ttype=ttype)
            placeholder_term = subgraphNode.terminals[term_name]
            sg_input_term = subgraphNode.subgraphInputs.terminals[term_name]
            
            # Check if this boundary should be visually connected to internal node
            internal_node_name = boundary_input.get('internal_node')
            internal_term_name = boundary_input.get('internal_terminal')
            
            if internal_node_name and internal_term_name:
                # Remap old node name to new node name
                if internal_node_name not in node_mapping:
                    logger.warning(f"Boundary input references unknown node {internal_node_name}")
                    continue
                
                new_node_name = node_mapping[internal_node_name]
                
                if new_node_name not in self._graph.nodes:
                    logger.warning(f"Remapped node {new_node_name} not in graph")
                    continue
                
                internal_node = self._graph.nodes[new_node_name]['node']
                
                # Validate terminal exists
                if internal_term_name not in internal_node.terminals:
                    logger.warning(f"Node {new_node_name} missing terminal {internal_term_name}")
                    continue
                
                internal_term = internal_node.terminals[internal_term_name]
                
                # Store boundary connection info (will create visual connection later)
                boundary_connections.append({
                    'type': 'input',
                    'terminal_name': term_name,
                    'internal_node': internal_node,
                    'internal_term': internal_term,
                })
        
        # Process boundary outputs (similar to inputs)
        for boundary_output in boundary_outputs:
            term_name = boundary_output['placeholder_terminal']
            ttype_str = boundary_output['ttype']
            ttype = eval(ttype_str) if isinstance(ttype_str, str) else ttype_str
            
            # Add output terminal to placeholder (also creates SubgraphOutput terminal)
            subgraphNode.addOutput(name=term_name, ttype=ttype)
            placeholder_term = subgraphNode.terminals[term_name]
            sg_output_term = subgraphNode.subgraphOutputs.terminals[term_name]
            
            internal_node_name = boundary_output.get('internal_node')
            internal_term_name = boundary_output.get('internal_terminal')
            
            if internal_node_name and internal_term_name:
                if internal_node_name not in node_mapping:
                    logger.warning(f"Boundary output references unknown node {internal_node_name}")
                    continue
                
                new_node_name = node_mapping[internal_node_name]
                
                if new_node_name not in self._graph.nodes:
                    logger.warning(f"Remapped node {new_node_name} not in graph")
                    continue
                
                internal_node = self._graph.nodes[new_node_name]['node']
                
                if internal_term_name not in internal_node.terminals:
                    logger.warning(f"Node {new_node_name} missing terminal {internal_term_name}")
                    continue
                
                internal_term = internal_node.terminals[internal_term_name]
                
                # Store boundary connection info (will create visual connection later)
                boundary_connections.append({
                    'type': 'output',
                    'terminal_name': term_name,
                    'internal_node': internal_node,
                    'internal_term': internal_term,
                })
        
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
        internal_connections = []
        
        for node in nodes:
            # Remove from root view
            item = node.graphicsItem()
            if item.scene() is not None:
                item.scene().removeItem(item)
            
            # Add to subgraph view
            view.viewBox().addItem(item)
            
            # Find internal connections (both endpoints in subgraph)
            for term_name, term in node.terminals.items():
                for remote_term, conn_item in term.connections().items():
                    remote_node = remote_term.node()
                    if remote_node in nodes:
                        # This is an internal connection
                        if conn_item not in internal_connections:
                            internal_connections.append(conn_item)
            
            node.recolor()
        
        # Move internal connections to subgraph view
        for conn in internal_connections:
            if conn.scene() is not None:
                conn.scene().removeItem(conn)
            view.viewBox().addItem(conn)
        
        # Step 5: Create visual ConnectionItems for boundary connections
        # These are in the subgraph view connecting helpers to internal nodes
        # NOW we can create connections since everything is in the view
        for bc in boundary_connections:
            internal_term = bc['internal_term']
            
            if bc['type'] == 'input':
                # SubgraphInput → Internal
                sg_input_term = subgraphNode.subgraphInputs.terminals[bc['terminal_name']]
                
                # Create visual-only connection (now that nodes are in the view)
                # Use signal=False so it doesn't create graph edges
                sg_input_term.connectTo(internal_term, signal=False)
                
                # Get the ConnectionItem that was just created
                conn_item = sg_input_term.connections().get(internal_term)
                if conn_item:
                    bc['subgraph_visual'] = conn_item
                    # Recolor terminal to show it's connected
                    sg_input_term.recolor(QtGui.QColor(255, 255, 255))
            else:  # output
                # Internal → SubgraphOutput
                sg_output_term = subgraphNode.subgraphOutputs.terminals[bc['terminal_name']]
                
                # Create visual-only connection (now that nodes are in the view)
                internal_term.connectTo(sg_output_term, signal=False)
                
                # Get the ConnectionItem that was just created
                conn_item = internal_term.connections().get(sg_output_term)
                if conn_item:
                    bc['subgraph_visual'] = conn_item
                    sg_output_term.recolor(QtGui.QColor(255, 255, 255))
        
        # Step 6: Store subgraph metadata
        names = [node.name() for node in nodes]
        
        self._subgraphs[name] = {
            'nodes': names,
            'placeholder': subgraphNode,
            'view': view,
            'boundary_connections': boundary_connections,
            'internal_connections': internal_connections,
            'description': description or ''
        }
        
        # Switch back to root view - user sees placeholder and can connect it
        self.viewManager().displayView(name='root')
        
        # Add to library
        self._addSubgraphToLibrary(name)
        
        logger.info(f"Created imported subgraph {name} with {len(nodes)} nodes")

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
        existing_desc = sg_data.get('description', '')
        name, desc = self._showExportDialog(subgraph_name, existing_desc)
        if not name:
            return
        
        # Show file dialog if no filename provided
        if fileName is None:
            fileName, _ = FileDialog.getSaveFileName(
                self.widget(),
                "Export Subgraph",
                f"{name}.fc",
                "Flowchart files (*.fc)"
            )
            if not fileName:
                return
        
        # Collect nodes in subgraph
        nodes = []
        for node_name in sg_data['nodes']:
            if node_name not in self._graph.nodes:
                continue
            node = self._graph.nodes[node_name]['node']
            nodes.append({
                'class': type(node).__name__,
                'name': node_name,
                'state': node.saveState()
            })
        
        # Collect internal connections only
        connects = []
        for from_node, to_node, data in self._graph.edges(data=True):
            if from_node in sg_data['nodes'] and to_node in sg_data['nodes']:
                connects.append((from_node, data['from_term'], 
                               to_node, data['to_term']))
        
        # Collect boundary input metadata
        boundary_inputs = []
        sg_placeholder = sg_data['placeholder']
        
        # Build mapping of placeholder terminal names to boundary connections
        input_bc_map = {}
        output_bc_map = {}
        
        for bc in sg_data['boundary_connections']:
            term_name = bc['terminal_name']
            if bc['type'] == 'input':
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
                    boundary_inputs.append({
                        'placeholder_terminal': input_term_name,
                        'internal_node': bc['internal_node'].name(),
                        'internal_terminal': bc['internal_term'].name(),
                        'ttype': ttype
                    })
            else:
                # No boundary connection - export disconnected
                boundary_inputs.append({
                    'placeholder_terminal': input_term_name,
                    'internal_node': None,
                    'internal_terminal': None,
                    'ttype': ttype
                })
        
        # Export boundary outputs
        boundary_outputs = []
        for output_term_name in sg_placeholder.outputs():
            placeholder_term = sg_placeholder.terminals[output_term_name]
            ttype = placeholder_term.type()  # Keep as class object - TypeEncoder will serialize it
            
            if output_term_name in output_bc_map:
                for bc in output_bc_map[output_term_name]:
                    boundary_outputs.append({
                        'placeholder_terminal': output_term_name,
                        'internal_node': bc['internal_node'].name(),
                        'internal_terminal': bc['internal_term'].name(),
                        'ttype': ttype
                    })
            else:
                boundary_outputs.append({
                    'placeholder_terminal': output_term_name,
                    'internal_node': None,
                    'internal_terminal': None,
                    'ttype': ttype
                })
        
        # Create state dict
        state = {
            'subgraph_metadata': {
                'name': name,
                'description': desc,
                'boundary_inputs': boundary_inputs,
                'boundary_outputs': boundary_outputs
            },
            'nodes': nodes,
            'connects': connects,
            'views': {
                'root': sg_data['view'].viewBox().saveState()
            }
        }
        
        # Save to file
        with open(fileName, 'w') as f:
            json.dump(state, f, indent=2, cls=TypeEncoder)
        
        if self._widget:
            self.widget().chartWidget.updateStatus(f"Exported subgraph to: {fileName}")
        logger.info(f"Exported subgraph {subgraph_name} to {fileName}")

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
            with open(fileName, 'r') as f:
                state = json.load(f)
        else:
            state = fileName  # Already a dict
        
        # Check for nested subgraphs
        if 'subgraphs' in state and state['subgraphs']:
            if not self._showNestedSubgraphWarning(len(state['subgraphs'])):
                return None
        
        # Generate unique subgraph name
        base_name = state.get('subgraph_metadata', {}).get('name', 'imported')
        if isinstance(fileName, str):
            base_name = base_name or os.path.splitext(os.path.basename(fileName))[0]
        name = self._generateUniqueSubgraphName(base_name)
        
        # Create subgraph view and switch to it
        subgraph_view = self.viewManager().addView(name)
        self.viewManager().displayView(name=name)
        
        # Restore nodes with unique names (will be created in subgraph view)
        node_mapping = {}  # old_name -> new_name
        restored_nodes = []
        
        for node_state in state.get('nodes', []):
            old_name = node_state.get('name')
            new_name = self._generateUniqueNodeName(old_name)
            
            try:
                # Create node
                if node_state['class'] == 'SourceNode':
                    # Handle SourceNode specially
                    terminals = node_state.get('state', {}).get('terminals', {})
                    # Eval ttype strings
                    for term_name, term_info in terminals.items():
                        if isinstance(term_info.get('ttype'), str):
                            term_info['ttype'] = eval(term_info['ttype'])
                    from ami.flowchart.library.common import SourceNode
                    node = SourceNode(name=new_name, terminals=terminals)
                    self.addNode(node=node)
                else:
                    node = self.createNode(node_state['class'], name=new_name, prompt=False)
                
                if node:
                    node_mapping[old_name] = node.name()  # Get actual assigned name
                    
                    node.blockSignals(True)
                    node.restoreState(node_state.get('state', {}))
                    node.blockSignals(False)
                    restored_nodes.append(node)
            except Exception:
                printExc(f"Error creating node {old_name}: (continuing anyway)")
                continue
        
        # Restore connections with mapped names
        for conn in state.get('connects', []):
            if len(conn) < 4:
                continue
            from_node, from_term, to_node, to_term = conn[0], conn[1], conn[2], conn[3]
            
            if from_node not in node_mapping or to_node not in node_mapping:
                continue
            
            try:
                from_node_obj = self._graph.nodes[node_mapping[from_node]]['node']
                to_node_obj = self._graph.nodes[node_mapping[to_node]]['node']
                
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
                    to_term=to_term
                )
            except Exception:
                printExc(f"Error connecting {from_node}.{from_term} to {to_node}.{to_term}")
                continue
        
        if not restored_nodes:
            logger.error("No nodes were successfully restored")
            return None
        
        # Create subgraph using import-specific function
        metadata = state.get('subgraph_metadata', {})
        self._createSubgraphFromImport(
            name=name,
            nodes=restored_nodes,
            boundary_inputs=metadata.get('boundary_inputs', []),
            boundary_outputs=metadata.get('boundary_outputs', []),
            node_mapping=node_mapping,
            pos=pos,
            description=metadata.get('description', ''),
            view=subgraph_view
        )
        
        # Switch back to root view
        self.viewManager().displayView(name='root')
        
        if self._widget:
            self.widget().chartWidget.updateStatus(f"Imported subgraph: {name}")
        logger.info(f"Imported subgraph {name} with {len(restored_nodes)} nodes")
        
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
            'subgraph_metadata': {
                'name': template.name,
                'description': template.description,
                'boundary_inputs': template.boundary_inputs,
                'boundary_outputs': template.boundary_outputs
            },
            'nodes': template.nodes,
            'connects': template.connects
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
        
        from ami.flowchart.SubgraphLibrary import SubgraphTemplate
        
        sg_data = self._subgraphs[subgraph_name]
        
        # Collect nodes in subgraph
        nodes = []
        for node_name in sg_data['nodes']:
            if node_name not in self._graph.nodes:
                continue
            node = self._graph.nodes[node_name]['node']
            nodes.append({
                'class': type(node).__name__,
                'name': node_name,
                'state': node.saveState()
            })
        
        # Collect internal connections only
        connects = []
        for from_node, to_node, data in self._graph.edges(data=True):
            if from_node in sg_data['nodes'] and to_node in sg_data['nodes']:
                connects.append((from_node, data['from_term'], 
                               to_node, data['to_term']))
        
        # Collect boundary metadata (for SubgraphTemplate)
        placeholder = sg_data['placeholder']
        boundary_inputs = []
        boundary_outputs = []
        
        for bc in sg_data.get('boundary_connections', []):
            if bc['type'] == 'input':
                term = placeholder.terminals.get(bc['terminal_name'])
                if term:
                    boundary_inputs.append({
                        'placeholder_terminal': bc['terminal_name'],
                        'internal_node': bc['internal_node'].name(),
                        'internal_terminal': bc['internal_term'].name(),
                        'ttype': term.type()
                    })
            else:  # output
                term = placeholder.terminals.get(bc['terminal_name'])
                if term:
                    boundary_outputs.append({
                        'placeholder_terminal': bc['terminal_name'],
                        'internal_node': bc['internal_node'].name(),
                        'internal_terminal': bc['internal_term'].name(),
                        'ttype': term.type()
                    })
        
        # Create state dict with boundary metadata
        state = {
            'nodes': nodes,
            'connects': connects,
            'subgraph_metadata': {
                'name': subgraph_name,
                'description': sg_data.get('description', ''),
                'boundary_inputs': boundary_inputs,
                'boundary_outputs': boundary_outputs
            }
        }
        
        # Create template
        description = sg_data.get('description', '') or "Subgraph created in flowchart"
        template = SubgraphTemplate(
            name=subgraph_name,
            description=description,
            state=state,
            source_file=None
        )
        
        # Add to library
        self.subgraph_library.addSubgraph(subgraph_name, template)
        
        # Update the UI tree
        self._updateSubgraphLibraryUI()
        
        # Show status message
        if self._widget:
            action = "Updated" if update else "Added"
            self.widget().chartWidget.updateStatus(f"{action} subgraph template: {subgraph_name}")
        
        logger.info(f"{action if update else 'Added'} subgraph {subgraph_name} to library")

    def _updateSubgraphLibraryUI(self):
        """Update the subgraph library tree in the UI (hierarchical by source file)"""
        if not self._widget:
            return
        
        ctrl = self.widget()
        
        # Check if UI has subgraph_tree attribute
        if not hasattr(ctrl.ui, 'subgraph_tree'):
            logger.debug("UI does not have subgraph_tree, skipping library update")
            return
        
        # Clear the tree
        ctrl.ui.clear_model(ctrl.ui.subgraph_tree)
        
        # Group subgraphs by source file
        from collections import defaultdict
        import os
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

    def _addRestoredSubgraphsToLibrary(self):
        """Add all subgraphs in the current flowchart to the library
        
        Called after restoring a flowchart to make the subgraphs available
        in the library tree for drag-and-drop.
        """
        if not self._widget:
            return
        
        from ami.flowchart.SubgraphLibrary import SubgraphTemplate
        
        for sg_name, sg_data in self._subgraphs.items():
            # Skip if already in library
            if self.subgraph_library.hasSubgraph(sg_name):
                continue
            
            # Collect nodes in subgraph
            nodes = []
            for node_name in sg_data['nodes']:
                if node_name not in self._graph.nodes:
                    continue
                node = self._graph.nodes[node_name]['node']
                nodes.append({
                    'class': type(node).__name__,
                    'name': node_name,
                    'state': node.saveState()
                })
            
            # Collect internal connections only
            connects = []
            for from_node, to_node, data in self._graph.edges(data=True):
                if from_node in sg_data['nodes'] and to_node in sg_data['nodes']:
                    connects.append((from_node, data['from_term'], 
                                   to_node, data['to_term']))
            
            # Create state dict
            state = {
                'nodes': nodes,
                'connects': connects
            }
            
            # Create template
            template = SubgraphTemplate(
                name=sg_name,
                description=sg_data.get('description', 'Subgraph from flowchart'),
                state=state,
                source_file=None
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
            if node_name in sg_data['nodes']:
                # Remove from subgraph
                sg_data['nodes'].remove(node_name)
                logger.info(f"Removed {node_name} from subgraph {sg_name}")
                
                # Auto-delete empty subgraphs
                if not sg_data['nodes']:
                    logger.info(f"Subgraph {sg_name} is empty, deleting")
                    # This will trigger SubgraphNode.close()
                    sg_data['placeholder'].close()
                    # Will be removed from self._subgraphs by close()
                    continue
                
                # Update boundary connections (remove connections involving this node)
                sg_data['boundary_connections'] = [
                    bc for bc in sg_data['boundary_connections']
                    if bc['internal_term'].node().name() != node_name
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

        if hasattr(node, 'to_operation'):
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
            if 'eventid' in input_vars:
                await ctrl.graphCommHandler.unexport([input_vars['In'], input_vars['eventid']],
                                                     [node.values['alias'], "_timestamp"])
            elif 'Timestamp' in input_vars:
                await ctrl.graphCommHandler.unexport([input_vars['In'], input_vars['Timestamp']],
                                                     [node.values['alias'], "_timestamp"])

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
        key = localNode + '.' + localTerm.name() + '->' + remoteNode + '.' + remoteTerm.name()



        # Check if connecting FROM SubgraphInput helper TO internal node
        if hasattr(remoteTerm.node(), 'isSubgraphInput') and remoteTerm.node().isSubgraphInput:
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
                        to_term=localTerm.name()
                    )
                    
                    # CRITICAL: Update internal node's _input_vars
                    localTerm.node().connected(localTerm, external_term)
                    
                    self.sigNodeChanged.emit(localTerm.node())
                    return
                else:
                    # No external connection yet, just create normal edge for now
                    pass

        # Check if connecting to/from a subgraph placeholder
        if hasattr(remoteTerm.node(), 'isSubgraph') and remoteTerm.node().isSubgraph:
            subgraph = remoteTerm.node()
            sg_data = self._subgraphs[subgraph.name()]
            
            if remoteTerm.isInput():
                # External -> Placeholder Input
                # Find matching boundary connection
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'input':
                        internal_node = bc['internal_node']
                        internal_term = bc['internal_term']
                        
                        # Create DIRECT graph edge: External -> Internal
                        edge_key = f"{localNode}.{localTerm.name()}->{internal_node.name()}.{internal_term.name()}"
                        
                        self._graph.add_edge(
                            localNode,
                            internal_node.name(),
                            key=edge_key,
                            from_term=localTerm.name(),
                            to_term=internal_term.name()
                        )
                        
                        # CRITICAL: Update internal node's _input_vars
                        internal_node.connected(internal_term, localTerm)
                        
                        self.sigNodeChanged.emit(localTerm.node())
                        return
            
            elif remoteTerm.isOutput():
                # Placeholder Output -> External
                # Find matching boundary connection
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'output':
                        internal_node = bc['internal_node']
                        internal_term = bc['internal_term']
                        
                        # Create DIRECT graph edge: Internal -> External
                        edge_key = f"{internal_node.name()}.{internal_term.name()}->{localNode}.{localTerm.name()}"
                        
                        self._graph.add_edge(
                            internal_node.name(),
                            localNode,
                            key=edge_key,
                            from_term=internal_term.name(),
                            to_term=localTerm.name()
                        )
                        
                        # Update external node's _input_vars
                        localTerm.node().connected(localTerm, internal_term)
                        
                        self.sigNodeChanged.emit(internal_node)
                        return

        if not self._graph.has_edge(localNode, remoteNode, key=key):
            self._graph.add_edge(localNode, remoteNode, key=key,
                                 from_term=localTerm.name(), to_term=remoteTerm.name())

            msg = fcMsgs.NodeTermConnected(localNode, isinstance(localTerm.node(), SourceNode),
                                           localTerm.name(), localTerm.saveState(),
                                           remoteNode, isinstance(remoteTerm.node(), SourceNode),
                                           remoteTerm.name(), remoteTerm.saveState())
            localTerm.node().terminalConnected(msg)
            await self.broker.send_string(localNode, zmq.SNDMORE)
            await self.broker.send_pyobj(msg)

            msg = fcMsgs.NodeTermConnected(remoteNode, isinstance(remoteTerm.node(), SourceNode),
                                           remoteTerm.name(), remoteTerm.saveState(),
                                           localNode, isinstance(localTerm.node(), SourceNode),
                                           localTerm.name(), localTerm.saveState())
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
        key = localNode + '.' + localTerm.name() + '->' + remoteNode + '.' + remoteTerm.name()

        # Check if disconnecting from a subgraph placeholder
        if hasattr(remoteTerm.node(), 'isSubgraph') and remoteTerm.node().isSubgraph:
            subgraph = remoteTerm.node()
            sg_data = self._subgraphs[subgraph.name()]
            
            if remoteTerm.isInput():
                # Disconnecting External -> Placeholder Input
                # Find matching boundary connection
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'input':
                        internal_node = bc['internal_node']
                        internal_term = bc['internal_term']
                        
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
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'output':
                        internal_node = bc['internal_node']
                        internal_term = bc['internal_term']
                        
                        edge_key = f"{internal_node.name()}.{internal_term.name()}->{localNode}.{localTerm.name()}"
                        
                        if self._graph.has_edge(internal_node.name(), localNode, key=edge_key):
                            self._graph.remove_edge(internal_node.name(), localNode, key=edge_key)
                        
                        # Update external node's _input_vars
                        localTerm.node().disconnected(localTerm, internal_term)
                        
                        self.sigNodeChanged.emit(internal_node)
                        return

        if self._graph.has_edge(localNode, remoteNode, key=key):
            self._graph.remove_edge(localNode, remoteNode, key=key)

            msg = fcMsgs.NodeTermDisconnected(localNode, isinstance(localTerm.node(), SourceNode),
                                              localTerm.name(), localTerm.saveState(),
                                              remoteNode, isinstance(remoteTerm.node(), SourceNode),
                                              remoteTerm.name(), remoteTerm.saveState())
            localTerm.node().terminalDisconnected(msg)
            await self.broker.send_string(localNode, zmq.SNDMORE)
            await self.broker.send_pyobj(msg)

            msg = fcMsgs.NodeTermDisconnected(remoteNode, isinstance(remoteTerm.node(), SourceNode),
                                              remoteTerm.name(), remoteTerm.saveState(),
                                              localNode, isinstance(localTerm.node(), SourceNode),
                                              localTerm.name(), localTerm.saveState())
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
                    node = self._graph.nodes[node]['node']
                    name = node.name()
                    node.nodeEnabled(enabled)
                    if not enabled:
                        if hasattr(node, 'to_operation'):
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
        state['nodes'] = []
        state['connects'] = []
        state['viewbox'] = self.viewBox().saveState()

        # Save regular nodes (skip visual-only nodes like SubgraphNode)
        for name, node in self.nodes(data='node'):
            # Skip if node is None (shouldn't happen, but be defensive)
            if node is None:
                continue
            # Skip visual-only nodes
            if getattr(node, 'is_visual_only', False):
                continue
            cls = type(node)
            clsName = cls.__name__
            ns = {'class': clsName, 'name': name, 'state': node.saveState()}
            state['nodes'].append(ns)

        for from_node, to_node, data in self._graph.edges(data=True):
            from_term = data['from_term']
            to_term = data['to_term']
            state['connects'].append((from_node, from_term, to_node, to_term))

        # NEW: Save subgraphs (visual-only metadata)
        state['subgraphs'] = []
        for sg_name, sg_data in self._subgraphs.items():
            placeholder_pos = sg_data['placeholder'].graphicsItem().pos()
            state['subgraphs'].append({
                'name': sg_name,
                'nodes': sg_data['nodes'],
                'placeholder_pos': (placeholder_pos.x(), placeholder_pos.y()),
                'description': sg_data.get('description', '')
            })
        
        # NEW: Save all view states (not just root)
        state['views'] = {}
        for view_name, view in self.viewManager().views.items():
            state['views'][view_name] = view.viewBox().saveState()

        state['source_configuration'] = self.widget().sourceConfigure.saveState()
        state['library'] = self.widget().libraryEditor.saveState()
        return state

    def restoreState(self, state):
        """
        Restore the state of this flowchart from a previous call to `saveState()`.
        """
        if 'source_configuration' in state:
            src_cfg = state['source_configuration']
            self.widget().sourceConfigure.restoreState(src_cfg)
            if src_cfg['files']:
                self.widget().sourceConfigure.applyClicked()

        if 'library' in state:
            lib_cfg = state['library']
            self.widget().libraryEditor.restoreState(lib_cfg)
            self.widget().libraryEditor.applyClicked()

        if 'viewbox' in state:
            self.viewBox().restoreState(state['viewbox'])

        nodes = state['nodes']
        nodes.sort(key=lambda a: a['state']['pos'][0])
        for n in nodes:
            if n['class'] == 'SourceNode':
                try:
                    ttype = eval(n['state']['terminals']['Out']['ttype'])
                    n['state']['terminals']['Out']['ttype'] = ttype
                    node = SourceNode(name=n['name'], terminals=n['state']['terminals'])
                    self.addNode(node=node)
                except Exception:
                    printExc("Error creating node %s: (continuing anyway)" % n['name'])
            else:
                try:
                    node = self.createNode(n['class'], name=n['name'], prompt=False)
                except Exception:
                    printExc("Error creating node %s: (continuing anyway)" % n['name'])

            node.blockSignals(True)

            if hasattr(node, "display"):
                node.display(topics=None, terms=None, addr=None, win=None)

            node.restoreState(n['state'])

            node.blockSignals(False)

        connections = {}
        edges = {}
        checked = []

        with tempfile.NamedTemporaryFile(mode='w') as type_file:
            type_file.write("from typing import *\n")
            type_file.write("from mypy_extensions import TypedDict\n")
            type_file.write("import numbers\n")
            type_file.write("import builtins\n")
            type_file.write("import amitypes\n")
            type_file.write("T = TypeVar('T')\n\n")

            nodes = self.nodes(data='node')

            for n1, t1, n2, t2 in state['connects']:
                try:
                    node1 = nodes[n1]
                    term1 = node1[t1]
                    node2 = nodes[n2]
                    term2 = node2[t2]

                    term1.connectTo(term2, type_file=type_file, checked=checked)
                    if term1.isInput():
                        in_name = node1.name() + '_' + term1.name()
                        in_name = in_name.replace('.', '_')
                        out_name = node2.name() + '_' + term2.name()
                        out_name = out_name.replace('.', '_')
                        edge = ((node2.name(), node1.name()),
                                f"{node2.name()}.{term2.name()}->{node1.name()}.{term1.name()}",
                                term2.name(), term1.name())
                        edges[(in_name, out_name)] = edge
                    else:
                        in_name = node2.name() + '_' + term2.name()
                        in_name = in_name.replace('.', '_')
                        out_name = node1.name() + '_' + term1.name()
                        out_name = out_name.replace('.', '_')
                        edge = ((node1.name(), node2.name()),
                                f"{node1.name()}.{term1.name()}->{node2.name()}.{term2.name()}",
                                term1.name(), term2.name())
                        edges[(in_name, out_name)] = edge

                    connections[(in_name, out_name)] = (term1, term2)
                except Exception:
                    print(node1.terminals)
                    print(node2.terminals)
                    printExc("Error connecting terminals %s.%s - %s.%s:" % (n1, t1, n2, t2))

            type_file.flush()
            dmypy_status = os.environ['DMYPY_STATUS_FILE']
            status = subprocess.run(["dmypy", "--status-file", dmypy_status, "check", type_file.name],
                                    capture_output=True, text=True)

            if status.returncode != 0:
                lines = status.stdout.split('\n')[:-1]
                for line in lines:
                    m = re.search(r"\"+(\w+)\"+", line)
                    if m:
                        m = m.group().replace('"', '')
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
                self._graph.add_edge(localNode, remoteNode, key=key,
                                     from_term=localTerm, to_term=remoteTerm)
        
        # NEW: Restore subgraphs (MUST BE AFTER nodes and connections)
        if 'subgraphs' in state:
            for sg_state in state['subgraphs']:
                # Get node objects from names
                node_objects = []
                for node_name in sg_state['nodes']:
                    if node_name in self._graph.nodes:
                        node_objects.append(self._graph.nodes[node_name]['node'])
                    else:
                        logger.warning(f"Node {node_name} not found for subgraph {sg_state['name']}")
                
                # Only create if we have valid nodes
                if node_objects:
                    self.makeSubgraphFromSelection(
                        nodes=node_objects,
                        name=sg_state['name'],
                        pos=sg_state.get('placeholder_pos'),
                        description=sg_state.get('description', '')
                    )
                else:
                    logger.warning(f"Skipping empty subgraph {sg_state['name']}")
            
            # Switch back to root view after restoring all subgraphs
            self.viewManager().displayView(name='root')
            
            # Automatically add restored subgraphs to the library
            self._addRestoredSubgraphsToLibrary()
        
        # NEW: Restore view states
        if 'views' in state:
            for view_name, view_state in state['views'].items():
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

        with open(fileName, 'r') as f:
            state = json.load(f)

        ctrl = self.widget()
        await ctrl.clear()
        self.restoreState(state)
        self.viewBox().autoRange()
        self.sigFileLoaded.emit(fileName)
        await ctrl.applyClicked(build_views=False)

        nodes = []
        for name, node in self.nodes(data='node'):
            if node.viewed or node.exportable():
                nodes.append(node)
            node.blockSignals(False)

        await ctrl.chartWidget.build_views(nodes, ctrl=True, export=True)

    def saveFile(self, fileName=None, startDir=None, suggestedFileName='flowchart.fc'):
        """
        Save this flowchart to a .fc file
        """
        if fileName is None:
            if startDir is None:
                startDir = self.filePath
            if startDir is None:
                startDir = '.'
            self.fileDialog = FileDialog(None, "Save Flowchart..", startDir, "Flowchart (*.fc)")
            self.fileDialog.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
            self.fileDialog.show()
            self.fileDialog.fileSelected.connect(self.saveFile)
            return

        if not fileName.endswith('.fc'):
            fileName += ".fc"

        state = self.saveState()
        state = json.dumps(state, indent=2, separators=(',', ': '), sort_keys=False, cls=TypeEncoder)

        with open(fileName, 'w') as f:
            f.write(state)
            f.write('\n')

        ctrl = self.widget()
        ctrl.graph_info.labels(self.hutch, ctrl.graph_name).info({'graph': state})
        ctrl.chartWidget.updateStatus(f"Saved graph to: {fileName}")
        self.sigFileSaved.emit(fileName)

    async def clear(self):
        """
        Remove all nodes from this flowchart except the original input/output nodes.
        """
        for name, node in self._graph.nodes(data='node'):
            if node is None:
                continue
            await self.broker.send_string(name, zmq.SNDMORE)
            await self.broker.send_pyobj(fcMsgs.CloseNode())
            node.close(emit=False)

        self._graph = nx.MultiDiGraph()

    async def updateState(self):
        while True:
            await self.checkpoint.recv_string()
            msg = await self.checkpoint.recv_pyobj()
            node_name = msg.name
            new_node_state = msg.state

            if node_name not in self._graph.nodes:
                continue

            node = self._graph.nodes[node_name]['node']
            current_node_state = node.saveState()
            restore_ctrl = False
            restore_widget = False

            if 'ctrl' in new_node_state:
                if current_node_state['ctrl'] != new_node_state['ctrl']:
                    current_node_state['ctrl'] = new_node_state['ctrl']
                    restore_ctrl = True

            if 'widget' in new_node_state:
                if current_node_state['widget'] != new_node_state['widget']:
                    restore_widget = True
                    current_node_state['widget'] = new_node_state['widget']

            if 'geometry' in new_node_state:
                node.geometry = QtCore.QByteArray.fromHex(bytes(new_node_state['geometry'], 'ascii'))

            if restore_ctrl or restore_widget:
                node.blockSignals(True)
                node.restoreState(current_node_state)
                node.blockSignals(False)
                node.changed = node.isChanged(restore_ctrl, restore_widget)
                if node.changed:
                    self.sigNodeChanged.emit(node)

            node.viewed = new_node_state['viewed']

    async def updateSources(self, init=False):
        num_workers = None

        while True:
            topic = await self.graphinfo.recv_string()
            source = await self.graphinfo.recv_string()
            msg = await self.graphinfo.recv_pyobj()

            if topic == 'sources':
                source_library = SourceLibrary()
                for source, node_type in msg.items():
                    pth = []
                    if ":" in source:
                        for part in source.split(':')[:-1]:
                            if pth:
                                part = ":".join((pth[-1], part))
                            pth.append(part)
                    elif "_" in source:
                        for part in source.split('_')[:-1]:
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

            elif topic == 'event_rate':
                if num_workers is None:
                    ctrl = self.widget()
                    compiler_args = await ctrl.graphCommHandler.compilerArgs
                    num_workers = compiler_args['num_workers']
                    events_per_second = [None]*num_workers
                    total_events = [None]*num_workers

                if ctrl.graph_name not in msg:
                    continue
                time_per_event = msg[ctrl.graph_name]
                worker = int(re.search(r'(\d)+', source).group())
                events_per_second[worker] = len(time_per_event)/(time_per_event[-1][1] - time_per_event[0][0])
                total_events[worker] = msg['num_events']

                if all(events_per_second):
                    events_per_second = int(np.average(events_per_second))
                    total_num_events = int(np.sum(total_events))
                    ctrl = self.widget()
                    ctrl.ui.rateLbl.setText(f"Num Events: {total_num_events} Avg Events/Sec: {events_per_second}")
                    events_per_second = [None]*num_workers
                    total_events = [None]*num_workers
            elif topic == 'warning':
                ctrl = self.widget()
                if hasattr(msg, 'node_name'):
                    if msg.graph_name != ctrl.graph_name:
                        continue
                    node_name = ""
                    if msg.node_name in ctrl.metadata:
                        node_name = ctrl.metadata[msg.node_name]['parent']
                    if node_name in self.nodes(data='node'):
                        node = self.nodes(data='node')[node_name]
                        if node.exception is None:
                            node.setException(msg, "warning")
                            ctrl.chartWidget.updateStatus(f"WARNING: {source} {node.name()}: {msg}", color='orange')
                            logger.warning(f"{source} {node.name()}: {msg}")
            elif topic == 'error':
                ctrl = self.widget()
                if hasattr(msg, 'node_name'):
                    if msg.graph_name != ctrl.graph_name:
                        continue
                    node_name = ctrl.metadata[msg.node_name]['parent']
                    node = self.nodes(data='node')[node_name]
                    node.setException(msg)
                    ctrl.chartWidget.updateStatus(f"ERROR: {source} {node.name()}: {msg}", color='red')
                    logger.error(f"{source} {node.name()}: {msg}")
                else:
                    ctrl.chartWidget.updateStatus(f"ERROR: {source}: {msg}", color='red')
                    logger.error(f"{source}: {msg}")

    async def run(self, load=None):
        tasks = [asyncio.create_task(self.updateState()),
                 asyncio.create_task(self.updateSources())]

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
        self.chart = chart
        self.chartWidget = FlowchartWidget(chart, self)

        self.ui = EditorTemplate.Ui_Toolbar()
        self.ui.setupUi(parent=self, chart=self.chartWidget, configure=configure)
        self.ui.create_model(self.ui.node_tree, self.chart.library.getLabelTree())
        self.ui.create_model(self.ui.source_tree, self.chart.source_library.getLabelTree(), typ="SourceTree")

        self.chart.sigNodeChanged.connect(self.ui.setPending)

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

        self.ui.actionHome.triggered.connect(self.homeClicked)
        self.ui.actionArrange.triggered.connect(self.arrangeClicked)
        self.ui.navGroup.triggered.connect(self.navClicked)

        self.chart.sigFileLoaded.connect(self.setCurrentFile)
        self.chart.sigFileSaved.connect(self.setCurrentFile)

        self.sourceConfigure = SourceConfiguration()
        self.sourceConfigure.sigApply.connect(self.configureApply)

        self.libraryEditor = EditorTemplate.LibraryEditor(self, chart.library, chart.subgraph_library)
        self.libraryEditor.sigApplyClicked.connect(self.libraryUpdated)
        self.libraryEditor.sigReloadClicked.connect(self.libraryReloaded)
        self.ui.libraryConfigure.clicked.connect(self.libraryEditor.show)

        self.ipython_widget = None
        self.graph_info = pc.Info('ami_graph', 'AMI Client graph', ['hutch', 'name'])
        self.graph_version = pc.Gauge('ami_graph_version', 'AMI Client graph version', ['hutch', 'name'])

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
            for name, node in self.chart._graph.nodes(data='node'):
                if node is None:
                    continue
                node.changed = True
            # reset reference counting on views
            await self.features.reset()

        changed_nodes = set()
        failed_nodes = set()
        seen = set()

        for name, gnode in self.chart._graph.nodes(data='node'):
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

                if not hasattr(gnode, 'to_operation'):
                    if gnode.viewable() and gnode.viewed:
                        displays.add(gnode)
                    elif gnode.exportable():
                        try:
                            assert(gnode.values['alias'])
                        except AssertionError:
                            gnode.setException(True)
                            self.chartWidget.updateStatus(f"{gnode.name()} set alias!", color='red')
                            continue
                        try:
                            assert(gnode.values['alias'] != gnode.input_vars()['In'])
                        except AssertionError:
                            gnode.setException(True)
                            self.chartWidget.updateStatus(f"{gnode.name()} alias name cannot be same as input!",
                                                          color='red')
                            continue
                        displays.add(gnode)

                    continue

                outputs = [name]
                outputs.extend(nx.algorithms.dag.descendants(self.chart._graph, name))

                for output in outputs:
                    gnode = self.chart._graph.nodes[output]
                    node = gnode['node']

                    if hasattr(node, 'to_operation') and node not in seen:
                        try:
                            nodes = node.to_operation(inputs=node.input_vars(),
                                                      outputs=node.output_vars(),
                                                      parent=node.name(),
                                                      latched=node.latched)
                        except Exception as e:
                            self.chartWidget.updateStatus(f"{node.name()} {e}!", color='red')
                            printExc(f"{node.name()} raised exception! See console for stacktrace.")
                            node.setException(True)
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
                self.chartWidget.updateStatus(f"{node.name()} disconnected!", color='red')
                node.setException(True)
            msg.show()
            return

        if failed_nodes:
            self.chartWidget.updateStatus("failed to submit graph", color='red')
            msg.show()
            return

        if graph_nodes:
            await self.graphCommHandler.add(graph_nodes)
            node_names = ', '.join(set(map(lambda node: node.parent, graph_nodes)))
            self.chartWidget.updateStatus(f"Submitted {node_names}")

        node_names = ', '.join(set(map(lambda node: node.name(), displays)))
        if displays and build_views:
            self.chartWidget.updateStatus(f"Redisplaying {node_names}")
            await self.chartWidget.build_views(displays, export=True, redisplay=True)

        for node in changed_nodes:
            node.changed = False

        self.metadata = await self.graphCommHandler.metadata
        self.ui.setPendingClear()
        version = str(await self.graphCommHandler.graphVersion)
        state = self.chart.saveState()
        state = json.dumps(state, indent=2, separators=(',', ': '), sort_keys=False, cls=TypeEncoder)

        ts = datetime.now().strftime("%d%m%Y_%H%M%S")
        with open(os.path.expanduser(f"~/.cache/ami/autosave_{ts}.fc"), "w") as f:
            f.write(state)
            f.write('\n')

        self.graph_info.labels(self.chart.hutch, self.graph_name).info({'graph': state, 'version': version})
        self.graph_version.labels(self.chart.hutch, self.graph_name).set(version)

    def openClicked(self):
        startDir = self.chart.filePath
        if startDir is None:
            startDir = '.'
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

    def homeClicked(self):
        children = self.viewBox().allChildren()
        self.viewBox().autoRange(items=children)

    def arrangeClicked(self):
        sources = []
        displays = []
        for name, data in self.chart._graph.nodes(data=True):
            if data.get('subset') == 0:
                sources.append(name)
            elif data.get('subset') == 2:
                displays.append(name)
        fixed = sources + displays
        pos = nx.drawing.layout.multipartite_layout(self.chart._graph, scale=len(self.chart._graph.nodes())*75)
        pos = nx.drawing.layout.spring_layout(nx.Graph(self.chart._graph), pos=pos, fixed=fixed, k=200)
        for name in self.chart._graph.nodes():
            if name not in pos:
                continue
            px = pos[name][0]
            py = pos[name][1]
            p = (find_nearest(px), find_nearest(py))
            gnode['node'].graphicsItem().setPos(*p)

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

        for name, gnode in self.chart._graph.nodes(data='node'):
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
        self.chart.sigFileLoaded.emit(None)
        self.features = Features(self.graphCommHandler)
        await self.graphCommHandler.updatePlots(self.features.plots)

    def configureClicked(self):
        self.sourceConfigure.show()

    if HAS_QTCONSOLE:
        def consoleClicked(self):
            class AmiCli():

                def __init__(self, ctrl, chartWidget, chart, graph, graphCommHandler):
                    self.ctrl = ctrl
                    self.chartWidget = chartWidget
                    self.chart = chart
                    self.graphCommHandler = graphCommHandler

            if self.ipython_widget is None:
                kernel_manager = QtInProcessKernelManager()
                kernel_manager.start_kernel(show_banner=False)
                kernel = kernel_manager.kernel
                kernel.gui = 'qt'

                kernel_client = kernel_manager.client()
                kernel_client.start_channels()

                self.ipython_widget = RichJupyterWidget()
                self.ipython_widget.setWindowTitle('AMI Console')
                self.ipython_widget.kernel_manager = kernel_manager
                self.ipython_widget.kernel_client = kernel_client

            graphCommHandler = GraphCommHandler(self.graphmgr_addr.name, self.graphmgr_addr.comm)
            self.amicli = AmiCli(self, self.chartWidget, self.chart, self.chart._graph, graphCommHandler)
            self.ipython_widget.kernel_manager.kernel.shell.push({'amicli': self.amicli})
            win = QtWidgets.QMainWindow(parent=self)
            win.setCentralWidget(self.ipython_widget)
            win.show()

    @asyncSlot(object)
    async def configureApply(self, src_cfg):
        missing = []

        if 'files' in src_cfg:
            for f in src_cfg['files']:
                if not os.path.exists(f):
                    missing.append(f)

        if not missing:
            await self.graphCommHandler.updateSources(src_cfg)
        else:
            missing = ' '.join(missing)
            self.chartWidget.updateStatus(f"Missing {missing}!", color='red')

    @asyncSlot()
    async def libraryUpdated(self):
        await self.chart.broker.send_string("library", zmq.SNDMORE)
        await self.chart.broker.send_pyobj(fcMsgs.Library(name=self.graph_name,
                                                          paths=self.libraryEditor.node_paths))

        dirs = set(map(os.path.dirname, self.libraryEditor.node_paths))
        await self.graphCommHandler.updatePath(dirs)

        self.chartWidget.updateStatus("Loaded modules.")

    @asyncSlot(object)
    async def libraryReloaded(self, mods):
        smods = set(map(lambda mod: mod.__name__, mods))

        for name, node in self.chart._graph.nodes(data='node'):
            if node is None or node.__module__ not in smods:
                continue
            if True:
                await self.chart.broker.send_string(node.name(), zmq.SNDMORE)
                await self.chart.broker.send_pyobj(fcMsgs.ReloadLibrary(name=node.name(),
                                                                        mods=smods))
                self.chartWidget.updateStatus(f"Reloaded {node.name()}.")


class FlowchartWidget(dockarea.DockArea):
    """Includes the actual graphical flowchart and debugging interface"""
    def __init__(self, chart, ctrl):
        super().__init__()
        self.chart = chart
        self.ctrl = ctrl
        self.hoverItem = None

        #  build user interface (it was easier to do it here than via developer)
        self.viewManager = ViewManager(self, ctrl)
        self.viewManager.sigViewAdded.connect(self.viewAdded)
        self.viewManager.sigMakeSubgraphFromSelection.connect(self.makeSubgraphFromSelection)
        self.viewDock = dockarea.Dock('view', size=(1000, 600))
        self.viewDock.nStyle = ""
        self.viewDock.addWidget(self.viewManager)
        self.viewDock.hideTitleBar()
        self.addDock(self.viewDock)

        self.hoverText = QtWidgets.QTextEdit()
        self.hoverText.setReadOnly(True)
        self.hoverDock = dockarea.Dock('Hover Info', size=(1000, 20))
        self.hoverDock.addWidget(self.hoverText)
        self.addDock(self.hoverDock, 'bottom')

        self.statusText = QtWidgets.QTextEdit()
        self.statusText.setReadOnly(True)
        self.statusDock = dockarea.Dock('Status', size=(1000, 20))
        self.statusDock.addWidget(self.statusText)
        self.addDock(self.statusDock, 'bottom')

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
            node = SourceNode(name=node, terminals={'Out': {'io': 'out', 'ttype': node_type}})
            self.chart.addNode(node=node, pos=pos)

    @asyncSlot()
    async def selectionChanged(self):
        # print "FlowchartWidget.selectionChanged called."
        items = self.scene().selectedItems()

        if len(items) != 1:
            return

        item = items[0]

        if not hasattr(item, 'node'):
            return

        node = item.node
        if not node.enabled():
            return

        if isinstance(node, SubgraphNode):
            action = self.viewManager.actions[node.name()]
            action.setChecked(True)
            action.triggered.emit()
            return

        if not hasattr(node, 'display'):
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
                        if 'node' not in gnode:
                            continue
                        node = gnode['node']
                        if node in seen:
                            continue
                        else:
                            seen.add(node)

                        if node.changed:
                            pending.add(node.name())

            if pending:
                pending = ', '.join(pending)
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
            if hasattr(node.widget, 'saveState'):
                state = node.widget.saveState()

            args = {'name': name,
                    'state': state,
                    'redisplay': redisplay,
                    'geometry': node.geometry,
                    'units': node.input_units(),
                    'terminals': node.saveTerminals(),
                    'label': node._label}

            if node.buffered():
                # buffered nodes are allowed to override their topics/terms
                # this is done because they may want to view intermediate values
                args['topics'] = node.buffered_topics()
                args['terms'] = node.buffered_terms()
                self.ctrl.features.add_plot(node, **args)

            elif isinstance(node, SourceNode) and node.viewable():
                new, topic = await self.ctrl.features.get(name, name)

                args['terms'] = node.input_vars()
                args['topics'] = {name: topic}

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

                args['terms'] = node.input_vars()
                args['topics'] = topics

                if new_plot:
                    self.ctrl.features.add_plot(node, **args)

            elif isinstance(node, CtrlNode) and ctrl:
                args['terms'] = node.input_vars()
                args['topics'] = {}

            display_args.append(args)

            if node.exportable() and export:
                input_vars = node.input_vars()
                values = node.values
                if 'eventid' in input_vars:
                    await self.ctrl.graphCommHandler.export([input_vars['In'],
                                                             input_vars['eventid']],
                                                            [values['alias'], "_timestamp"],
                                                            N=values['events'])
                elif 'Timestamp' in input_vars:
                    await self.ctrl.graphCommHandler.export([input_vars['In'], input_vars['Timestamp']],
                                                            [values['alias'], "_timestamp"])

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
            name = args['name']
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
            if hasattr(node, 'isSubgraph') and node.isSubgraph:
                subgraph_name = node.name()
                if subgraph_name in self.chart._subgraphs:
                    sg_data = self.chart._subgraphs[subgraph_name]
                    description = sg_data.get('description', '')
                    node_count = len(sg_data.get('nodes', []))
                    
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
                doc = re.sub(r'(\t+)|(  )+', '', doc)
            
            text = [doc]

            if not (hasattr(node, 'isSubgraph') and node.isSubgraph) and node.inputs():
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
                text.append(' '.join(connections))

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
                text.append(' '.join(connections))

            text = '\n'.join(text)

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
                connections = ' '.join(connections)
                text = '\n'.join([text, connections])
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
                text = ' '.join(["Connection", prefix, from_node, to_node])

        if text:
            self.hoverText.setPlainText(text)

    def clear(self):
        self.hoverText.setPlainText('')

    def updateStatus(self, text, color='black'):
        now = datetime.now().strftime('%H:%M:%S')
        if STYLE.get("Theme", None) == "dark" and color == 'black':
            color = '#fff'
        self.statusText.insertHtml(f"<font color={color}>[{now}] {text}</font>")
        self.statusText.append("")


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
