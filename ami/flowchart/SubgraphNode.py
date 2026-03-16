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

    def addInputFromMenu(self):
        graph = self.node._graph

        self.addInputWidget = QtWidgets.QWidget(self.parentWidget().parentWidget())
        self.addInputWidget.setWindowTitle(f"{self.node.name()} add input")

        layout = QtWidgets.QGridLayout(self.addInputWidget)
        self.addInputs = QtWidgets.QComboBox(self.addInputWidget)
        add = QtWidgets.QPushButton("Add", parent=self.addInputWidget)
        add.clicked.connect(self.addInput)
        cancel = QtWidgets.QPushButton("Cancel", parent=self.addInputWidget)

        layout.addWidget(self.addInputs, 0, 0, 1, -1)
        layout.addWidget(cancel, 1, 0)
        layout.addWidget(add, 1, 1)

        for node_name, node in graph.nodes(data='node'):
            if node in self.node.children:
                continue

            for term_name, term in node.outputs().items():
                term_name = '.'.join([node_name, term_name])
                if term_name in self.node.inputs():
                    continue

                self.addInputs.addItem(term_name, term)

        self.addInputWidget.show()

    def addInput(self):
        name = self.addInputs.currentText()
        term = self.addInputs.currentData()()
        ttype = term.type()
        new_term = self.node.addInput(name, ttype=ttype, removeable=True)
        term.connectTo(new_term, signal=False)
        self.addInputWidget.close()

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
