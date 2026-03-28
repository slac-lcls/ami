# -*- coding: utf-8 -*-
"""
NodeStateWidget: A Qt widget for displaying the complete state of a flowchart node.

This widget shows the state returned by node.saveState() plus runtime attributes
in a hierarchical tree view. It's designed to help users debug and inspect node
state during flowchart execution.
"""

from qtpy import QtCore, QtGui, QtWidgets
from collections import OrderedDict
import json


class NodeStateWidget(QtWidgets.QWidget):
    """Widget that displays a node's complete state in a tree view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Main layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tree widget
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Property", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 200)
        
        # Allow column resizing
        header = self.tree.header()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)
        
        layout.addWidget(self.tree)
        
        # Show initial placeholder
        self.clear()

    def displayNodeState(self, node):
        """Display the complete state of a node.
        
        Args:
            node: Node instance to display
        """
        self.tree.clear()
        
        if node is None:
            self.clear()
            return
        
        # Get node state
        try:
            state = node.saveState()
        except Exception as e:
            self._addErrorItem(f"Error getting node state: {e}")
            return
        
        # Add header with node info
        header = QtWidgets.QTreeWidgetItem(self.tree)
        header.setText(0, f"Node: {node.name()}")
        header.setText(1, type(node).__name__)
        header.setExpanded(True)
        font = header.font(0)
        font.setBold(True)
        font.setPointSize(font.pointSize() + 1)
        header.setFont(0, font)
        header.setFont(1, font)
        
        # Add runtime state section
        self._addRuntimeState(node, header)
        
        # Add position section
        if 'pos' in state:
            self._addPositionSection(state['pos'], header)
        
        # Add control state section
        if 'ctrl' in state:
            self._addSection("Control State", state['ctrl'], header)
        
        # Add terminals section
        if 'terminals' in state:
            self._addTerminalsSection(state['terminals'], node, header)
        
        # Add widget state section
        if 'widget' in state:
            self._addSection("Widget State", state['widget'], header)
        
        # Add other state keys
        other_state = {}
        standard_keys = {'pos', 'ctrl', 'terminals', 'widget', 'enabled', 
                        'viewed', 'latched', 'label', 'geometry'}
        for key, value in state.items():
            if key not in standard_keys:
                other_state[key] = value
        
        if other_state:
            self._addSection("Other State", other_state, header)
        
        # Expand all items by default
        self.tree.expandAll()

    def clear(self):
        """Clear the tree and show placeholder message."""
        self.tree.clear()
        item = QtWidgets.QTreeWidgetItem(self.tree)
        item.setText(0, "No node selected")
        item.setForeground(0, QtGui.QBrush(QtGui.QColor(150, 150, 150)))
        font = item.font(0)
        font.setItalic(True)
        item.setFont(0, font)

    def _addRuntimeState(self, node, parent):
        """Add runtime state section (created, changed, viewed, etc.)."""
        section = QtWidgets.QTreeWidgetItem(parent)
        section.setText(0, "Runtime State")
        self._makeSectionHeader(section)
        
        # Add runtime attributes
        runtime_attrs = [
            ('created', getattr(node, 'created', None)),
            ('changed', getattr(node, 'changed', None)),
            ('viewed', getattr(node, 'viewed', None)),
            ('enabled', getattr(node, '_enabled', None)),
            ('latched', getattr(node, 'latched', None)),
            ('exception', getattr(node, 'exception', None)),
        ]
        
        for attr_name, attr_value in runtime_attrs:
            self._addStateItem(section, attr_name, attr_value)
        
        # Add label if present
        label = getattr(node, '_label', '')
        if label:
            self._addStateItem(section, 'label', label)

    def _addPositionSection(self, pos, parent):
        """Add position section."""
        section = QtWidgets.QTreeWidgetItem(parent)
        section.setText(0, "Position")
        self._makeSectionHeader(section)
        
        if isinstance(pos, (list, tuple)) and len(pos) >= 2:
            self._addStateItem(section, 'x', pos[0])
            self._addStateItem(section, 'y', pos[1])
        else:
            self._addStateItem(section, 'pos', pos)

    def _addTerminalsSection(self, terminals_state, node, parent):
        """Add terminals section showing connections."""
        section = QtWidgets.QTreeWidgetItem(parent)
        section.setText(0, "Terminals")
        self._makeSectionHeader(section)
        
        # Separate inputs and outputs
        inputs = QtWidgets.QTreeWidgetItem(section)
        inputs.setText(0, "Inputs")
        self._makeSectionHeader(inputs)
        
        outputs = QtWidgets.QTreeWidgetItem(section)
        outputs.setText(0, "Outputs")
        self._makeSectionHeader(outputs)
        
        has_inputs = False
        has_outputs = False
        
        # Add each terminal
        for term_name, term_state in terminals_state.items():
            if term_name not in node.terminals:
                continue
                
            terminal = node.terminals[term_name]
            
            # Determine if input or output
            parent_item = inputs if terminal.isInput() else outputs
            if terminal.isInput():
                has_inputs = True
            else:
                has_outputs = True
            
            # Format terminal info
            term_item = QtWidgets.QTreeWidgetItem(parent_item)
            term_item.setText(0, term_name)
            
            # Build connection info
            connections = []
            if terminal.isInput():
                input_terms = terminal.inputTerminals()
                if input_terms:
                    for in_term in input_terms:
                        conn_str = f"{in_term.node().name()}.{in_term.name()}"
                        connections.append(conn_str)
            else:
                dep_terms = terminal.dependentTerms()
                if dep_terms:
                    for dep_term in dep_terms:
                        conn_str = f"{dep_term.node().name()}.{dep_term.name()}"
                        connections.append(conn_str)
            
            # Set value text
            term_type = term_state.get('ttype', 'Unknown')
            if hasattr(term_type, '__name__'):
                term_type = term_type.__name__
            else:
                term_type = str(term_type)
            
            if connections:
                conn_text = ", ".join(connections)
                term_item.setText(1, f"→ {conn_text}")
                term_item.setToolTip(1, f"Type: {term_type}\nConnected to: {conn_text}")
            else:
                term_item.setText(1, "not connected")
                term_item.setToolTip(1, f"Type: {term_type}")
                term_item.setForeground(1, QtGui.QBrush(QtGui.QColor(150, 150, 150)))
        
        # Remove empty sections
        if not has_inputs:
            section.removeChild(inputs)
        if not has_outputs:
            section.removeChild(outputs)

    def _addSection(self, title, data, parent):
        """Add a collapsible section with data."""
        section = QtWidgets.QTreeWidgetItem(parent)
        section.setText(0, title)
        self._makeSectionHeader(section)
        
        if isinstance(data, dict):
            for key, value in data.items():
                self._addStateItem(section, key, value)
        else:
            self._addStateItem(section, title, data)

    def _addStateItem(self, parent, key, value, depth=0):
        """Recursively add state items to the tree.
        
        Args:
            parent: Parent QTreeWidgetItem
            key: Property name
            value: Property value
            depth: Current nesting depth
        """
        item = QtWidgets.QTreeWidgetItem(parent)
        item.setText(0, str(key))
        
        # Handle different value types
        if isinstance(value, dict):
            item.setText(1, f"{{...}} ({len(value)} items)")
            # Add nested items
            for k, v in value.items():
                self._addStateItem(item, k, v, depth + 1)
        elif isinstance(value, (list, tuple)):
            item.setText(1, f"[...] ({len(value)} items)")
            # Add list items
            for i, v in enumerate(value):
                self._addStateItem(item, f"[{i}]", v, depth + 1)
        elif isinstance(value, OrderedDict):
            item.setText(1, f"{{...}} ({len(value)} items)")
            for k, v in value.items():
                self._addStateItem(item, k, v, depth + 1)
        else:
            # Simple value
            formatted_value = self._formatValue(value)
            item.setText(1, formatted_value)
            
            # Add tooltip for long values
            if len(formatted_value) > 50:
                item.setToolTip(1, str(value))
            
            # Apply color coding
            self._setItemColor(item, value)

    def _formatValue(self, value):
        """Format a value for display.
        
        Args:
            value: Value to format
            
        Returns:
            Formatted string
        """
        if value is None:
            return "None"
        elif isinstance(value, bool):
            return str(value)
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Truncate long strings
            if len(value) > 100:
                return value[:97] + "..."
            return value
        elif isinstance(value, Exception):
            return f"{type(value).__name__}: {str(value)}"
        else:
            # Try to convert to string
            try:
                s = str(value)
                if len(s) > 100:
                    return s[:97] + "..."
                return s
            except:
                return f"<{type(value).__name__}>"

    def _setItemColor(self, item, value):
        """Apply color coding to an item based on its value.
        
        Args:
            item: QTreeWidgetItem
            value: The value to base coloring on
        """
        if isinstance(value, bool):
            if value:
                # True: light green
                item.setBackground(1, QtGui.QBrush(QtGui.QColor(230, 255, 230)))
            else:
                # False: light red
                item.setBackground(1, QtGui.QBrush(QtGui.QColor(255, 230, 230)))
        elif isinstance(value, Exception):
            # Exception: light orange
            item.setBackground(1, QtGui.QBrush(QtGui.QColor(255, 244, 230)))

    def _makeSectionHeader(self, item):
        """Make an item look like a section header.
        
        Args:
            item: QTreeWidgetItem to style
        """
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)
        item.setForeground(0, QtGui.QBrush(QtGui.QColor(50, 50, 50)))

    def _addErrorItem(self, message):
        """Add an error message item.
        
        Args:
            message: Error message to display
        """
        item = QtWidgets.QTreeWidgetItem(self.tree)
        item.setText(0, "Error")
        item.setText(1, message)
        item.setForeground(0, QtGui.QBrush(QtGui.QColor(200, 0, 0)))
        item.setForeground(1, QtGui.QBrush(QtGui.QColor(200, 0, 0)))
