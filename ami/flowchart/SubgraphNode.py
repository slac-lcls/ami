from pyqtgraph.Qt import QtWidgets
from ami.flowchart.Node import Node, NodeGraphicsItem


class SubgraphNode(Node):

    """
    Subgraph
    """

    def __init__(self, name, **kwargs):
        kwargs['allowAddInput'] = True
        kwargs['allowAddOutput'] = True
        super().__init__(name, **kwargs)
        self.isSubgraph = True
        self.is_visual_only = True  # Flag to skip adding to self._graph
        self.flowchart = kwargs.get('flowchart', None)  # For cleanup
        self._subgraphInputs = SubgraphNodeInput('Inputs', allowAddOutput=True, rootNode=self)
        self._subgraphOutputs = SubgraphNodeOutput('Outputs', allowAddInput=True, rootNode=self)
        self.children = kwargs.get('children', [])

    def addInput(self, name=None, **kwargs):
        if name:
            self._subgraphInputs.addOutput(name, **kwargs)
            return self.addTerminal(name, io='in', ttype=kwargs['ttype'])

    def addOutput(self, name=None, **kwargs):
        if name:
            self._subgraphOutputs.addInput(name, **kwargs)
            return self.addTerminal(name, io='out', ttype=kwargs['ttype'])

    @property
    def subgraphInputs(self):
        return self._subgraphInputs

    @property
    def subgraphOutputs(self):
        return self._subgraphOutputs

    def setGraph(self, graph):
        super().setGraph(graph)
        self._subgraphInputs.setGraph(graph)
        self._subgraphOutputs.setGraph(graph)
    

    
    def removeTerminal(self, term):
        """Override to also remove corresponding terminals from SubgraphInputs/Outputs"""
        if isinstance(term, str):
            term_name = term
        else:
            term_name = term.name()
        
        # Check if this is an input or output terminal
        if term_name in self._inputs:
            # Remove corresponding output terminal from SubgraphInputs
            if term_name in self._subgraphInputs.terminals:
                self._subgraphInputs.removeTerminal(term_name)
        
        if term_name in self._outputs:
            # Remove corresponding input terminal from SubgraphOutputs
            if term_name in self._subgraphOutputs.terminals:
                self._subgraphOutputs.removeTerminal(term_name)
        
        # Call parent implementation to actually remove the terminal
        super().removeTerminal(term)

    def close(self, emit=True):
        """Close subgraph placeholder and delete all child nodes."""
        # Validate we have flowchart reference
        if not hasattr(self, 'flowchart') or not self.flowchart:
            # Fallback to default Node.close if no flowchart
            from ami.flowchart.Node import Node
            Node.close(self, emit)
            return
        
        # Get subgraph data
        if self.name() not in self.flowchart._subgraphs:
            # Subgraph not tracked, just clean up this node
            from ami.flowchart.Node import Node
            Node.close(self, emit)
            return
        
        sg_data = self.flowchart._subgraphs[self.name()]
        
        # Step 1: Delete all child nodes
        for node_name in sg_data['nodes']:
            if node_name not in self.flowchart._graph.nodes:
                continue
            node = self.flowchart._graph.nodes[node_name]['node']
            # This will trigger nodeClosed which removes it from the subgraph
            node.close(emit=emit)
        
        # Step 2: Clean up boundary connections
        for bc in sg_data.get('boundary_connections', []):
            # Remove visual-only connections
            if hasattr(bc['root_visual'], 'close'):
                bc['root_visual'].close()
            if hasattr(bc['subgraph_visual'], 'close'):
                bc['subgraph_visual'].close()
        
        # Step 3: Remove tracking (if still exists - may have been removed by nodeClosed)
        if self.name() in self.flowchart._subgraphs:
            del self.flowchart._subgraphs[self.name()]
        
        # Step 4: Remove view
        self.flowchart.viewManager().removeView(self.name())
        
        # Step 5: Clean up helper nodes
        self._subgraphInputs.close(emit=False)
        self._subgraphOutputs.close(emit=False)
        
        # Step 6: Clean up placeholder (THIS node)
        # Use Node.close directly to avoid recursion
        from ami.flowchart.Node import Node
        Node.close(self, emit=False)

    def graphicsItem(self, brush=None):
        """Return the GraphicsItem for this node. Subclasses may re-implement
        this method to customize their appearance in the flowchart."""
        if self._graphicsItem is None:
            self._graphicsItem = SubgraphNodeGraphicsItem(self, brush)
        return self._graphicsItem


class SubgraphNodeGraphicsItem(NodeGraphicsItem):

    def mouseDoubleClickEvent(self, ev):
        """Switch to subgraph view on double-click"""
        ev.accept()
        if self.node.flowchart:
            self.node.flowchart.viewManager().displayView(
                name=self.node.name(),
                autoRange=True
            )

    def buildMenu(self, reset=False):
        """Override to add custom submenus for adding inputs and outputs"""
        # Call parent to get base menu
        menu = super().buildMenu(reset)
        
        # Check if node has _graph attribute (not set during initialization)
        if not hasattr(self.node, '_graph') or self.node._graph is None:
            return menu
        
        # Find and replace "Add input" action with submenu
        if self.node._allowAddInput:
            # Remove the default "Add input" action
            for action in menu.actions():
                if action.text() == "Add input":
                    menu.removeAction(action)
                    break
            
            # Always rebuild the submenu fresh each time (simpler, avoids Qt memory issues)
            self.addInputMenu = QtWidgets.QMenu("Add input", menu)
            self.rebuildAddInputMenu()
            
            # Insert the submenu where "Add input" was (before "Add output" or "Remove node")
            actions = menu.actions()
            insert_before = None
            for action in actions:
                if action.text() in ["Add output", "Remove node"]:
                    insert_before = action
                    break
            
            if insert_before:
                menu.insertMenu(insert_before, self.addInputMenu)
            else:
                menu.addMenu(self.addInputMenu)
        
        # Find and replace "Add output" action with submenu
        if self.node._allowAddOutput:
            # Remove the default "Add output" action
            for action in menu.actions():
                if action.text() == "Add output":
                    menu.removeAction(action)
                    break
            
            # Always rebuild the submenu fresh each time
            self.addOutputMenu = QtWidgets.QMenu("Add output", menu)
            self.rebuildAddOutputMenu()
            
            # Insert the submenu where "Add output" was (before "Remove node")
            actions = menu.actions()
            insert_before = None
            for action in actions:
                if action.text() == "Remove node":
                    insert_before = action
                    break
            
            if insert_before:
                menu.insertMenu(insert_before, self.addOutputMenu)
            else:
                menu.addMenu(self.addOutputMenu)
        
        # Add "Export Subgraph" menu item
        if hasattr(self.node, 'flowchart') and self.node.flowchart:
            export_action = menu.addAction("Export Subgraph...")
            export_action.triggered.connect(self.exportSubgraph)
        
        return menu
    
    def exportSubgraph(self):
        """Export this subgraph to a .fc file"""
        if hasattr(self.node, 'flowchart') and self.node.flowchart:
            self.node.flowchart.exportSubgraph(self.node.name())

    def getMenu(self):
        """Override to rebuild input/output submenus dynamically on every right-click"""
        # Call parent to get the base menu and rebuild "Connect To" submenu
        menu = super().getMenu()
        
        # Rebuild our custom submenus dynamically
        self.rebuildAddInputMenu()
        self.rebuildAddOutputMenu()
        
        return menu

    def rebuildAddInputMenu(self):
        """Rebuild the Add input submenu with current available inputs"""
        if not hasattr(self, 'addInputMenu'):
            return
        
        # Clear existing items
        self.addInputMenu.clear()
        
        graph = self.node._graph
        available_inputs = []
        
        for node_name, node in graph.nodes(data='node'):
            if node in self.node.children:
                continue
            
            for term_name, term_ref in node.outputs().items():
                full_term_name = '.'.join([node_name, term_name])
                if full_term_name in self.node.inputs():
                    continue
                
                # Dereference the weakref immediately to get the actual terminal
                term = term_ref() if callable(term_ref) else term_ref
                available_inputs.append((full_term_name, term))
        
        if available_inputs:
            # Sort by name for easier finding
            for term_name, term in sorted(available_inputs, key=lambda x: x[0]):
                action = self.addInputMenu.addAction(term_name)
                # Store the info in the action's data to avoid closure issues
                action.setData((term_name, term))
                action.triggered.connect(lambda checked, a=action: self.addInputFromAction(a))
        else:
            self.addInputMenu.addAction("(no available inputs)").setEnabled(False)
    
    def rebuildAddOutputMenu(self):
        """Rebuild the Add output submenu with current available outputs from child nodes"""
        if not hasattr(self, 'addOutputMenu'):
            return
        
        # Clear existing items
        self.addOutputMenu.clear()
        
        available_outputs = []
        
        # Iterate through child nodes (nodes inside the subgraph)
        for child_node in self.node.children:
            node_name = child_node.name()
            
            for term_name, term_ref in child_node.outputs().items():
                full_term_name = '.'.join([node_name, term_name])
                
                # Check if already exposed as subgraph output
                if full_term_name in self.node.outputs():
                    continue
                
                # Dereference weakref
                term = term_ref() if callable(term_ref) else term_ref
                available_outputs.append((full_term_name, term))
        
        if available_outputs:
            # Sort by name for easier finding
            for term_name, term in sorted(available_outputs, key=lambda x: x[0]):
                action = self.addOutputMenu.addAction(term_name)
                action.setData((term_name, term))
                action.triggered.connect(lambda checked, a=action: self.addOutputFromAction(a))
        else:
            self.addOutputMenu.addAction("(no available outputs)").setEnabled(False)
    
    def addInputFromAction(self, action):
        """Add an input terminal from a QAction"""
        term_name, term = action.data()
        self.addInput(term_name, term)
    
    def addOutputFromAction(self, action):
        """Add an output terminal from a QAction"""
        term_name, term = action.data()
        self.addOutput(term_name, term)

    def addInput(self, name, term):
        """Add an input terminal and connect it"""
        from qtpy import QtGui, QtCore
        from ami.flowchart.Terminal import ConnectionItem
        
        ttype = term.type()
        
        # Add terminal to placeholder (also adds to SubgraphInputs)
        new_term = self.node.addInput(name, ttype=ttype, removable=True)
        
        # Get the SubgraphInput terminal that was just created
        sg_input_term = self.node.subgraphInputs.terminals.get(name)
        
        # Get the flowchart and subgraph data
        if not hasattr(self.node, 'flowchart') or not self.node.flowchart:
            # Fallback: just connect and return
            term.connectTo(new_term, signal=False)
            return
        
        flowchart = self.node.flowchart
        subgraph_name = self.node.name()
        
        if subgraph_name not in flowchart._subgraphs:
            # Fallback: just connect and return
            term.connectTo(new_term, signal=False)
            return
        
        sg_data = flowchart._subgraphs[subgraph_name]
        root_view = flowchart.viewManager().views['root']
        subgraph_view = sg_data['view']
        
        # Actually connect the terminals (this updates Terminal._connections)
        term.connectTo(new_term, signal=False)
        
        # Hide the default connection item that was created
        for conn in new_term.connections().values():
            if conn.scene() is not None:
                conn.scene().removeItem(conn)
        
        # Create visual-only connection in root view: external → placeholder
        root_visual = ConnectionItem(
            term.graphicsItem(),
            new_term.graphicsItem()
        )
        root_view.viewBox().addItem(root_visual)
        
        # Recolor placeholder terminal to white (it's connected in root view)
        new_term.recolor(QtGui.QColor(255, 255, 255))
        
        # SubgraphInput terminal should stay black (not connected yet)
        # User needs to manually connect it to an internal node
        
        # Check if SubgraphInputs node is in the scene, if not add it
        if self.node.subgraphInputs.graphicsItem().scene() is None:
            subgraph_view.viewBox().addItem(self.node.subgraphInputs.graphicsItem())
            # Position it to the left of the leftmost child node
            if self.node.children:
                leftmost_x = min(child.graphicsItem().pos().x() for child in self.node.children)
                first_y = self.node.children[0].graphicsItem().pos().y()
                self.node.subgraphInputs.graphicsItem().moveBy(leftmost_x - 200, first_y)
            else:
                self.node.subgraphInputs.graphicsItem().moveBy(0, 0)
        
        # Update graphics to properly position terminals
        self.node.graphicsItem().updateTerminals()
        self.node.subgraphInputs.graphicsItem().updateTerminals()
        
        # Update all existing visual connections in root view to realign with new terminal positions
        for bc in sg_data.get('boundary_connections', []):
            if hasattr(bc.get('root_visual'), 'updateLine'):
                bc['root_visual'].updateLine()
            # Also update subgraph view connections
            if hasattr(bc.get('subgraph_visual'), 'updateLine'):
                bc['subgraph_visual'].updateLine()
        
        # Also update the new connection we just created
        root_visual.updateLine()

    def addOutput(self, name, term):
        """Add an output terminal and connect it from internal node"""
        from qtpy import QtGui, QtCore
        from ami.flowchart.Terminal import ConnectionItem
        
        ttype = term.type()
        
        # Add output terminal to placeholder (also adds input to SubgraphOutputs)
        new_term = self.node.addOutput(name, ttype=ttype, removable=True)
        
        # Get the SubgraphOutput input terminal that was just created
        sg_output_term = self.node.subgraphOutputs.terminals.get(name)
        
        # Get flowchart and subgraph data
        if not hasattr(self.node, 'flowchart') or not self.node.flowchart:
            # Fallback: just connect and return
            term.connectTo(sg_output_term, signal=False)
            return
        
        flowchart = self.node.flowchart
        subgraph_name = self.node.name()
        
        if subgraph_name not in flowchart._subgraphs:
            # Fallback: just connect and return
            term.connectTo(sg_output_term, signal=False)
            return
        
        sg_data = flowchart._subgraphs[subgraph_name]
        root_view = flowchart.viewManager().views['root']
        subgraph_view = sg_data['view']
        
        # Check if SubgraphOutputs node is in the scene, if not add it
        if self.node.subgraphOutputs.graphicsItem().scene() is None:
            subgraph_view.viewBox().addItem(self.node.subgraphOutputs.graphicsItem())
            # Position it to the right of the rightmost child node
            if self.node.children:
                rightmost_x = max(child.graphicsItem().pos().x() for child in self.node.children)
                first_y = self.node.children[0].graphicsItem().pos().y()
                self.node.subgraphOutputs.graphicsItem().moveBy(rightmost_x + 200, first_y)
            else:
                self.node.subgraphOutputs.graphicsItem().moveBy(200, 0)
        
        # Actually connect: internal → SubgraphOutputs
        term.connectTo(sg_output_term, signal=False)
        
        # Hide default connection item created by connectTo
        for conn in sg_output_term.connections().values():
            if conn.scene() is not None:
                conn.scene().removeItem(conn)
        
        # Create visual-only connection in subgraph view: internal → SubgraphOutputs
        subgraph_visual = ConnectionItem(
            term.graphicsItem(),
            sg_output_term.graphicsItem()
        )
        subgraph_view.viewBox().addItem(subgraph_visual)
        
        # Recolor SubgraphOutputs terminal to white (connected in subgraph view)
        sg_output_term.recolor(QtGui.QColor(255, 255, 255))
        
        # Placeholder output terminal stays black (not connected externally yet)
        # User can now connect it to external nodes in root view
        
        # Update terminal positions
        self.node.graphicsItem().updateTerminals()
        self.node.subgraphOutputs.graphicsItem().updateTerminals()
        
        # Update existing visual connections to realign
        for bc in sg_data.get('boundary_connections', []):
            if hasattr(bc.get('root_visual'), 'updateLine'):
                bc['root_visual'].updateLine()
            if hasattr(bc.get('subgraph_visual'), 'updateLine'):
                bc['subgraph_visual'].updateLine()
        
        # Update the new connection
        subgraph_visual.updateLine()


class SubgraphNodeInput(Node):

    """
    Subgraph Inputs
    """

    def __init__(self, *args, **kwargs):
        rootNode = kwargs.pop('rootNode')
        super().__init__(*args, **kwargs)
        self.isSubgraphInput = True
        self.is_visual_only = True  # Flag to skip adding to self._graph
        self.rootNode = rootNode

    def addOutput(self, name=None, **kwargs):
        if name:
            return self.addTerminal(name, io='out', ttype=kwargs['ttype'])

    def getInputTerm(self, term):
        # Get the corresponding terminal on the root (placeholder) node
        root_inputs = self.rootNode.inputs()
        if term.name() not in root_inputs:
            # Terminal doesn't exist on placeholder yet, return None
            return None
        
        rootTerm = root_inputs[term.name()]()
        if not rootTerm:
            return None
        
        inputTerms = rootTerm.inputTerminals()
        if inputTerms:
            return inputTerms[0]
        
        return None


class SubgraphNodeOutput(Node):

    """
    Subgraph Outputs
    """

    def __init__(self, *args, **kwargs):
        rootNode = kwargs.pop('rootNode')
        super().__init__(*args, **kwargs)
        self.isSubgraphOutput = True
        self.is_visual_only = True  # Flag to skip adding to self._graph
        self.rootNode = rootNode

    def addInput(self, name=None, **kwargs):
        if name:
            return self.addTerminal(name, io='in', ttype=kwargs['ttype'])
    
    def getOutputTerm(self, term):
        """Get the source terminal that feeds this SubgraphOutput terminal
        
        Given a terminal on SubgraphOutputs (input terminal), find what's connected to it
        and return that source terminal.
        """
        # Get corresponding terminal on the root (placeholder) node
        root_outputs = self.rootNode.outputs()
        if term.name() not in root_outputs:
            return None
        
        rootTerm = root_outputs[term.name()]()
        if not rootTerm:
            return None
        
        # For SubgraphOutput input terminals, find what's connected TO them
        inputTerms = term.inputTerminals()
        if inputTerms:
            return inputTerms[0]
        
        return None
