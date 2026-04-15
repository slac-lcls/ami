# -*- coding: utf-8 -*-
import os
from collections import OrderedDict


class SubgraphLibrary:
    """Library of subgraph templates that can be instantiated"""

    def __init__(self):
        self.subgraphList = OrderedDict()  # {name: template}
        self.subgraphTree = OrderedDict()  # Tree structure for UI

    def addSubgraph(self, name, template, paths=None):
        """Register a subgraph template

        Args:
            name: Unique name for the subgraph template
            template: SubgraphTemplate instance
            paths: List of file paths where this template is defined (optional)
        """
        self.subgraphList[name] = template

        # Add to tree structure (flat for now, could be hierarchical later)
        self.subgraphTree[name] = {"template": template, "paths": paths or []}

    def getSubgraph(self, name):
        """Get subgraph template by name

        Args:
            name: Name of the subgraph template

        Returns:
            SubgraphTemplate instance or None if not found
        """
        return self.subgraphList.get(name)

    def removeSubgraph(self, name):
        """Remove a subgraph from library

        Args:
            name: Name of the subgraph template to remove
        """
        if name in self.subgraphList:
            del self.subgraphList[name]
        if name in self.subgraphTree:
            del self.subgraphTree[name]

    def hasSubgraph(self, name):
        """Check if subgraph exists in library

        Args:
            name: Name of the subgraph template

        Returns:
            True if subgraph exists, False otherwise
        """
        return name in self.subgraphList

    def getNames(self):
        """Get list of all subgraph template names

        Returns:
            List of subgraph template names
        """
        return list(self.subgraphList.keys())


class SubgraphTemplate:
    """Template for creating subgraph instances"""

    def __init__(self, name, description, state, source_file=None):
        """Initialize a subgraph template

        Args:
            name: Display name for the subgraph
            description: Description of what the subgraph does
            state: Flowchart state dict containing 'nodes' and 'connects'
            source_file: Path to the .fc file this was loaded from (optional)
        """
        self.name = name
        self.description = description
        self.nodes = state.get("nodes", [])
        self.connects = state.get("connects", [])
        self.source_file = source_file

        # Store boundary metadata from subgraph_metadata if present
        metadata = state.get("subgraph_metadata", {})
        self.boundary_inputs = metadata.get("boundary_inputs", [])
        self.boundary_outputs = metadata.get("boundary_outputs", [])

        # Auto-detect boundary terminals on creation (fallback if no metadata)
        self.inputs = self._detectInputs()
        self.outputs = []  # Outputs are user-defined, not auto-detected

    def _detectInputs(self):
        """Find unconnected input terminals to expose as subgraph inputs

        Returns:
            List of dicts with keys: 'node', 'terminal', 'ttype'
        """
        # Build set of connected inputs
        connected_inputs = set()
        for conn in self.connects:
            if len(conn) >= 4:
                from_node, from_term, to_node, to_term = conn[0], conn[1], conn[2], conn[3]
                connected_inputs.add((to_node, to_term))

        # Find dangling inputs
        inputs = []
        for node_state in self.nodes:
            node_name = node_state.get("name")
            terminals = node_state.get("state", {}).get("terminals", {})

            for term_name, term_info in terminals.items():
                if term_info.get("io") == "in":
                    if (node_name, term_name) not in connected_inputs:
                        # Get ttype
                        ttype = term_info.get("ttype")

                        inputs.append({"node": node_name, "terminal": term_name, "ttype": ttype})

        return inputs
