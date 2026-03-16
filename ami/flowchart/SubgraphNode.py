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
        """Override to add custom submenu for adding inputs"""
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
    
    def addInputFromAction(self, action):
        """Add an input terminal from a QAction"""
        term_name, term = action.data()
        self.addInput(term_name, term)

    def addInput(self, name, term):
        """Add an input terminal and connect it"""
        from qtpy import QtGui
        from ami.flowchart.Terminal import ConnectionItem
        
        ttype = term.type()
        
        # Add terminal to placeholder (also adds to SubgraphInputs)
        new_term = self.node.addInput(name, ttype=ttype, removeable=True)
        
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
        
        # Create visual connection in root view: external → placeholder
        root_visual = ConnectionItem(
            term.graphicsItem(),
            new_term.graphicsItem()
        )
        root_view.viewBox().addItem(root_visual)
        
        # Recolor placeholder terminal to white (it's connected in root view)
        new_term.recolor(QtGui.QColor(255, 255, 255))
        
        # SubgraphInput terminal should stay black (not connected yet)
        # User needs to manually connect it to an internal node
        
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

    def addOutputFromMenu(self):
        print("OUTPUT")


class SubgraphNodeInput(Node):

    """
    Subgraph Inputs
    """

    def __init__(self, *args, **kwargs):
        rootNode = kwargs.pop('rootNode')
        super().__init__(*args, **kwargs)
        self.isSubgraphInput = True
        self.rootNode = rootNode

    def addOutput(self, name=None, **kwargs):
        if name:
            return self.addTerminal(name, io='out', ttype=kwargs['ttype'])

    def getInputTerm(self, term):
        rootTerm = self.rootNode.inputs()[term.name()]()
        inputTerms = rootTerm.inputTerminals()
        if inputTerms:
            return inputTerms[0]


class SubgraphNodeOutput(Node):

    """
    Subgraph Outputs
    """

    def __init__(self, *args, **kwargs):
        rootNode = kwargs.pop('rootNode')
        super().__init__(*args, **kwargs)
        self.isSubgraphOutput = True
        self.rootNode = rootNode

    def addOutput(self, name=None, **kwargs):
        if name:
            return self.addTerminal(name, io='in', ttype=kwargs['ttype'])
