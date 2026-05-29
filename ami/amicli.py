"""AmiCli - Graph manipulation API for MCP server and QtConsole."""

import logging
import os

logger = logging.getLogger(__name__)


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
            return node
        except Exception as e:
            logger.error(f"Failed to create node {node_type}: {e}")
            raise

    def connect_nodes(self, src_name, src_term, dst_name, dst_term):
        """Connect two node terminals.

        Args:
            src_name: Source node name (e.g., 'cspad')
            src_term: Source terminal name (e.g., 'cspad' for SourceNodes, 'Out' for others)
            dst_name: Destination node name (e.g., 'BinningNode.0')
            dst_term: Destination terminal name (e.g., 'In')

        Raises:
            Exception: If nodes don't exist or connection fails
        """
        try:
            # Get nodes from graph
            if src_name not in self.graph.nodes():
                raise Exception(f"Source node '{src_name}' not found")
            if dst_name not in self.graph.nodes():
                raise Exception(f"Destination node '{dst_name}' not found")

            src_node = self.graph.nodes[src_name]["node"]
            dst_node = self.graph.nodes[dst_name]["node"]

            # Get terminals
            if src_term not in src_node.terminals:
                raise Exception(
                    f"Terminal '{src_term}' not found on node '{src_name}'. "
                    f"Available: {list(src_node.terminals.keys())}"
                )
            if dst_term not in dst_node.terminals:
                raise Exception(
                    f"Terminal '{dst_term}' not found on node '{dst_name}'. "
                    f"Available: {list(dst_node.terminals.keys())}"
                )

            src_terminal = src_node.terminals[src_term]
            dst_terminal = dst_node.terminals[dst_term]

            # Connect
            src_terminal.connectTo(dst_terminal)
        except Exception as e:
            logger.error(f"Failed to connect {src_name}.{src_term} -> {dst_name}.{dst_term}: {e}")
            raise

    def disconnect_nodes(self, src_name, src_term, dst_name, dst_term):
        """Disconnect two node terminals.

        Args:
            src_name: Source node name
            src_term: Source terminal name
            dst_name: Destination node name
            dst_term: Destination terminal name

        Raises:
            Exception: If nodes/terminals don't exist or aren't connected
        """
        try:
            src_node = self.graph.nodes[src_name]["node"]
            dst_node = self.graph.nodes[dst_name]["node"]
            src_terminal = src_node.terminals[src_term]
            dst_terminal = dst_node.terminals[dst_term]

            src_terminal.disconnectFrom(dst_terminal)
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
            from ami.flowchart.library.common import SourceNode

            node_type = self.chart.source_library.getSourceType(source_name)
            node = SourceNode(name=source_name, terminals={"Out": {"io": "out", "ttype": node_type}})
            self.chart.addNode(node=node)
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

            import json as json_mod

            with open(filename, "r") as f:
                state = json_mod.load(f)

            # Clear existing nodes synchronously
            for name in list(self.graph.nodes()):
                node = self.graph.nodes[name]["node"]
                node.close()

            # Restore state synchronously
            self.chart.restoreState(state)
        except Exception as e:
            logger.error(f"Failed to load graph from '{filename}': {e}")
            raise

    def clear_graph(self):
        """Remove all nodes from the graph.

        This is fire-and-forget. The clear runs asynchronously via the UI action.
        """
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

        Returns:
            List of dicts with type, description, inputs, outputs, and parameters.
            Example: [{"type": "Roi2D", "description": "Region of Interest of image.",
                       "inputs": {"In": {"type": "Array2d", "optional": false}},
                       "outputs": {"Out": {"type": "Array2d"}, "Roi_Coordinates": {"type": "Array1d"}},
                       "parameters": [{"name": "origin x", "type": "intSpin", "value": 0, "min": 0}, ...]
                      }]
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

                # Get terminal info (requires instantiation)
                inputs = {}
                outputs = {}
                try:
                    sample = node_class("_temp_")
                    for name, term_ref in sample.inputs().items():
                        term = term_ref() if callable(term_ref) else term_ref
                        if term is None:
                            continue
                        inputs[name] = {
                            "type": str(term.type()),
                            "optional": term.optional(),
                        }
                    for name, term_ref in sample.outputs().items():
                        term = term_ref() if callable(term_ref) else term_ref
                        if term is None:
                            continue
                        outputs[name] = {
                            "type": str(term.type()),
                        }
                except Exception:
                    pass

                types.append(
                    {
                        "type": node_type,
                        "description": desc,
                        "inputs": inputs,
                        "outputs": outputs,
                        "parameters": params,
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
            import time

            time.sleep(1.5)  # Wait for heartbeat
            data = self.graphCommHandler.fetch(feature_name)
        return data

    def add_terminal(self, node_name, terminal_name, direction, ttype="Any"):
        """Add a terminal to a node that supports it.

        Args:
            node_name: Node name (e.g., 'Calculator.0', 'Filter.0')
            terminal_name: Name for the new terminal (e.g., 'In.1', 'Out.1')
            direction: 'in' or 'out'
            ttype: Type string ('Any', 'float', 'int', 'Array1d', 'Array2d', 'Array3d')
        """
        from typing import Any

        from amitypes import Array1d, Array2d, Array3d

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

        if node.nodeName != "Calculator":
            raise ValueError(f"Node '{node_name}' is not a Calculator (it's a {node.nodeName})")

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

        if node.nodeName != "Filter":
            raise ValueError(f"Node '{node_name}' is not a Filter (it's a {node.nodeName})")

        # Set the conditions
        import collections

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
