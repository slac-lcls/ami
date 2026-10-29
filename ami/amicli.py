"""AmiCli - Graph manipulation API for MCP server and QtConsole."""

import ast
import asyncio
import collections
import concurrent.futures
import json
import logging
import os
import time
from typing import Any

import numpy as np
import zmq
from amitypes import Array1d, Array2d, Array3d
from qtpy import QtCore

from ami.flowchart.library.common import SourceNode
from ami.flowchart.Node import find_free_pos, find_nearest

logger = logging.getLogger(__name__)


def node_type(node):
    """Return a node's type name. Source nodes have no nodeName, so fall back to the class name."""
    return getattr(node, "nodeName", type(node).__name__)


class AmiCli:
    """API for programmatic graph manipulation in AMI.

    Used by both the MCP server (for external AI agents) and QtConsole (for
    interactive Python).

    Args:
        ctrl: FlowchartCtrlWidget instance
        chartWidget: MessageBroker/FlowchartWidget instance
        chart: Flowchart instance
        graphCommHandler: GraphCommHandler for manager communication
    """

    def __init__(self, ctrl, chartWidget, chart, graphCommHandler):
        self.ctrl = ctrl
        self.chartWidget = chartWidget
        self.chart = chart
        self.graphCommHandler = graphCommHandler
        # Nodes created through this API that have not been positioned yet, mapped to
        # the position they spawned at. They get placed next to the first node they are
        # connected to, so editing an existing graph never re-arranges the user's layout.
        self._unplaced = {}
        # Pending render_plot screenshot requests: request_id -> concurrent.futures.Future.
        # Populated by request_screenshot (Qt thread), resolved by resolve_screenshot_request
        # (also Qt thread, called from Flowchart.updateState on a NodeScreenshotReply).
        self._screenshot_requests = {}
        self._screenshot_request_counter = 0

    @property
    def graph(self):
        return self.chart._graph

    def create_node(self, node_type, label=""):
        """Create a node in the flowchart.

        Args:
            node_type: Type of node (e.g., 'BinningNode', 'ScatterPlot')
            label: Optional descriptive label (becomes node name if unique)

        Returns:
            Node object

        Raises:
            Exception: If node type doesn't exist or creation fails
        """
        try:
            node = self.chart.createNode(node_type, name=None)
            if label:
                node._label = label
                node.graphicsItem().setLabel(label)
            self._mark_unplaced(node)
            return node
        except Exception as e:
            logger.error(f"Failed to create node {node_type}: {e}")
            raise

    def delete_node(self, node_name):
        """Delete a node from the graph.

        Args:
            node_name: Node name (e.g., 'Average.0', 'Roi2D.0')

        Raises:
            Exception: If node doesn't exist
        """
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]
        node.close()
        self._unplaced.pop(node, None)

    def connect_nodes(self, src_name, src_term, dst_name, dst_term):
        """Connect two node terminals. Automatically handles subgraph boundary crossing.

        Args:
            src_name: Source node name
            src_term: Source terminal name (e.g., 'Out')
            dst_name: Destination node name
            dst_term: Destination terminal name (e.g., 'In')

        Raises:
            Exception: If nodes don't exist or connection fails
        """
        try:
            if src_name not in self.graph.nodes():
                raise Exception(
                    f"Source node '{src_name}' not found. " f"Available: {list(self.graph.nodes())[:10]}..."
                )
            if dst_name not in self.graph.nodes():
                raise Exception(
                    f"Destination node '{dst_name}' not found. " f"Available: {list(self.graph.nodes())[:10]}..."
                )

            src_node = self.graph.nodes[src_name]["node"]
            dst_node = self.graph.nodes[dst_name]["node"]

            if src_term not in src_node.terminals:
                raise Exception(
                    f"Terminal '{src_term}' not found on '{src_name}'. " f"Available: {list(src_node.terminals.keys())}"
                )
            if dst_term not in dst_node.terminals:
                raise Exception(
                    f"Terminal '{dst_term}' not found on '{dst_name}'. " f"Available: {list(dst_node.terminals.keys())}"
                )

            src_terminal = src_node.terminals[src_term]
            dst_terminal = dst_node.terminals[dst_term]

            # Check if this crosses a subgraph boundary
            src_sg = self._find_subgraph_for_node(src_name)
            dst_sg = self._find_subgraph_for_node(dst_name)

            if src_sg == dst_sg:
                # Same context (both root, or both in same subgraph): normal connect
                src_terminal.connectTo(dst_terminal)
                self._place_connected(src_node, dst_node)
            else:
                # Cross-boundary: route through placeholder
                self._connect_across_boundary(
                    src_name,
                    src_term,
                    src_node,
                    src_terminal,
                    src_sg,
                    dst_name,
                    dst_term,
                    dst_node,
                    dst_terminal,
                    dst_sg,
                )
        except Exception as e:
            logger.error(f"Failed to connect {src_name}.{src_term} -> {dst_name}.{dst_term}: {e}")
            raise

    def _mark_unplaced(self, node):
        pos = node.graphicsItem().pos()
        self._unplaced[node] = (pos.x(), pos.y())

    def _is_unplaced(self, node):
        """True if node was created by this API and has not been moved since (by us or the user)."""
        if node not in self._unplaced:
            return False
        pos = node.graphicsItem().pos()
        if (pos.x(), pos.y()) != self._unplaced[node]:
            del self._unplaced[node]
            return False
        return True

    def _place_connected(self, src_node, dst_node):
        """Position newly created nodes relative to the node they were just connected to.

        Downstream nodes go to the right of their source, upstream nodes to the left
        of their destination. Nodes that are already placed are never moved.
        """
        if self._is_unplaced(dst_node):
            self._unplaced.pop(src_node, None)
            self._place_near(dst_node, src_node, 300)
            del self._unplaced[dst_node]
        elif self._is_unplaced(src_node):
            self._place_near(src_node, dst_node, -300)
            del self._unplaced[src_node]

    def _place_near(self, node, anchor, dx):
        item = node.graphicsItem()
        pos = anchor.graphicsItem().pos()
        x, y = find_nearest(pos.x() + dx), find_nearest(pos.y())
        if item.scene() is not None:
            x, y = find_free_pos(item, x, y, item.scene())
        item.setPos(x, y)

    def _find_subgraph_for_node(self, node_name):
        """Return subgraph name if node is inside one, else None."""
        for sg_name, sg_data in self.chart._subgraphs.items():
            if node_name in sg_data["nodes"]:
                return sg_name
        return None

    def _connect_across_boundary(
        self, src_name, src_term, src_node, src_terminal, src_sg, dst_name, dst_term, dst_node, dst_terminal, dst_sg
    ):
        """Handle a connection that crosses a subgraph boundary.

        External → Internal: creates/reuses boundary input terminal, then connects
        SubgraphInput → internal node.

        Internal → External: creates/reuses boundary output terminal, then connects
        placeholder output → external node.
        """
        if src_sg is None and dst_sg is not None:
            # src is external, dst is inside a subgraph
            sg_data = self.chart._subgraphs[dst_sg]
            subgraphNode = sg_data["placeholder"]
            terminal_name = f"{src_name}.{src_term}"

            # Create boundary input terminal if it doesn't exist yet
            if terminal_name not in subgraphNode.inputs():
                subgraphNode.graphicsItem().addInput(terminal_name, src_terminal)

            # Connect SubgraphInput output → internal node input
            sg_input_term = subgraphNode.subgraphInputs.terminals[terminal_name]
            sg_view = sg_data["view"]
            sg_input_term.connectTo(dst_terminal, view=sg_view.viewBox())

        elif src_sg is not None and dst_sg is None:
            # src is inside a subgraph, dst is external
            sg_data = self.chart._subgraphs[src_sg]
            subgraphNode = sg_data["placeholder"]
            terminal_name = f"{src_name}.{src_term}"

            # Create boundary output terminal if it doesn't exist yet
            if terminal_name not in subgraphNode.outputs():
                subgraphNode.graphicsItem().addOutput(terminal_name, src_terminal)

            # Connect placeholder output → external node input
            placeholder_out_term = subgraphNode.terminals[terminal_name]
            root_view = self.chart.viewManager().views["root"]
            placeholder_out_term.connectTo(dst_terminal, view=root_view.viewBox())

        else:
            raise Exception(
                f"Connecting between two different subgraphs ('{src_sg}' → '{dst_sg}') " f"is not supported"
            )

    def disconnect_nodes(self, src_name, src_term, dst_name, dst_term):
        """Disconnect two node terminals. Handles subgraph boundary crossing.

        Args:
            src_name: Source node name
            src_term: Source terminal name
            dst_name: Destination node name
            dst_term: Destination terminal name

        Raises:
            Exception: If nodes/terminals don't exist or aren't connected
        """
        try:
            if src_name not in self.graph.nodes():
                raise Exception(f"Source node '{src_name}' not found")
            if dst_name not in self.graph.nodes():
                raise Exception(f"Destination node '{dst_name}' not found")

            src_node = self.graph.nodes[src_name]["node"]
            dst_node = self.graph.nodes[dst_name]["node"]
            src_terminal = src_node.terminals[src_term]
            dst_terminal = dst_node.terminals[dst_term]

            src_sg = self._find_subgraph_for_node(src_name)
            dst_sg = self._find_subgraph_for_node(dst_name)

            if src_sg == dst_sg:
                # Same context: normal disconnect
                src_terminal.disconnectFrom(dst_terminal)
            elif src_sg is None and dst_sg is not None:
                # External → internal: disconnect via SubgraphInput terminal
                sg_data = self.chart._subgraphs[dst_sg]
                subgraphNode = sg_data["placeholder"]
                terminal_name = f"{src_name}.{src_term}"
                if terminal_name in subgraphNode.subgraphInputs.terminals:
                    sg_input_term = subgraphNode.subgraphInputs.terminals[terminal_name]
                    sg_input_term.disconnectFrom(dst_terminal)
            elif src_sg is not None and dst_sg is None:
                # Internal → external: disconnect via placeholder output terminal
                sg_data = self.chart._subgraphs[src_sg]
                subgraphNode = sg_data["placeholder"]
                terminal_name = f"{src_name}.{src_term}"
                if terminal_name in subgraphNode.terminals:
                    placeholder_out_term = subgraphNode.terminals[terminal_name]
                    placeholder_out_term.disconnectFrom(dst_terminal)
            else:
                raise Exception("Disconnecting between two different subgraphs is not supported")

        except Exception as e:
            logger.error(f"Failed to disconnect {src_name}.{src_term} -> {dst_name}.{dst_term}: {e}")
            raise

    def ensure_source(self, source_name):
        """Ensure a data source node exists in the graph.

        Args:
            source_name: Name of the source (e.g., 'cspad', 'laser_power')

        Returns:
            Source node name (same as source_name)

        Raises:
            Exception: If source doesn't exist in available sources
        """
        try:
            # Check if already exists
            if source_name in self.graph.nodes():
                return source_name

            # Check if source is available
            available_sources = self.list_sources()
            if source_name not in available_sources:
                raise Exception(f"Source '{source_name}' not available. " f"Available sources: {available_sources}")

            # Create source node (same approach as sourceMenuTriggered)
            node_type = self.chart.source_library.getSourceType(source_name)
            node = SourceNode(name=source_name, terminals={"Out": {"io": "out", "ttype": node_type}})
            self.chart.addNode(node=node)
            self._mark_unplaced(node)
            return node.name()
        except Exception as e:
            logger.error(f"Failed to ensure source '{source_name}': {e}")
            raise

    def node_info(self, name):
        """Get information about a node.

        Args:
            name: Node name

        Returns:
            Dict with keys: node, type, inputs, outputs, state

        Raises:
            Exception: If node doesn't exist
        """
        try:
            if name not in self.graph.nodes():
                raise Exception(f"Node '{name}' not found")

            node = self.graph.nodes[name]["node"]
            return {
                "node": node,
                "type": type(node).__name__,
                "inputs": {k: v().type() for k, v in node.inputs().items() if v() is not None},
                "outputs": {k: v().type() for k, v in node.outputs().items() if v() is not None},
                "state": node.saveState(),
            }
        except Exception as e:
            logger.error(f"Failed to get info for node '{name}': {e}")
            raise

    def get_node_parameters(self, node_name):
        """Get current parameters for a node.

        Args:
            node_name: Node name (e.g., 'GaussianFilter1D.0')

        Returns:
            Dict of parameter name -> current value

        Raises:
            Exception: If node doesn't exist
        """
        try:
            if node_name not in self.graph.nodes():
                raise Exception(f"Node '{node_name}' not found")
            node = self.graph.nodes[node_name]["node"]
            if not hasattr(node, "stateGroup") or node.stateGroup is None:
                return {}
            return node.stateGroup.state()
        except Exception as e:
            logger.error(f"Failed to get parameters for '{node_name}': {e}")
            raise

    def set_node_parameters(self, node_name, parameters):
        """Set parameters on a node.

        If the node's display window is open (e.g. an Roi2D box), it's pushed there too, so
        the window reflects the change immediately and doesn't later send a stale checkpoint
        that would silently revert it.

        Args:
            node_name: Node name (e.g., 'GaussianFilter1D.0')
            parameters: Dict of parameter name -> value (e.g., {"sigma": 2.0})

        Returns:
            Dict of all current parameter values after update

        Raises:
            Exception: If node doesn't exist or doesn't support parameters
        """
        try:
            if node_name not in self.graph.nodes():
                raise Exception(f"Node '{node_name}' not found")
            node = self.graph.nodes[node_name]["node"]
            if not hasattr(node, "stateGroup") or node.stateGroup is None:
                raise Exception(f"Node '{node_name}' does not have configurable parameters")
            node.stateGroup.setState(parameters)
            # Update node.values to stay in sync
            for k, v in parameters.items():
                if k in node.values:
                    node.values[k] = v
            # Emit signal so graph picks up new parameters
            node.sigStateChanged.emit(node)

            from ami.client import flowchart_messages as fcMsgs

            self._publish_to_node(node, fcMsgs.NodeCtrlUpdate(node_name, parameters))

            return node.stateGroup.state()
        except Exception as e:
            logger.error(f"Failed to set parameters on '{node_name}': {e}")
            raise

    def get_graph_errors(self):
        """Get errors/warnings from all nodes in the graph.

        Returns:
            List of dicts with node name, type, error message, and traceback if available.
            Empty list if no errors.
        """
        errors = []
        try:
            for name, node in self.chart.nodes(data="node"):
                if node is None:
                    continue
                if node.exception is not None:
                    error_info = {"node": name, "type": type(node).__name__}
                    exc = node.exception
                    if exc is True:
                        error_info["error"] = "Unknown error (check GUI status bar)"
                    else:
                        error_info["error"] = str(exc)
                        error_info["exception_type"] = type(exc).__name__
                        if hasattr(exc, "traceback_str"):
                            error_info["traceback"] = exc.traceback_str
                    errors.append(error_info)
            return errors
        except Exception as e:
            logger.error(f"Failed to get graph errors: {e}")
            raise

    def apply_graph(self):
        """Trigger graph apply (same as clicking Apply button).

        This is fire-and-forget. The apply runs asynchronously.
        Check get_graph_errors() after a short delay to see results.
        """
        self.ctrl.ui.actionApply.trigger()

    def save_graph(self, filename):
        """Save current graph to .fc file.

        Args:
            filename: Path to save file (will add .fc extension if missing)

        Returns:
            Path to saved file

        Raises:
            Exception: If save fails
        """
        try:
            if not filename.endswith(".fc"):
                filename += ".fc"

            self.chart.saveFile(filename)
            return filename
        except Exception as e:
            logger.error(f"Failed to save graph to '{filename}': {e}")
            raise

    def load_graph(self, filename):
        """Load graph from .fc file.

        Args:
            filename: Path to .fc file

        Raises:
            Exception: If file doesn't exist or load fails
        """
        try:
            if not os.path.exists(filename):
                raise Exception(f"File '{filename}' not found")

            with open(filename, "r") as f:
                state = json.load(f)

            # Clear existing nodes synchronously
            for name in list(self.graph.nodes()):
                node = self.graph.nodes[name]["node"]
                node.close()

            # Restore state synchronously
            self.chart.restoreState(state)
            self._unplaced.clear()
        except Exception as e:
            logger.error(f"Failed to load graph from '{filename}': {e}")
            raise

    def clear_graph(self):
        """Remove all nodes from the graph.

        This is fire-and-forget. The clear runs asynchronously via the UI action.
        """
        self._unplaced.clear()
        self.ctrl.ui.actionNew.trigger()

    def auto_layout(self):
        """Auto-arrange node positions using force-directed layout.

        Raises:
            Exception: If layout fails
        """
        try:
            # Trigger the arrange action
            if hasattr(self.ctrl, "arrangeClicked"):
                self.ctrl.arrangeClicked()
                self._unplaced.clear()
            else:
                logger.warning("Auto layout not available")
        except Exception as e:
            logger.error(f"Failed to auto-layout: {e}")
            raise

    def get_graph_state(self):
        """Get full graph state snapshot.

        Returns:
            Dict with nodes, connections, sources
        """
        try:
            nodes = []
            for name, node in self.chart.nodes(data="node"):
                if node is None or getattr(node, "is_visual_only", False):
                    continue
                nodes.append(
                    {
                        "name": name,
                        "type": type(node).__name__,
                        "inputs": list(node.inputs().keys()),
                        "outputs": list(node.outputs().keys()),
                    }
                )

            connections = []
            for from_node, to_node, data in self.graph.edges(data=True):
                connections.append(
                    {
                        "from": from_node,
                        "from_term": data["from_term"],
                        "to": to_node,
                        "to_term": data["to_term"],
                    }
                )

            return {
                "nodes": nodes,
                "connections": connections,
                "sources": self.list_sources(),
                "subgraphs": self.list_subgraphs(),
            }
        except Exception as e:
            logger.error(f"Failed to get graph state: {e}")
            raise

    def list_sources(self):
        """Get available data sources from workers with type information.

        Returns:
            Dict mapping source names to their types
            Example: {"cspad": "Array2d", "laser": "float", "delta_t": "float"}
        """
        try:
            if self.chart.source_library is None:
                return {}
            return {name: str(node_type) for name, node_type in self.chart.source_library.sourceList.items()}
        except Exception as e:
            logger.error(f"Failed to list sources: {e}")
            return {}

    def list_node_types(self):
        """Get all registered node types with descriptions, terminal specs, and parameters.

        Terminal specs come from Node.describe_class(), which reads a class's static terminals
        without instantiating it (see its docstring for why: building ~90 real GUI nodes just to
        inspect them left temp nodes for Python's garbage collector to free on the wrong thread,
        which could segfault the Qt main thread). A few node types add terminals themselves after
        construction (e.g. via a user-facing "add input" prompt) rather than declaring them
        statically; those report empty inputs/outputs here but "can_add_inputs"/"can_add_outputs"
        is true, so an empty list isn't mistaken for "this node takes no input".

        Returns:
            List of dicts with type, description, inputs, outputs, parameters, viewable,
            can_add_inputs, can_add_outputs.
            Example: [{"type": "Roi2D", "description": "Region of Interest of image.",
                       "inputs": {"In": {"type": "Array2d", "optional": false}},
                       "outputs": {"Out": {"type": "Array2d"}, "Roi_Coordinates": {"type": "Array1d"}},
                       "parameters": [{"name": "origin x", "type": "intSpin", "value": 0, "min": 0}],
                       "viewable": true, "can_add_inputs": false, "can_add_outputs": false}]
        """
        try:
            types = []
            for node_type in self.chart.library.nodeList.keys():
                node_class = self.chart.library.getNodeType(node_type)
                # Get description from docstring
                desc = (node_class.__doc__ or "").strip()

                # Get parameters from uiTemplate (class-level, no instantiation needed)
                params = []
                if hasattr(node_class, "uiTemplate"):
                    for param in node_class.uiTemplate:
                        p = {"name": param[0], "type": param[1]}
                        if len(param) > 2 and isinstance(param[2], dict):
                            p.update(param[2])
                        params.append(p)

                spec = node_class.describe_class()
                inputs, outputs = {}, {}
                viewable = can_add_inputs = can_add_outputs = False
                if spec is not None:
                    for name, opts in spec["terminals"].items():
                        entry = {"type": str(opts.get("ttype"))}
                        if opts.get("io") == "in":
                            entry["optional"] = bool(opts.get("optional", False))
                            inputs[name] = entry
                        elif opts.get("io") == "out":
                            outputs[name] = entry
                    viewable = spec["viewable"]
                    can_add_inputs = spec["allowAddInput"]
                    can_add_outputs = spec["allowAddOutput"]

                types.append(
                    {
                        "type": node_type,
                        "description": desc,
                        "inputs": inputs,
                        "outputs": outputs,
                        "parameters": params,
                        "viewable": viewable,
                        "can_add_inputs": can_add_inputs,
                        "can_add_outputs": can_add_outputs,
                    }
                )
            return types
        except Exception as e:
            logger.error(f"Failed to list node types: {e}")
            return []

    def validate_graph(self):
        """Check graph for issues (disconnected terminals, etc).

        Returns:
            List of issue descriptions (empty if no issues)
        """
        issues = []
        try:
            for name, node in self.chart.nodes(data="node"):
                if node is None or getattr(node, "is_visual_only", False):
                    continue

                # Check for disconnected required inputs
                for term_name, term_ref in node.inputs().items():
                    term = term_ref() if callable(term_ref) else term_ref
                    if term is None:
                        continue
                    if not term.optional() and len(term.connections()) == 0:
                        issues.append(f"Node '{name}' has disconnected required input '{term_name}'")

            return issues
        except Exception as e:
            logger.error(f"Failed to validate graph: {e}")
            return [f"Validation error: {e}"]

    def import_subgraph(self, template_name_or_path, pos=None):
        """Instantiate a subgraph from library or file.

        Args:
            template_name_or_path: Template name or path to .fc file
            pos: Optional position [x, y]

        Returns:
            Dict with name, boundary_inputs, boundary_outputs

        Raises:
            Exception: If template not found or import fails
        """
        try:
            # Check if it's a file path
            if os.path.exists(template_name_or_path):
                result = self.chart.importSubgraphFromFile(template_name_or_path, pos=pos)
            elif self.chart.subgraph_library.hasSubgraph(template_name_or_path):
                result = self.chart.instantiateSubgraphFromLibrary(template_name_or_path, pos=pos)
            else:
                raise Exception(
                    f"Subgraph template '{template_name_or_path}' not found. "
                    f"Available: {self.chart.subgraph_library.getNames()}"
                )

            return {
                "name": result["name"],
                "boundary_inputs": result.get("boundary_inputs", []),
                "boundary_outputs": result.get("boundary_outputs", []),
            }
        except Exception as e:
            logger.error(f"Failed to import subgraph '{template_name_or_path}': {e}")
            raise

    def create_subgraph(self, node_names, name, description):
        """Group nodes into a subgraph.

        Args:
            node_names: List of node names to include
            name: Name for the subgraph
            description: Description text

        Returns:
            Subgraph name

        Raises:
            Exception: If nodes don't exist or creation fails
        """
        try:
            # Get node objects
            nodes = []
            for node_name in node_names:
                if node_name not in self.graph.nodes():
                    raise Exception(f"Node '{node_name}' not found")
                nodes.append(self.graph.nodes[node_name]["node"])

            # Create subgraph
            self.chart.makeSubgraphFromSelection(nodes=nodes, name=name, description=description)
            return name
        except Exception as e:
            logger.error(f"Failed to create subgraph '{name}': {e}")
            raise

    def export_subgraph(self, subgraph_name, filename):
        """Save subgraph as .fc template.

        Args:
            subgraph_name: Name of existing subgraph
            filename: Path to save file

        Raises:
            Exception: If subgraph doesn't exist or export fails
        """
        try:
            if subgraph_name not in self.chart._subgraphs:
                raise Exception(f"Subgraph '{subgraph_name}' not found")

            self.chart.exportSubgraph(subgraph_name, filename)
        except Exception as e:
            logger.error(f"Failed to export subgraph '{subgraph_name}': {e}")
            raise

    def list_subgraph_templates(self):
        """List registered subgraph templates with descriptions.

        Returns:
            List of dicts with name, description
        """
        try:
            templates = []
            for name in self.chart.subgraph_library.getNames():
                template = self.chart.subgraph_library.getSubgraph(name)
                templates.append(
                    {
                        "name": name,
                        "description": template.description if template else "",
                    }
                )
            return templates
        except Exception as e:
            logger.error(f"Failed to list subgraph templates: {e}")
            return []

    def subgraph_info(self, template_name):
        """Get boundary terminals and description for a template.

        Args:
            template_name: Name of template

        Returns:
            Dict with inputs, outputs, description

        Raises:
            Exception: If template doesn't exist
        """
        try:
            if not self.chart.subgraph_library.hasSubgraph(template_name):
                raise Exception(
                    f"Template '{template_name}' not found. " f"Available: {self.chart.subgraph_library.getNames()}"
                )

            template = self.chart.subgraph_library.getSubgraph(template_name)
            return {
                "inputs": template.boundary_inputs,
                "outputs": template.boundary_outputs,
                "description": template.description,
            }
        except Exception as e:
            logger.error(f"Failed to get info for template '{template_name}': {e}")
            raise

    def list_subgraphs(self):
        """List all subgraphs with their child nodes and boundary info.

        Returns:
            List of dicts with name, description, nodes, inputs, outputs
        """
        try:
            result = []
            for sg_name, sg_data in self.chart._subgraphs.items():
                placeholder = sg_data["placeholder"]

                # Get terminal names
                input_terminals = list(placeholder.inputs().keys())
                output_terminals = list(placeholder.outputs().keys())

                result.append(
                    {
                        "name": sg_name,
                        "description": sg_data.get("description", ""),
                        "nodes": sg_data["nodes"],
                        "inputs": input_terminals,
                        "outputs": output_terminals,
                    }
                )
            return result
        except Exception as e:
            logger.error(f"Failed to list subgraphs: {e}")
            return []

    def list_subgraph_terminals(self, subgraph_name):
        """Get detailed boundary terminal info including connections.

        Args:
            subgraph_name: Name of existing subgraph

        Returns:
            Dict with inputs and outputs, each showing terminal name, type,
            external connection, and internal connections

        Raises:
            Exception: If subgraph doesn't exist
        """
        try:
            if subgraph_name not in self.chart._subgraphs:
                raise Exception(f"Subgraph '{subgraph_name}' not found")

            sg_data = self.chart._subgraphs[subgraph_name]
            placeholder = sg_data["placeholder"]

            inputs = []
            outputs = []

            # Process input terminals
            for term_name, term_ref in placeholder.inputs().items():
                term = term_ref() if callable(term_ref) else term_ref

                # Get external source
                external_conn = None
                input_terms = term.inputTerminals()
                if input_terms:
                    src_term = input_terms[0]
                    external_conn = {
                        "node": src_term.node().name(),
                        "terminal": src_term.name(),
                    }

                # Get internal connections from boundary_connections
                internal_conns = []
                for bc in sg_data.get("boundary_connections", []):
                    if bc.get("terminal_name") == term_name and bc.get("type") == "input":
                        internal_conns.append(
                            {
                                "node": bc["internal_node"].name(),
                                "terminal": bc["internal_term"].name(),
                            }
                        )

                inputs.append(
                    {
                        "name": term_name,
                        "type": term.type().__name__ if hasattr(term.type(), "__name__") else str(term.type()),
                        "external_connection": external_conn,
                        "internal_connections": internal_conns,
                    }
                )

            # Process output terminals
            for term_name, term_ref in placeholder.outputs().items():
                term = term_ref() if callable(term_ref) else term_ref

                # Get external targets
                external_conns = []
                for dep_term in term.dependentTerms():
                    external_conns.append(
                        {
                            "node": dep_term.node().name(),
                            "terminal": dep_term.name(),
                        }
                    )

                # Get internal source from boundary_connections
                internal_conn = None
                for bc in sg_data.get("boundary_connections", []):
                    if bc.get("terminal_name") == term_name and bc.get("type") == "output":
                        internal_conn = {
                            "node": bc["internal_node"].name(),
                            "terminal": bc["internal_term"].name(),
                        }
                        break

                outputs.append(
                    {
                        "name": term_name,
                        "type": term.type().__name__ if hasattr(term.type(), "__name__") else str(term.type()),
                        "internal_connection": internal_conn,
                        "external_connections": external_conns,
                    }
                )

            return {"inputs": inputs, "outputs": outputs}
        except Exception as e:
            logger.error(f"Failed to get terminal info for subgraph '{subgraph_name}': {e}")
            raise

    def add_subgraph_input(self, subgraph_name, source_node, source_term):
        """Add a boundary input terminal to a subgraph.

        Args:
            subgraph_name: Name of existing subgraph
            source_node: External node providing data
            source_term: Terminal on that node (e.g., 'Out')

        Returns:
            Terminal name that was created

        Raises:
            Exception: If subgraph/nodes don't exist or source is inside subgraph
        """
        if subgraph_name not in self.chart._subgraphs:
            raise Exception(f"Subgraph '{subgraph_name}' not found")
        if source_node not in self.graph.nodes():
            raise Exception(f"Source node '{source_node}' not found")

        sg_data = self.chart._subgraphs[subgraph_name]
        if source_node in sg_data["nodes"]:
            raise Exception(f"Source node '{source_node}' is inside the subgraph")

        subgraphNode = sg_data["placeholder"]
        ext_node = self.graph.nodes[source_node]["node"]
        if source_term not in ext_node.terminals:
            raise Exception(f"Terminal '{source_term}' not found on node '{source_node}'")
        ext_term = ext_node.terminals[source_term]
        terminal_name = f"{source_node}.{source_term}"

        if terminal_name in subgraphNode.inputs():
            raise Exception(f"Input terminal '{terminal_name}' already exists on subgraph")

        # Delegate to existing GUI method — handles terminal pair creation,
        # visual wiring, SubgraphInputs scene placement, graphics updates
        subgraphNode.graphicsItem().addInput(terminal_name, ext_term)
        return terminal_name

    def remove_subgraph_input(self, subgraph_name, terminal_name):
        """Remove a boundary input terminal from a subgraph.

        Args:
            subgraph_name: Name of existing subgraph
            terminal_name: Terminal name to remove (e.g., 'jungfrau1M:raw:image.Out')

        Raises:
            Exception: If subgraph or terminal doesn't exist
        """
        if subgraph_name not in self.chart._subgraphs:
            raise Exception(f"Subgraph '{subgraph_name}' not found")

        sg_data = self.chart._subgraphs[subgraph_name]
        subgraphNode = sg_data["placeholder"]

        if terminal_name not in subgraphNode.inputs():
            raise Exception(
                f"Input terminal '{terminal_name}' not found on subgraph '{subgraph_name}'. "
                f"Available: {list(subgraphNode.inputs().keys())}"
            )

        # removeTerminal handles both placeholder terminal and SubgraphInputs mirror
        subgraphNode.removeTerminal(terminal_name)

    def add_subgraph_output(self, subgraph_name, internal_node, internal_term):
        """Add a boundary output terminal to a subgraph.

        Args:
            subgraph_name: Name of existing subgraph
            internal_node: Internal node to expose (must be child of subgraph)
            internal_term: Terminal on that node (e.g., 'Out')

        Returns:
            Terminal name that was created

        Raises:
            Exception: If subgraph doesn't exist or internal_node is not a child
        """
        if subgraph_name not in self.chart._subgraphs:
            raise Exception(f"Subgraph '{subgraph_name}' not found")

        sg_data = self.chart._subgraphs[subgraph_name]
        if internal_node not in sg_data["nodes"]:
            raise Exception(
                f"Node '{internal_node}' is not in subgraph '{subgraph_name}'. "
                f"Nodes in subgraph: {sg_data['nodes']}"
            )

        if internal_node not in self.graph.nodes():
            raise Exception(f"Node '{internal_node}' not found in graph")

        subgraphNode = sg_data["placeholder"]
        int_node = self.graph.nodes[internal_node]["node"]
        if internal_term not in int_node.terminals:
            raise Exception(f"Terminal '{internal_term}' not found on node '{internal_node}'")
        int_term = int_node.terminals[internal_term]
        terminal_name = f"{internal_node}.{internal_term}"

        if terminal_name in subgraphNode.outputs():
            raise Exception(f"Output terminal '{terminal_name}' already exists on subgraph")

        # Delegate to existing GUI method — handles terminal pair creation,
        # visual wiring, SubgraphOutputs scene placement, graphics updates
        subgraphNode.graphicsItem().addOutput(terminal_name, int_term)
        return terminal_name

    def remove_subgraph_output(self, subgraph_name, terminal_name):
        """Remove a boundary output terminal from a subgraph.

        Args:
            subgraph_name: Name of existing subgraph
            terminal_name: Terminal name to remove (e.g., 'Calculator.0.Out')

        Raises:
            Exception: If subgraph or terminal doesn't exist
        """
        if subgraph_name not in self.chart._subgraphs:
            raise Exception(f"Subgraph '{subgraph_name}' not found")

        sg_data = self.chart._subgraphs[subgraph_name]
        subgraphNode = sg_data["placeholder"]

        if terminal_name not in subgraphNode.outputs():
            raise Exception(
                f"Output terminal '{terminal_name}' not found on subgraph '{subgraph_name}'. "
                f"Available: {list(subgraphNode.outputs().keys())}"
            )

        subgraphNode.removeTerminal(terminal_name)

    def move_node_to_subgraph(self, node_name, subgraph_name):
        """Move a node from root view into an existing subgraph.

        Args:
            node_name: Node to move (must be in root view, not in any subgraph)
            subgraph_name: Target subgraph name

        Returns:
            Dict with new boundary terminals created

        Raises:
            Exception: If node doesn't exist, is a source, or is already in a subgraph
        """

        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")

        node_obj = self.graph.nodes[node_name]["node"]
        if isinstance(node_obj, SourceNode):
            raise Exception(f"Cannot move source node '{node_name}' into subgraph")

        for sg_name, sg_data in self.chart._subgraphs.items():
            if node_name in sg_data["nodes"]:
                raise Exception(f"Node '{node_name}' is already in subgraph '{sg_name}'")

        if subgraph_name not in self.chart._subgraphs:
            raise Exception(f"Subgraph '{subgraph_name}' not found")

        # Delegate all logic to Flowchart
        return self.chart.moveNodeToSubgraph(node_name, subgraph_name)

    def list_features(self):
        """Return dict of available features in the global store.

        Returns:
            Dict mapping feature names to their types. For ndarrays, the type
            is a tuple of (type, ndim).
        """
        return self.graphCommHandler.features

    def fetch_data(self, feature_name):
        """Fetch data for a feature. Auto-views if not in store.

        Args:
            feature_name: Name of the feature to fetch (e.g., 'ScalarPlot.0.Y')

        Returns:
            The fetched data (scalar, array, dict, or None if unavailable)
        """
        data = self.graphCommHandler.fetch(feature_name)
        if data is None:
            # Try registering a view and retrying
            self.graphCommHandler.view(feature_name)

            time.sleep(1.5)  # Wait for heartbeat
            data = self.graphCommHandler.fetch(feature_name)
        return data

    def _pending_upstream_changes(self, node_name):
        """Names of upstream nodes (inclusive) with unapplied changes, same check the GUI makes
        before opening a node's window (see FlowchartWidget.selectionChanged).
        """
        import networkx as nx

        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        pending = set()
        for ancestor in nx.ancestors(self.graph, node_name) | {node_name}:
            gnode = self.graph.nodes[ancestor]
            path_node = gnode.get("node")
            if path_node is not None and getattr(path_node, "changed", False) and hasattr(path_node, "to_operation"):
                pending.add(ancestor)
        return pending

    def open_view(self, node_name):
        """Open a node's display window if it isn't already open, same as clicking it in the GUI.

        Must run in the Qt thread. Raises if the node isn't found, isn't viewable/buffered, or
        has unapplied upstream changes (apply_graph() first, as the GUI requires before viewing).
        """
        if node_name not in self.graph.nodes():
            if node_name in self.list_sources():
                raise Exception(
                    f"Node '{node_name}' not found. It's a known source — call ensure_source('{node_name}') first."
                )
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]
        # "buffered" nodes (ScalarPlot, ScatterPlot, TimePlot, ScatterRoi, ...) show a window of
        # recent events rather than the latest value, but the GUI opens a window for them the
        # same way (see FlowchartWidget.build_views' separate buffered-node branch).
        if not hasattr(node, "display") or not (node.viewable() or node.buffered()):
            raise Exception(
                f"Node '{node_name}' ({node_type(node)}) has no plot window to screenshot; "
                "use fetch_data, or connect a viewer node"
            )
        if node.viewed:
            return
        pending = self._pending_upstream_changes(node_name)
        if pending:
            raise Exception(f"Pending changes for {', '.join(sorted(pending))}; call apply_graph() first")
        asyncio.ensure_future(self.chartWidget.build_views([node], ctrl=True))

    def request_screenshot(self, node_name):
        """Request a PNG screenshot of node_name's open display window.

        Must run in the Qt thread; opens the window first via open_view() if needed. Returns a
        concurrent.futures.Future, resolved from Flowchart.updateState when the window's reply
        arrives (or left pending forever if the window never answers — callers must apply their
        own timeout via future.result(timeout=...)).
        """
        from ami.client import flowchart_messages as fcMsgs

        self.open_view(node_name)
        node = self.graph.nodes[node_name]["node"]

        self._screenshot_request_counter += 1
        request_id = self._screenshot_request_counter
        future = concurrent.futures.Future()
        future.request_id = request_id  # so a timed-out caller can abandon_screenshot_request(future)
        self._screenshot_requests[request_id] = future

        def send_once_viewed():
            # The window subscribes to its topic before setting viewed=True (NodeProcess.display,
            # called synchronously from its message loop), so this can't race a dropped request.
            if not future.done():
                if node.viewed:
                    self._publish_to_node(node, fcMsgs.NodeScreenshotRequest(node_name, request_id))
                else:
                    QtCore.QTimer.singleShot(50, send_once_viewed)

        send_once_viewed()
        return future

    def abandon_screenshot_request(self, future):
        """Drop a request_screenshot() future the caller gave up waiting on (e.g. after its own
        timeout), so a late reply has nothing left to resolve. Must run in the Qt thread.

        Also cancels the future (a no-op if the window already replied): request_screenshot's
        send_once_viewed polls "not future.done()" to decide whether to keep re-scheduling
        itself, so if the window never opens/views, cancelling here is what stops it from
        polling forever after the caller has given up.
        """
        self._screenshot_requests.pop(getattr(future, "request_id", None), None)
        future.cancel()

    def resolve_screenshot_request(self, request_id, png=None, error=None):
        """Complete the future from request_screenshot() with the window's reply.

        Called from Flowchart.updateState on the Qt thread when a NodeScreenshotReply arrives.
        """
        future = self._screenshot_requests.pop(request_id, None)
        if future is None or future.done():
            return  # already timed out and abandoned by the caller
        if error is not None:
            future.set_exception(Exception(error))
        else:
            future.set_result(png)

    # Plot node types that take_reference/compare_to_reference support, mapped to their (x, y) input terminals.
    # x is None when the plot draws y against its index.
    REFERENCE_PLOTS = {"LinePlot": ("X", "Y"), "WaveformViewer": (None, "In")}
    REFERENCE_DIR = os.path.expanduser("~/.cache/ami/references")

    def is_reference_plot(self, name):
        """True if name is a LinePlot/WaveformViewer node (False for sources, features, other nodes)."""
        return name in self.graph.nodes() and node_type(self.graph.nodes[name]["node"]) in self.REFERENCE_PLOTS

    def plot_traces(self, node_name):
        """Return the traces of a LinePlot/WaveformViewer as {legend name: {"x": feature or None, "y": feature}}.

        Legend names match the plot window: "<y> vs <x>" for LinePlot, "<y>" for WaveformViewer.
        Traces with unconnected inputs are skipped. Must run in the Qt thread.
        """
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]
        if node_type(node) not in self.REFERENCE_PLOTS:
            raise Exception(
                f"Node '{node_name}' ({node_type(node)}) is not supported; use one of {list(self.REFERENCE_PLOTS)}"
            )
        xterm, yterm = self.REFERENCE_PLOTS[node_type(node)]
        input_vars = node.input_vars()
        traces = {}
        # extra traces use terminals "Y.1"/"X.1", "In.1", ... (see Node.nextTerminalName)
        for term in input_vars:
            if term != yterm and not term.startswith(yterm + "."):
                continue
            suffix = term[len(yterm) :]
            x = input_vars.get(xterm + suffix) if xterm else None
            if xterm and x is None:
                continue
            y = input_vars[term]
            traces[f"{y} vs {x}" if xterm else y] = {"x": x, "y": y}
        if not traces:
            raise Exception(f"Node '{node_name}' has no connected traces")
        return traces

    def plot_features(self, node_name, trace=""):
        """Return the features of one trace of a LinePlot/WaveformViewer as {"x": ..., "y": ...}.

        Args:
            node_name: Plot node name
            trace: Legend name of the trace (see plot_traces); optional if the plot has only one trace

        Must run in the Qt thread. Fetch the data with fetch_xy() (which may block) from the caller.
        """
        traces = self.plot_traces(node_name)
        if trace:
            if trace not in traces:
                raise Exception(f"Trace '{trace}' not found on '{node_name}'. Traces: {list(traces)}")
            return traces[trace]
        if len(traces) > 1:
            raise Exception(f"'{node_name}' has {len(traces)} traces; pass trace= one of {list(traces)}")
        return next(iter(traces.values()))

    def fetch_xy(self, features):
        """Fetch live (x, y) arrays for the features returned by plot_features(). Blocks; not for the Qt thread."""
        y = self.fetch_data(features["y"])
        if y is None:
            raise Exception(f"No data for '{features['y']}' yet. Check connections and apply_graph.")
        y = np.asarray(y, dtype=float)
        if y.ndim != 1:
            raise Exception(f"'{features['y']}' is {y.ndim}D; references need 1D data")
        if features["x"] is None:
            return np.arange(len(y), dtype=float), y
        x = self.fetch_data(features["x"])
        if x is None:
            raise Exception(f"No data for '{features['x']}' yet.")
        x = np.asarray(x, dtype=float)
        if x.shape != y.shape:
            raise Exception(f"X {x.shape} and Y {y.shape} have different shapes")
        return x, y

    def write_reference_csv(self, node_name, x, y, name=""):
        """Write x, y to a CSV in REFERENCE_DIR and return its path."""
        os.makedirs(self.REFERENCE_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        base = "".join(c if c.isalnum() or c in "-_." else "_" for c in (name or node_name))
        path = os.path.join(self.REFERENCE_DIR, f"{base}_{stamp}.csv")
        np.savetxt(path, np.column_stack([x, y]), delimiter=",", header="x,y", comments="")
        return path

    def reference_xy(self, node_name, name):
        """Return the (x, y) arrays of an existing reference overlay. Must run in the Qt thread."""
        _, widget = self._plot_widget(node_name)
        if name not in widget.reference_traces:
            raise Exception(f"Reference '{name}' not found on '{node_name}'. Available: {list(widget.csv_references)}")
        x, y = widget.reference_traces[name].getData()
        return np.asarray(x, dtype=float), np.asarray(y, dtype=float)

    def _plot_widget(self, node_name):
        """Return the flowchart-side plot widget of a node, creating it if needed."""
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]
        widget = None
        if hasattr(node, "display"):
            widget = node.display(topics=None, terms=None, addr=None, win=None)
        if widget is None or not hasattr(widget, "load_csv_reference"):
            raise Exception(f"Node '{node_name}' ({type(node).__name__}) is not a plot and does not support references")
        return node, widget

    def _publish_to_node(self, node, msg):
        """Publish msg on node's topic over the chart broker.

        The MessageBroker only forwards it to a running NodeProcess (the display window); if
        none is running, it's silently dropped. Low-level: does not mark the node as changed.
        """

        async def send():
            await self.chart.broker.send_string(node.name(), zmq.SNDMORE)
            await self.chart.broker.send_pyobj(msg)

        asyncio.ensure_future(send())

    def _send_to_node_window(self, node, msg):
        """Push msg to node's display window, if open, and refresh the state panel.

        Used for updates made directly through this API (agent/MCP calls) that need to reach an
        already-open NodeProcess window, bypassing the normal checkpoint/restore path.
        """
        self._publish_to_node(node, msg)
        node.sigStateChanged.emit(node)

    def _push_references(self, node, widget):
        """Sync reference overlays to the node's display window (if open) and refresh the state panel."""
        from ami.client import flowchart_messages as fcMsgs

        self._send_to_node_window(node, fcMsgs.NodeReferencesUpdate(node.name(), dict(widget.csv_references)))

    def list_references(self, node_name):
        """Return the CSV reference overlays of a plot node.

        Args:
            node_name: Plot node name (e.g., 'LinePlot.0')

        Returns:
            Dict of reference name -> CSV file path
        """
        _, widget = self._plot_widget(node_name)
        return dict(widget.csv_references)

    def set_reference(self, node_name, path, name=""):
        """Overlay a CSV file as a reference trace on a plot node.

        Same as "Add CSV Reference" in the plot's CSV dialog. The CSV is either two
        columns (x, y) or a single column (y, plotted against its index), with an
        optional header row. Setting a name that already exists replaces it.

        Args:
            node_name: Plot node name (e.g., 'LinePlot.0')
            path: Path to the CSV file
            name: Reference name (defaults to the file name without extension)

        Returns:
            Name of the reference that was set
        """
        try:
            node, widget = self._plot_widget(node_name)
            path = os.path.abspath(os.path.expanduser(path))
            if not os.path.isfile(path):
                raise Exception(f"File '{path}' not found")
            # Resolve the default name (matches load_csv_reference's own default) before the
            # replace check, so a second call with no explicit name replaces rather than adding
            # "<name>_1".
            name = name or os.path.splitext(os.path.basename(path))[0]
            if name in widget.csv_references:
                widget.remove_csv_reference(name)
            name = widget.load_csv_reference(path, name=name)
            if name is None:
                raise Exception(f"Could not parse '{path}' as a CSV reference (expected x,y or y columns)")
            self._push_references(node, widget)
            return name
        except Exception as e:
            logger.error(f"Failed to set reference on '{node_name}': {e}")
            raise

    def remove_reference(self, node_name, name):
        """Remove a CSV reference overlay from a plot node.

        Args:
            node_name: Plot node name (e.g., 'LinePlot.0')
            name: Reference name (see list_references)
        """
        try:
            node, widget = self._plot_widget(node_name)
            if name not in widget.csv_references:
                raise Exception(
                    f"Reference '{name}' not found on '{node_name}'. Available: {list(widget.csv_references)}"
                )
            widget.remove_csv_reference(name)
            self._push_references(node, widget)
        except Exception as e:
            logger.error(f"Failed to remove reference '{name}' from '{node_name}': {e}")
            raise

    def add_terminal(self, node_name, terminal_name, direction, ttype="Any"):
        """Add a terminal to a node that supports it.

        Args:
            node_name: Node name (e.g., 'Calculator.0', 'Filter.0')
            terminal_name: Name for the new terminal (e.g., 'In.1', 'Out.1')
            direction: 'in' or 'out'
            ttype: Type string ('Any', 'float', 'int', 'Array1d', 'Array2d', 'Array3d')
        """

        TYPE_MAP = {
            "Any": Any,
            "float": float,
            "int": int,
            "Array1d": Array1d,
            "Array2d": Array2d,
            "Array3d": Array3d,
        }

        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]
        resolved_type = TYPE_MAP.get(ttype, Any)

        if direction == "in":
            if not getattr(node, "_allowAddInput", False):
                raise ValueError(f"Node {node_name} does not allow adding inputs")
            node.addTerminal(name=terminal_name, io="in", ttype=resolved_type, removable=True)
        elif direction == "out":
            if not getattr(node, "_allowAddOutput", False):
                raise ValueError(f"Node {node_name} does not allow adding outputs")
            node.addTerminal(name=terminal_name, io="out", ttype=resolved_type, removable=True)
        else:
            raise ValueError(f"direction must be 'in' or 'out', got '{direction}'")

        return {
            "node": node_name,
            "terminal": terminal_name,
            "direction": direction,
            "type": ttype,
        }

    def remove_terminal(self, node_name, terminal_name):
        """Remove a terminal from a node.

        Args:
            node_name: Node name
            terminal_name: Terminal to remove
        """
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]
        if terminal_name not in node.terminals:
            raise ValueError(f"Terminal '{terminal_name}' not found on node '{node_name}'")
        node.removeTerminal(terminal_name)
        return {"node": node_name, "removed": terminal_name}

    def get_node_inputs(self, node_name):
        """Get connected variable names and current config for a node.

        Returns dict with:
            - input_terminals: dict of terminal name -> connected wire name (or None)
            - output_terminals: list of output terminal names
            - expression_vars: list of available variable names for expressions
            - current_config: current expression/conditions if applicable
        """
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]

        # Use built-in methods
        input_vars_map = node.input_vars()  # Dict of terminal_name -> variable_name

        # Get current config based on node type
        current_config = {}
        if hasattr(node, "values"):
            current_config = dict(node.values)

        return {
            "input_vars": input_vars_map,
            "current_config": current_config,
        }

    def set_calculator_expression(self, node_name, expression):
        """Set the math expression for a Calculator node.

        Args:
            node_name: Calculator node name (e.g., 'Calculator.0')
            expression: Math expression using connected wire names as variables
                       (e.g., 'cspad.Out * 2 + 5', 'cspad.Out / laser.Out')
        """
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]

        if node_type(node) != "Calculator":
            raise ValueError(f"Node '{node_name}' is not a Calculator (it's a {node_type(node)})")

        # Get available vars using built-in method
        input_vars = node.input_vars()

        # Set the expression
        node.values["operation"] = expression
        node.changed = True

        # Update the widget if it exists
        if node.widget is not None:
            node.widget.restoreState({"operation": expression})

        self.chart.sigNodeChanged.emit(node)

        return {
            "node": node_name,
            "expression": expression,
            "available_vars": list(input_vars.values()),
        }

    def _python_editor(self, node_name):
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]
        if node_type(node) != "PythonEditor":
            raise ValueError(f"Node '{node_name}' is not a PythonEditor (it's a {node_type(node)})")
        return node

    def get_python_code(self, node_name):
        """Get the code of a PythonEditor node.

        Args:
            node_name: PythonEditor node name (e.g., 'PythonEditor.0')

        Returns:
            Dict with the code and the node's input/output terminals in call/return order.
            If no code has been set yet, returns the default template.
        """
        node = self._python_editor(node_name)
        code = node.values["text"] or node.generate_template(node.inputs().keys(), node.outputs().keys())
        return {
            "node": node_name,
            "code": code,
            "inputs": list(node.inputs().keys()),
            "outputs": list(node.outputs().keys()),
        }

    def set_python_code(self, node_name, code):
        """Set the code of a PythonEditor node.

        The code must define ``class EventProcessor`` with an ``on_event(self, <inputs>, *args, **kwargs)``
        method taking one argument per input terminal and returning one value per output terminal, plus the
        begin_run/end_run/begin_step/end_step hooks (the workers call all of them).
        The code is only checked for syntax and structure here, not executed; runtime errors show up
        in get_graph_errors() after apply_graph().

        If the node's editor window is already open, its text is overwritten too, discarding any
        unsaved edits made directly in that window — the caller is expected to have shown the code
        to the user first.

        Args:
            node_name: PythonEditor node name (e.g., 'PythonEditor.0')
            code: Python source

        Returns:
            Dict with node name, inputs, and outputs

        Raises:
            Exception: If the node is not a PythonEditor or the code is invalid
        """
        node = self._python_editor(node_name)
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Syntax error on line {e.lineno}: {e.msg}")

        proc = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "EventProcessor"), None)
        if proc is None:
            raise ValueError("Code must define a top-level 'class EventProcessor' with an on_event method")
        methods = {n.name: n for n in proc.body if isinstance(n, ast.FunctionDef)}
        on_event = methods.get("on_event")
        if on_event is None:
            raise ValueError("EventProcessor must define on_event(self, <inputs>, *args, **kwargs)")
        missing = [m for m in ("begin_run", "end_run", "begin_step", "end_step") if m not in methods]
        if missing:
            raise ValueError(f"EventProcessor is missing {missing}; the workers call these (use 'pass' if unneeded)")

        inputs = list(node.inputs().keys())
        nargs = len(on_event.args.args) - 1  # minus self
        # named args beyond the inputs would never be filled; fewer is only ok if *args takes the rest
        if nargs > len(inputs) or (nargs < len(inputs) and on_event.args.vararg is None):
            raise ValueError(
                f"on_event takes {nargs} argument(s) besides self, but the node has {len(inputs)} input(s): {inputs}"
            )

        node.values["text"] = code
        if node.widget is not None:
            node.widget.restoreState({"text": code})
        node.changed = True
        self.chart.sigNodeChanged.emit(node)

        # Also reach the editor window if it's open in its own NodeProcess (a separate process
        # from this one, so node.widget above is never set there).
        from ami.client import flowchart_messages as fcMsgs

        self._send_to_node_window(node, fcMsgs.NodeWidgetStateUpdate(node.name(), {"text": code}))

        return {"node": node_name, "inputs": inputs, "outputs": list(node.outputs().keys())}

    def set_filter_conditions(self, node_name, conditions):
        """Set filter conditions for a Filter node.

        Args:
            node_name: Filter node name (e.g., 'Filter.0')
            conditions: Dict with If/Elif/Else blocks. Example:
                {
                    "If": {
                        "condition": "laser.Out == 1",
                        "Filter.0.Out": "cspad.Out"
                    },
                    "Else": {
                        "Filter.0.Out": "None"
                    }
                }
        """
        if node_name not in self.graph.nodes():
            raise Exception(f"Node '{node_name}' not found")
        node = self.graph.nodes[node_name]["node"]

        if node_type(node) != "Filter":
            raise ValueError(f"Node '{node_name}' is not a Filter (it's a {node_type(node)})")

        # Set the conditions
        node.values = collections.defaultdict(dict, conditions)
        node.changed = True

        # Update the widget if it exists
        if node.widget is not None:
            # Get current inputs and outputs
            inputs = node.input_vars()
            outputs = node.output_vars()

            # CRITICAL: Set inputs/outputs on widget FIRST before restoreState
            # This ensures the widget has the correct values when building UI components
            node.widget.inputs = inputs
            node.widget.outputs = outputs

            # Build state dict for restoreState
            state = {
                "conditions": len([k for k in conditions.keys() if k.startswith("Elif") or k == "If"]),
                "inputs": inputs,
                "outputs": outputs,
            }
            state.update(conditions)  # Add If/Elif/Else blocks

            node.widget.restoreState(state)

        self.chart.sigNodeChanged.emit(node)

        return {
            "node": node_name,
            "conditions": conditions,
        }
