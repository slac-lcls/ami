# Subgraph Helper Node Refactoring Plan

**Date:** March 17, 2026  
**Status:** Bug Fix + Architecture Improvement  
**Goal:** Fix broken subgraph import and make helper nodes visual-only with direct graph edges

---

## Executive Summary

**CRITICAL BUG:** The current implementation (Phase 2) uses `connectTo(signal=False)` which creates Terminal._connections but **does NOT create graph edges**. This breaks subgraph import because the execution graph is incomplete.

**ROOT CAUSE:**
- `signal=False` prevents `sigTerminalConnected` emission
- `Flowchart.nodeTermConnected()` never gets called
- `self._graph.add_edge()` never executes
- Result: Terminal._connections exist but graph edges are MISSING

**THE FIX:**
This refactoring makes helper nodes visual-only and manually manages graph edges to create the correct execution path. The three layers work together:

1. **Terminal Layer:** Terminal._connections (External → Placeholder, Helper → Internal) - for GUI/coloring/validation
2. **Graph Layer:** Graph edges (External → Internal, bypass helpers) - for execution
3. **Visual Layer:** ConnectionItems in appropriate views - for user interface

**Key Benefits:**
- ✅ **FIXES IMPORT BUG** - Manually creates missing graph edges
- ✅ Cleaner execution graph (no identity operations)
- ✅ Helpers serve purely as visual boundary markers
- ✅ Terminal._connections consistent across creation and runtime
- ✅ Both makeSubgraphFromSelection and _createSubgraphFromImport work correctly

---

## Critical Bug Analysis

### What's Broken in Current Implementation

**Symptom:** Cannot import `.fc` files as subgraphs - graph edges are missing

**Root Cause Chain:**
1. Code calls `helper_term.connectTo(internal_term, signal=False)` (Flowchart.py line 678)
2. `signal=False` prevents `Terminal.connected()` from calling `node.connected()` (Terminal.py line 183-185)
3. Without `node.connected()`, `sigTerminalConnected` is not emitted (Node.py line 422)
4. Without signal emission, `Flowchart.nodeTermConnected()` never fires (Flowchart.py line 1384)
5. Without `nodeTermConnected()`, `self._graph.add_edge()` never executes (Flowchart.py line 1399)
6. **Result:** Terminal._connections exist, but graph edges DO NOT

**Why We Can't Just Use `signal=True`:**
- Would create Helper → Internal graph edges (not External → Internal)
- Would trigger circular connection handlers
- Would create duplicate edge attempts
- Would cause "terminal already connected" errors (input terminals only allow one connection)

**The Solution:**
- Keep `signal=False` to avoid automatic callbacks
- Manually call `self._graph.add_edge()` to create DIRECT edges (External → Internal)
- Terminal._connections and graph edges both exist, serving different purposes

---

## Current Architecture (Broken)

### Three Node Types in a Subgraph

1. **SubgraphNode (placeholder)**
   - Visual-only node in root view (`is_visual_only=True`)
   - NOT in `self._graph` ✓
   - Shows external interface of subgraph

2. **SubgraphNodeInput & SubgraphNodeOutput (helpers)**
   - Currently IN `self._graph` ✗
   - Currently have `to_operation()` methods returning identity operations ✗
   - Visible in subgraph view as boundary markers

3. **Internal nodes**
   - Regular computation nodes inside the subgraph
   - In `self._graph` ✓

### Current Connection Flow (Broken)

**Terminal._connections:** Exist via `connectTo(signal=False)`
- External → Placeholder ✓
- Helper → Internal ✓

**Graph edges:** MISSING due to `signal=False`
- External → Helper: Does NOT exist ✗
- Helper → Internal: Does NOT exist ✗

**Result:** Graph compilation fails, import broken

---

## Target Architecture (Fixed)

### Three Node Types in a Subgraph

1. **SubgraphNode (placeholder)**
   - Visual-only node in root view (`is_visual_only=True`)
   - NOT in `self._graph` ✓
   - Shows external interface of subgraph

2. **SubgraphNodeInput & SubgraphNodeOutput (helpers)**
   - **Visual-only** (`is_visual_only=True`) - NOT in `self._graph` ✓
   - **NO `to_operation()` methods** ✓
   - Visible in subgraph view as boundary markers only

3. **Internal nodes**
   - Regular computation nodes inside the subgraph
   - In `self._graph` ✓

### Target Connection Flow (Fixed)

**Terminal._connections:** Created via `connectTo(signal=False)`
- External → Placeholder ✓ (for GUI/coloring)
- Helper → Internal ✓ (for GUI/coloring)

**Graph edges:** Manually created via `self._graph.add_edge()`
- External → Internal ✓ (DIRECT, bypass both placeholder and helper)

**Visual:** ConnectionItems in appropriate views
- Root view: External → Placeholder
- Subgraph view: Helper → Internal

**Result:** 
- Terminal coloring works (based on Terminal._connections)
- Graph compilation works (based on graph edges)
- Import works (graph edges exist)

---

## Three-Layer Design

The key insight is that Terminal._connections and graph edges serve **different but corresponding** purposes:

### Layer 1: Terminal Layer (GUI/Validation)
**Purpose:** Track what's visually connected for coloring, validation, type checking

**Implementation:** Terminal._connections dict
- External.out → Placeholder.in
- Helper.out → Internal.in

**Created by:** `connectTo(signal=False)`

### Layer 2: Graph Layer (Execution)
**Purpose:** Define actual data flow for graph compilation

**Implementation:** self._graph edges (NetworkX MultiDiGraph)
- External → Internal (DIRECT, bypass helpers and placeholder)

**Created by:** Manual `self._graph.add_edge()` calls

### Layer 3: Visual Layer (User Interface)
**Purpose:** Show connections in different views

**Implementation:** ConnectionItem objects in QGraphicsScenes
- Root view: ConnectionItem(External → Placeholder)
- Subgraph view: ConnectionItem(Helper → Internal)

**Created by:** `connectTo()` creates them, then moved to appropriate views

### How Layers Correspond

All three layers represent the **same logical connection** (External data flows to Internal node):
- **Terminal layer** shows it as: External → Placeholder (interface abstraction)
- **Graph layer** shows it as: External → Internal (direct implementation)
- **Visual layer** shows it as: Different ConnectionItems in different views

They correspond but differ in representation because they serve different purposes.

---

## Implementation Checklist

### Phase 1: Revert to Visual-Only Helpers
**File:** `ami/flowchart/SubgraphNode.py`

- [ ] **Line ~522:** Add `self.is_visual_only = True` to `SubgraphNodeInput.__init__()`
- [ ] **Line ~568:** Add `self.is_visual_only = True` to `SubgraphNodeOutput.__init__()`
- [ ] **Lines 547-556:** DELETE `to_operation()` from SubgraphNodeInput
- [ ] **Lines 598-607:** DELETE `to_operation()` from SubgraphNodeOutput

**File:** `ami/flowchart/Flowchart.py`

- [ ] **Lines 236-237:** DELETE `self._graph.add_node()` calls for helpers in `makeSubgraphFromSelection()`
- [ ] **Lines 511-512:** DELETE `self._graph.add_node()` calls for helpers in `_createSubgraphFromImport()`
- [ ] **Keep:** `sigClosed.connect()` and `setGraph()` calls (helpers still need graph reference)

**Testing:**
- Verify helpers not in `self._graph.nodes`
- Verify helpers still visible in subgraph view
- Graph compilation should skip helpers (no `to_operation()` to call)

---

### Phase 2: Consolidate Creation Methods (Recommended)

**Goal:** Single unified method for both selection and import code paths

**File:** `ami/flowchart/Flowchart.py`

**Step 2A: Extract Boundary Discovery**

Create new method around line 250:

```python
def _discoverBoundaries(self, nodes):
    """Scan graph edges to find subgraph boundary connections.
    
    Args:
        nodes: List of Node objects to analyze
        
    Returns:
        List of boundary metadata dicts with keys:
        - direction: 'input' or 'output'
        - external_node: external node name
        - external_term: external terminal name
        - internal_node: internal node name
        - internal_term: internal terminal name
        - terminal_name: name for placeholder terminal
        - ttype: terminal type
        - original_connection: (external_term, internal_term) tuple if exists
    """
    boundary_metadata = []
    node_names = [node.name() for node in nodes]
    
    # Find input boundaries (External → Internal)
    for fnode_name, tnode_name, data in self._graph.in_edges(node_names, data=True):
        if fnode_name in node_names and tnode_name in node_names:
            continue  # Skip internal connections
        
        external_node = self._graph.nodes[fnode_name]['node']
        internal_node = self._graph.nodes[tnode_name]['node']
        external_term = external_node.terminals[data['from_term']]
        internal_term = internal_node.terminals[data['to_term']]
        
        terminal_name = f"{fnode_name}.{data['from_term']}"
        
        boundary_metadata.append({
            'direction': 'input',
            'external_node': fnode_name,
            'external_term': data['from_term'],
            'internal_node': tnode_name,
            'internal_term': data['to_term'],
            'terminal_name': terminal_name,
            'ttype': external_term.type(),
            'original_connection': (external_term, internal_term)
        })
    
    # Find output boundaries (Internal → External)
    for fnode_name, tnode_name, data in self._graph.out_edges(node_names, data=True):
        if fnode_name in node_names and tnode_name in node_names:
            continue  # Skip internal connections
        
        internal_node = self._graph.nodes[fnode_name]['node']
        external_node = self._graph.nodes[tnode_name]['node']
        internal_term = internal_node.terminals[data['from_term']]
        external_term = external_node.terminals[data['to_term']]
        
        terminal_name = f"{fnode_name}.{data['from_term']}"
        
        boundary_metadata.append({
            'direction': 'output',
            'external_node': tnode_name,
            'external_term': data['to_term'],
            'internal_node': fnode_name,
            'internal_term': data['from_term'],
            'terminal_name': terminal_name,
            'ttype': internal_term.type(),
            'original_connection': (internal_term, external_term)
        })
    
    return boundary_metadata
```

**Step 2B: Create Unified Method**

Create new method around line 200:

```python
def _createSubgraph(self, name, nodes, pos=None, description=None, 
                   boundary_metadata=None, node_mapping=None):
    """Unified subgraph creation for both selection and import.
    
    Args:
        name: Subgraph name
        nodes: List of Node objects to include in subgraph
        pos: Position for placeholder (QPointF or tuple)
        description: Optional description
        boundary_metadata: Optional list of boundary dicts. If None, auto-discover.
        node_mapping: Optional dict mapping old names to new names (for import)
    
    Returns:
        subgraph placeholder node
    """
    from qtpy import QtGui
    from ami.flowchart.Terminal import ConnectionItem
    
    # Step 1: Discover boundaries if not provided
    if boundary_metadata is None:
        boundary_metadata = self._discoverBoundaries(nodes)
    
    # Step 2: Create view and placeholder
    view = self.viewManager().addView(name)
    
    subgraph = SubgraphNode(name, children=nodes, flowchart=self)
    subgraph.sigClosed.connect(self.nodeClosed)
    subgraph.setGraph(self._graph)
    
    # Helpers are created automatically by SubgraphNode.__init__
    # Set graph reference on helpers (but don't add to self._graph)
    subgraph.subgraphInputs.sigClosed.connect(self.nodeClosed)
    subgraph.subgraphOutputs.sigClosed.connect(self.nodeClosed)
    subgraph.subgraphInputs.setGraph(self._graph)
    subgraph.subgraphOutputs.setGraph(self._graph)
    
    # Step 3: Add placeholder to root view
    placeholder_item = subgraph.graphicsItem()
    self.viewBox().addItem(placeholder_item)
    if pos:
        if isinstance(pos, QtCore.QPointF):
            placeholder_item.moveBy(pos.x(), pos.y())
        else:
            placeholder_item.moveBy(*pos)
    else:
        if nodes:
            placeholder_item.moveBy(
                nodes[0].graphicsItem().pos().x(),
                nodes[0].graphicsItem().pos().y()
            )
    
    # Step 4: Process boundaries
    boundary_connections = []
    
    for boundary in boundary_metadata:
        # Remap node names if needed (for import)
        external_node_name = boundary['external_node']
        internal_node_name = boundary['internal_node']
        
        if node_mapping:
            internal_node_name = node_mapping.get(internal_node_name, internal_node_name)
        
        # Get node objects
        if external_node_name in self._graph.nodes:
            external_node = self._graph.nodes[external_node_name]['node']
            external_term = external_node.terminals[boundary['external_term']]
        else:
            # External node doesn't exist yet (will be connected later)
            external_node = None
            external_term = None
        
        internal_node = self._graph.nodes[internal_node_name]['node']
        internal_term = internal_node.terminals[boundary['internal_term']]
        
        # Create terminals on placeholder and helpers
        if boundary['direction'] == 'input':
            # Add input to placeholder (also creates output on helper)
            placeholder_term = subgraph.addInput(
                boundary['terminal_name'],
                ttype=boundary['ttype'],
                removable=True
            )
            helper_term = subgraph.subgraphInputs.terminals[boundary['terminal_name']]
            
            # Add helper to subgraph view if not already added
            if subgraph.subgraphInputs.graphicsItem().scene() is None:
                view.viewBox().addItem(subgraph.subgraphInputs.graphicsItem())
                # Position to left of internal nodes
                if nodes:
                    leftmost_x = min(n.graphicsItem().pos().x() for n in nodes)
                    first_y = nodes[0].graphicsItem().pos().y()
                    subgraph.subgraphInputs.graphicsItem().setPos(leftmost_x - 200, first_y)
            
            # Disconnect original connection if it exists
            if 'original_connection' in boundary:
                ext_term, int_term = boundary['original_connection']
                if ext_term.connectedTo(int_term):
                    ext_term.disconnectFrom(int_term, signal=False)
                    # Remove old graph edge
                    old_key = f"{boundary['external_node']}.{boundary['external_term']}->{boundary['internal_node']}.{boundary['internal_term']}"
                    if self._graph.has_edge(boundary['external_node'], boundary['internal_node'], key=old_key):
                        self._graph.remove_edge(boundary['external_node'], boundary['internal_node'], key=old_key)
            
            # Create Terminal._connections (GUI layer)
            if external_term:
                external_term.connectTo(placeholder_term, signal=False)
            
            helper_term.connectTo(internal_term, signal=False)
            
            # Move helper→internal visual connection to subgraph view
            sg_visual = helper_term._connections.get(internal_term)
            if sg_visual and sg_visual.scene() is not None:
                sg_visual.scene().removeItem(sg_visual)
            if sg_visual:
                view.viewBox().addItem(sg_visual)
            
            # Create DIRECT graph edge (execution layer): External → Internal
            if external_node:
                edge_key = f"{external_node.name()}.{boundary['external_term']}->{internal_node.name()}.{boundary['internal_term']}"
                if not self._graph.has_edge(external_node.name(), internal_node.name(), key=edge_key):
                    self._graph.add_edge(
                        external_node.name(),
                        internal_node.name(),
                        key=edge_key,
                        from_term=boundary['external_term'],
                        to_term=boundary['internal_term']
                    )
            
            # Recolor terminals
            placeholder_term.recolor(QtGui.QColor(255, 255, 255))
            helper_term.recolor(QtGui.QColor(255, 255, 255))
            internal_term.recolor(QtGui.QColor(255, 255, 255))
            
            # Store boundary info
            boundary_connections.append({
                'type': 'input',
                'terminal_name': boundary['terminal_name'],
                'internal_node': internal_node,
                'internal_term': internal_term,
                'external_node': external_node,
                'external_term': external_term,
                'root_visual': external_term._connections.get(placeholder_term) if external_term else None,
                'subgraph_visual': sg_visual
            })
        
        else:  # output
            # Add output to placeholder (also creates input on helper)
            placeholder_term = subgraph.addOutput(
                boundary['terminal_name'],
                ttype=boundary['ttype'],
                removable=True
            )
            helper_term = subgraph.subgraphOutputs.terminals[boundary['terminal_name']]
            
            # Add helper to subgraph view if not already added
            if subgraph.subgraphOutputs.graphicsItem().scene() is None:
                view.viewBox().addItem(subgraph.subgraphOutputs.graphicsItem())
                # Position to right of internal nodes
                if nodes:
                    rightmost_x = max(n.graphicsItem().pos().x() for n in nodes)
                    first_y = nodes[0].graphicsItem().pos().y()
                    subgraph.subgraphOutputs.graphicsItem().setPos(rightmost_x + 200, first_y)
            
            # Disconnect original connection if it exists
            if 'original_connection' in boundary:
                int_term, ext_term = boundary['original_connection']
                if int_term.connectedTo(ext_term):
                    int_term.disconnectFrom(ext_term, signal=False)
                    # Remove old graph edge
                    old_key = f"{boundary['internal_node']}.{boundary['internal_term']}->{boundary['external_node']}.{boundary['external_term']}"
                    if self._graph.has_edge(boundary['internal_node'], boundary['external_node'], key=old_key):
                        self._graph.remove_edge(boundary['internal_node'], boundary['external_node'], key=old_key)
            
            # Create Terminal._connections (GUI layer)
            internal_term.connectTo(helper_term, signal=False)
            
            if external_term:
                placeholder_term.connectTo(external_term, signal=False)
            
            # Move internal→helper visual connection to subgraph view
            sg_visual = internal_term._connections.get(helper_term)
            if sg_visual and sg_visual.scene() is not None:
                sg_visual.scene().removeItem(sg_visual)
            if sg_visual:
                view.viewBox().addItem(sg_visual)
            
            # Create DIRECT graph edge (execution layer): Internal → External
            if external_node:
                edge_key = f"{internal_node.name()}.{boundary['internal_term']}->{external_node.name()}.{boundary['external_term']}"
                if not self._graph.has_edge(internal_node.name(), external_node.name(), key=edge_key):
                    self._graph.add_edge(
                        internal_node.name(),
                        external_node.name(),
                        key=edge_key,
                        from_term=boundary['internal_term'],
                        to_term=boundary['external_term']
                    )
            
            # Recolor terminals
            placeholder_term.recolor(QtGui.QColor(255, 255, 255))
            helper_term.recolor(QtGui.QColor(255, 255, 255))
            internal_term.recolor(QtGui.QColor(255, 255, 255))
            
            # Store boundary info
            boundary_connections.append({
                'type': 'output',
                'terminal_name': boundary['terminal_name'],
                'internal_node': internal_node,
                'internal_term': internal_term,
                'external_node': external_node,
                'external_term': external_term,
                'root_visual': placeholder_term._connections.get(external_term) if external_term else None,
                'subgraph_visual': sg_visual
            })
    
    # Step 5: Move internal nodes to subgraph view
    internal_connections = []
    for node in nodes:
        # Remove from root view
        item = node.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)
        
        # Add to subgraph view
        view.viewBox().addItem(item)
        
        # Find internal connections
        for term_name, term in node.terminals.items():
            for remote_term, conn_item in term.connections().items():
                remote_node = remote_term.node()
                if remote_node in nodes:
                    if conn_item not in internal_connections:
                        internal_connections.append(conn_item)
        
        node.recolor()
    
    # Move internal connections to subgraph view
    for conn in internal_connections:
        if conn.scene() is not None:
            conn.scene().removeItem(conn)
        view.viewBox().addItem(conn)
    
    # Step 6: Store subgraph metadata
    node_names = [node.name() for node in nodes]
    self._subgraphs[name] = {
        'nodes': node_names,
        'placeholder': subgraph,
        'view': view,
        'boundary_connections': boundary_connections,
        'internal_connections': internal_connections,
        'description': description or ''
    }
    
    # Step 7: Update terminal positions
    subgraph.graphicsItem().updateTerminals()
    if subgraph.subgraphInputs.graphicsItem().scene():
        subgraph.subgraphInputs.graphicsItem().updateTerminals()
    if subgraph.subgraphOutputs.graphicsItem().scene():
        subgraph.subgraphOutputs.graphicsItem().updateTerminals()
    
    return subgraph
```

**Step 2C: Update Public Methods**

Replace `makeSubgraphFromSelection()` (lines 202-481):

```python
def makeSubgraphFromSelection(self, nodes=None, name=None, pos=None, description=None):
    """Create a subgraph from selected nodes.
    
    This creates a visual grouping in a separate view with a placeholder in root view.
    Delegates to unified _createSubgraph() method.
    
    Args:
        nodes: List of nodes to group
        name: Name for the subgraph
        pos: Position for the placeholder
        description: Optional description for the subgraph
    """
    if name is None:
        n = 0
        while True:
            name = f"combined.{n}"
            if name not in self._graph.nodes():
                break
            n += 1
    
    # Use unified creation method (auto-discovers boundaries)
    subgraph = self._createSubgraph(name, nodes, pos, description)
    
    # Display the subgraph view
    self.viewManager().displayView(name=subgraph.name(), autoRange=True)
    
    # Add to library
    self._addSubgraphToLibrary(name)
    
    return subgraph
```

Replace `_createSubgraphFromImport()` (lines 482-734):

```python
def _createSubgraphFromImport(self, name, nodes, boundary_inputs, boundary_outputs, 
                              node_mapping, pos=None, description=None):
    """Create a subgraph from imported nodes and boundary metadata.
    
    This is for importing .fc files where we have metadata about boundaries.
    Delegates to unified _createSubgraph() method.
    
    Args:
        name: Unique name for the subgraph
        nodes: List of already-restored Node objects
        boundary_inputs: List of dicts with boundary input metadata
        boundary_outputs: List of dicts with boundary output metadata
        node_mapping: Dict mapping old node names to new node names
        pos: Position for placeholder (optional, QPointF or tuple)
        description: Subgraph description (optional)
    """
    # Convert import metadata to unified format
    boundary_metadata = []
    
    for boundary_input in boundary_inputs:
        boundary_metadata.append({
            'direction': 'input',
            'external_node': None,  # No external connections on import
            'external_term': None,
            'internal_node': boundary_input.get('internal_node'),
            'internal_term': boundary_input.get('internal_terminal'),
            'terminal_name': boundary_input['placeholder_terminal'],
            'ttype': eval(boundary_input['ttype']) if isinstance(boundary_input['ttype'], str) else boundary_input['ttype']
        })
    
    for boundary_output in boundary_outputs:
        boundary_metadata.append({
            'direction': 'output',
            'external_node': None,
            'external_term': None,
            'internal_node': boundary_output.get('internal_node'),
            'internal_term': boundary_output.get('internal_terminal'),
            'terminal_name': boundary_output['placeholder_terminal'],
            'ttype': eval(boundary_output['ttype']) if isinstance(boundary_output['ttype'], str) else boundary_output['ttype']
        })
    
    # Use unified creation method with provided metadata
    subgraph = self._createSubgraph(
        name, 
        nodes, 
        pos, 
        description,
        boundary_metadata=boundary_metadata,
        node_mapping=node_mapping
    )
    
    if self._widget:
        self.widget().chartWidget.updateStatus(f"Imported subgraph: {name}")
    
    return subgraph
```

**Testing:**
- Create subgraph from selection - verify works
- Import subgraph from .fc - verify works
- Both should produce identical structure

---

### Phase 3: Handle Runtime Connections

**Goal:** When user connects external node to placeholder at runtime, create direct graph edge

**File:** `ami/flowchart/Flowchart.py`

**Modify `nodeTermConnected()` method (around line 1384):**

```python
async def nodeTermConnected(self, localTerm, remoteTerm):
    # Handle case where remoteTerm is None
    if not remoteTerm or not localTerm:
        return
    
    if remoteTerm.isOutput():
        t = remoteTerm
        remoteTerm = localTerm
        localTerm = t
    
    # CHECK: Is this a subgraph boundary connection?
    if hasattr(remoteTerm.node(), 'isSubgraph') and remoteTerm.node().isSubgraph:
        subgraph = remoteTerm.node()
        
        if remoteTerm.isInput():
            # External → Placeholder Input
            # Look up which internal node(s) this maps to
            if subgraph.name() in self._subgraphs:
                sg_data = self._subgraphs[subgraph.name()]
                
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'input':
                        # Create DIRECT graph edge: External → Internal
                        edge_key = f"{localTerm.node().name()}.{localTerm.name()}->{bc['internal_node'].name()}.{bc['internal_term'].name()}"
                        
                        if not self._graph.has_edge(localTerm.node().name(), bc['internal_node'].name(), key=edge_key):
                            self._graph.add_edge(
                                localTerm.node().name(),
                                bc['internal_node'].name(),
                                key=edge_key,
                                from_term=localTerm.name(),
                                to_term=bc['internal_term'].name()
                            )
                        
                        # Don't create default edge, we created direct edge
                        self.sigNodeChanged.emit(localTerm.node())
                        return
        
        elif remoteTerm.isOutput():
            # Placeholder Output → External
            # Look up which internal node(s) this maps to
            if subgraph.name() in self._subgraphs:
                sg_data = self._subgraphs[subgraph.name()]
                
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == localTerm.name() and bc['type'] == 'output':
                        # Create DIRECT graph edge: Internal → External
                        edge_key = f"{bc['internal_node'].name()}.{bc['internal_term'].name()}->{remoteTerm.node().name()}.{remoteTerm.name()}"
                        
                        if not self._graph.has_edge(bc['internal_node'].name(), remoteTerm.node().name(), key=edge_key):
                            self._graph.add_edge(
                                bc['internal_node'].name(),
                                remoteTerm.node().name(),
                                key=edge_key,
                                from_term=bc['internal_term'].name(),
                                to_term=remoteTerm.name()
                            )
                        
                        # Don't create default edge
                        self.sigNodeChanged.emit(localTerm.node())
                        return
    
    # Normal (non-subgraph) case: proceed with default edge creation
    localNode = localTerm.node().name()
    remoteNode = remoteTerm.node().name()
    key = localNode + '.' + localTerm.name() + '->' + remoteNode + '.' + remoteTerm.name()

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
```

**Testing:**
- Import subgraph
- Connect external node to placeholder at runtime (drag in GUI)
- Verify direct graph edge created
- Click "Apply" - verify graph compiles

---

### Phase 4: Handle Runtime Disconnections

**File:** `ami/flowchart/Flowchart.py`

**Modify `nodeTermDisconnected()` method (around line 1420):**

```python
async def nodeTermDisconnected(self, localTerm, remoteTerm):
    if remoteTerm.isOutput():
        t = remoteTerm
        remoteTerm = localTerm
        localTerm = t
    
    # CHECK: Is this a subgraph boundary disconnection?
    if hasattr(remoteTerm.node(), 'isSubgraph') and remoteTerm.node().isSubgraph:
        subgraph = remoteTerm.node()
        
        if remoteTerm.isInput():
            # Disconnecting External → Placeholder Input
            if subgraph.name() in self._subgraphs:
                sg_data = self._subgraphs[subgraph.name()]
                
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'input':
                        # Remove DIRECT graph edge: External → Internal
                        edge_key = f"{localTerm.node().name()}.{localTerm.name()}->{bc['internal_node'].name()}.{bc['internal_term'].name()}"
                        
                        if self._graph.has_edge(localTerm.node().name(), bc['internal_node'].name(), key=edge_key):
                            self._graph.remove_edge(localTerm.node().name(), bc['internal_node'].name(), key=edge_key)
                        
                        return
        
        elif remoteTerm.isOutput():
            # Disconnecting Placeholder Output → External
            if subgraph.name() in self._subgraphs:
                sg_data = self._subgraphs[subgraph.name()]
                
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == localTerm.name() and bc['type'] == 'output':
                        # Remove DIRECT graph edge: Internal → External
                        edge_key = f"{bc['internal_node'].name()}.{bc['internal_term'].name()}->{remoteTerm.node().name()}.{remoteTerm.name()}"
                        
                        if self._graph.has_edge(bc['internal_node'].name(), remoteTerm.node().name(), key=edge_key):
                            self._graph.remove_edge(bc['internal_node'].name(), remoteTerm.node().name(), key=edge_key)
                        
                        return
    
    # Normal (non-subgraph) case
    localNode = localTerm.node().name()
    remoteNode = remoteTerm.node().name()
    key = localNode + '.' + localTerm.name() + '->' + remoteNode + '.' + remoteTerm.name()

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
```

**Testing:**
- Connect external to subgraph
- Disconnect
- Verify graph edge removed
- Verify terminal colors update (black when disconnected)

---

### Phase 5: Fix _input_vars Tracing (Optional but Recommended)

**Goal:** When internal nodes connect via helpers, `_input_vars` should trace to actual external source

**File:** `ami/flowchart/Node.py`

**Modify `connected()` method (around line 384):**

```python
def connected(self, localTerm, remoteTerm):
    """Called whenever one of this node's terminals is connected elsewhere."""
    node = remoteTerm.node()

    if localTerm.isInput() and remoteTerm.isOutput():
        # NEW: If connecting from subgraph helper, trace to external source
        if hasattr(node, 'isSubgraphInput') and node.isSubgraphInput:
            # Helper → Internal connection
            # Look up which external nodes connect to this helper's placeholder terminal
            placeholder = node.rootNode
            placeholder_term = placeholder.terminals.get(remoteTerm.name())
            
            if placeholder_term:
                # Get all external connections to this placeholder terminal
                external_sources = placeholder_term.inputTerminals()
                if external_sources:
                    # Use first external source for _input_vars
                    remoteTerm = external_sources[0]
                    node = remoteTerm.node()
        
        # Existing subgraph tracing logic (keep for backwards compatibility)
        if hasattr(node, 'isSubgraphInput') and node.isSubgraphInput:
            remoteTerm = node.getInputTerm(remoteTerm)
            if remoteTerm:
                node = remoteTerm.node()
            else:
                node = None
        elif hasattr(node, 'isSubgraph') and node.isSubgraph:
            sg_output_term = node.subgraphOutputs.terminals.get(remoteTerm.name())
            if sg_output_term:
                internal_term = node.subgraphOutputs.getOutputTerm(sg_output_term)
                if internal_term:
                    remoteTerm = internal_term
                    node = remoteTerm.node()
                else:
                    node = None
            else:
                node = None

        if node and node.exportable() and node.values['alias']:
            self._input_vars[localTerm.name()] = node.values['alias']
        elif node and node.isSource():
            self._input_vars[localTerm.name()] = node.name()
        elif node and remoteTerm:
            self._input_vars[localTerm.name()] = '.'.join([node.name(), remoteTerm.name()])

    if not self.changed:
        self.changed = localTerm.isInput()

    self.sigTerminalConnected.emit(localTerm, remoteTerm)
```

**Testing:**
- Create subgraph with connection
- Check internal node's `_input_vars`
- Verify it points to external source, not helper

---

### Phase 6: Object Creation Order Documentation

**Critical Order Requirements:**

```python
# CORRECT ORDER:

# 1. Create SubgraphNode (auto-creates helpers)
subgraph = SubgraphNode(name, flowchart=self)
# Now: subgraph._graphicsItem exists
#      subgraph.subgraphInputs exists with _graphicsItem
#      subgraph.subgraphOutputs exists with _graphicsItem

# 2. Set graph references
subgraph.setGraph(self._graph)
# This also sets graph on helpers

# 3. Add graphicsItems to scenes (REQUIRED before creating ConnectionItems)
self.viewBox().addItem(subgraph.graphicsItem())  # Placeholder in root view
subgraph_view.viewBox().addItem(subgraph.subgraphInputs.graphicsItem())  # Helper in subgraph view

# 4. Create terminals (they need graphicsItems as parents)
placeholder_term = subgraph.addInput('foo', ttype=...)
# This creates:
#   - helper terminal (helper already has graphicsItem)
#   - placeholder terminal (placeholder already has graphicsItem)

# 5. Create Terminal._connections (terminals must exist and be in viewBoxes)
external_term.connectTo(placeholder_term, signal=False)
helper_term.connectTo(internal_term, signal=False)
# ConnectionItems auto-created and added to source's viewBox

# 6. Move ConnectionItems to correct views if needed
sg_visual = helper_term._connections[internal_term]
if sg_visual.scene():
    sg_visual.scene().removeItem(sg_visual)
subgraph_view.addItem(sg_visual)

# 7. Manually create graph edges
self._graph.add_edge(external_node.name(), internal_node.name(), ...)
```

**Common Mistakes to Avoid:**
- ❌ Creating ConnectionItem before adding nodes to viewBox
- ❌ Creating terminals before nodes exist
- ❌ Forgetting ConnectionItem auto-adds to source's viewBox
- ❌ Not calling setGraph() before using graph references

---

## Success Criteria

### Must Fix (Critical)
1. ✅ Can import `.fc` files as subgraphs without errors
2. ✅ Graph edges exist: External → Internal (direct, bypass helpers)
3. ✅ Terminal._connections exist: External → Placeholder, Helper → Internal
4. ✅ Graph compilation succeeds (no missing edges)
5. ✅ Helpers excluded from `self._graph` (is_visual_only=True)
6. ✅ No `to_operation()` methods on helpers

### Must Work (Functionality)
7. ✅ Terminal coloring correct (white when connected)
8. ✅ makeSubgraphFromSelection creates working subgraphs
9. ✅ _createSubgraphFromImport creates working subgraphs (now via unified method)
10. ✅ Save/reload preserves subgraph structure
11. ✅ Runtime connections (user drags new connection) work correctly

### Should Verify (Edge Cases)
13. ✅ Output boundaries work symmetrically to input boundaries
14. ✅ Disconnecting external → placeholder removes graph edge
15. ✅ Disconnecting helper → internal handled correctly
16. ✅ Node._input_vars traces to correct source node

---

## Testing Strategy

### Test 1: Import Subgraph (Critical Bug Fix)
1. Create simple flowchart: NodeA → NodeB → NodeC
2. Save as `test_subgraph.fc`
3. Clear flowchart
4. Import `test_subgraph.fc` as subgraph
5. **Verify:** No errors during import ✓
6. **Verify:** Graph edges exist in `self._graph` ✓
7. **Verify:** Helpers NOT in `self._graph` ✓
8. Connect external node → subgraph placeholder input
9. Click "Apply"
10. **Verify:** Graph compiles without errors ✓
11. **Verify:** Data flows correctly through subgraph ✓

### Test 2: Create from Selection
1. Create nodes in root view
2. Connect them: External → Internal1 → Internal2
3. Select Internal1, Internal2
4. Right-click → Make Subgraph
5. **Verify:** Subgraph created with correct boundary ✓
6. **Verify:** Graph edge External → Internal1 exists ✓
7. **Verify:** Helpers NOT in `self._graph` ✓
8. **Verify:** Terminal coloring correct (all white) ✓
9. Click "Apply"
10. **Verify:** Graph compiles and executes ✓

### Test 3: Save/Reload Cycle
1. Create subgraph with external connections
2. Save flowchart
3. Reload flowchart
4. **Verify:** Subgraph structure restored ✓
5. **Verify:** Graph edges restored ✓
6. **Verify:** Helpers NOT in `self._graph` ✓
7. **Verify:** External connections work ✓

### Test 4: Disconnection
1. Create subgraph with external connection
2. Disconnect external → placeholder
3. **Verify:** Graph edge removed ✓
4. **Verify:** Terminal colors updated (black for disconnected) ✓
5. Reconnect
6. **Verify:** Graph edge re-created ✓
7. **Verify:** Terminal colors updated (white) ✓

### Test 5: Runtime Connection
1. Import subgraph (no external connections)
2. Drag external node output → placeholder input (in GUI)
3. **Verify:** Connection created ✓
4. **Verify:** Direct graph edge created (External → Internal) ✓
5. Click "Apply"
6. **Verify:** Graph compiles ✓
7. **Verify:** Data flows correctly ✓

### Test 6: Output Boundaries
1. Create subgraph with output boundary
2. Connect internal → placeholder output → external
3. **Verify:** Graph edge Internal → External exists ✓
4. Click "Apply"
5. **Verify:** Data flows from internal to external ✓

---

## Implementation Notes

### Key Files to Modify

1. **ami/flowchart/SubgraphNode.py** (~4 changes)
   - Add `is_visual_only = True` to helpers (2 locations)
   - Delete `to_operation()` methods (2 deletions)

2. **ami/flowchart/Flowchart.py** (~500 lines, major refactor)
   - Remove helper registration (2 deletions)
   - Add `_discoverBoundaries()` method (new)
   - Add `_createSubgraph()` method (new, ~200 lines)
   - Replace `makeSubgraphFromSelection()` (~20 lines)
   - Replace `_createSubgraphFromImport()` (~30 lines)
   - Modify `nodeTermConnected()` (~40 lines addition)
   - Modify `nodeTermDisconnected()` (~30 lines addition)

3. **ami/flowchart/Node.py** (optional, ~10 lines)
   - Update `connected()` for better _input_vars tracing

**Total estimated changes:** ~700 lines across 2-3 files

### Estimated Implementation Time

- Phase 1 (Revert to visual-only): 1 hour
- Phase 2 (Consolidation): 4-6 hours (largest effort)
- Phase 3 (Runtime connections): 2 hours
- Phase 4 (Runtime disconnections): 1 hour
- Phase 5 (_input_vars fix): 1 hour (optional)
- Phase 6 (Documentation): Already done in this plan

**Total: 9-11 hours** (assuming Phase 2 consolidation is done)

### Migration from Current State

**Current state has:**
- ❌ Helpers in `self._graph` with `to_operation()`
- ❌ Missing graph edges (bug)
- ✅ Terminal._connections working

**Migration steps:**
1. Remove helpers from graph (Phase 1) - reverses Phase 2 of previous implementation
2. Implement manual edge management (Phases 2-5) - fixes the bug
3. Test thoroughly (all tests)

**Breaking changes:**
- Existing `.fc` files may have saved helper node references (already being filtered)
- This refactoring should be mostly compatible since helpers were already filtered from serialization

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Consolidation introduces bugs | Medium | High | Thorough testing after Phase 2, compare both code paths |
| Graph edge management errors | Medium | High | Extensive testing, careful key generation for edges |
| Terminal coloring breaks | Low | Medium | Terminal._connections already work, just keep them |
| Import still broken | Low | Critical | Manual edge creation should fix root cause |
| Runtime connections fail | Medium | High | Test extensively, handle all edge cases in nodeTermConnected |
| Object creation order violated | Low | Medium | Follow documented order, add assertions if needed |

---

## Rollback Plan

If implementation fails:

1. **Keep Phase 1 changes** (visual-only helpers) - this is the right architecture
2. **Revert Phases 2-5** if they cause issues
3. **Add manual edge creation** to existing `_createSubgraphFromImport()` as minimal fix:
   ```python
   # After existing connectTo calls, add:
   self._graph.add_edge(external_node.name(), internal_node.name(), ...)
   ```

This gives us the bug fix without the consolidation refactoring.

---

## Next Steps

1. ✅ Review this plan
2. ⏳ Implement Phase 1 (revert to visual-only)
3. ⏳ Test Phase 1 in isolation
4. ⏳ Implement Phase 2 (consolidation) OR skip to minimal fix
5. ⏳ Implement Phases 3-5 (runtime handling)
6. ⏳ Run full test suite
7. ⏳ Update SUBGRAPH_LIBRARY_IMPLEMENTATION.md with results

---

## Open Questions

- [ ] Should we do full consolidation (Phase 2) or minimal fix first?
- [ ] Do we need backward compatibility for old `.fc` files with helper references?
- [ ] Should `_input_vars` tracing (Phase 6) be mandatory or optional?
- [ ] Any additional edge cases to test?

---

**Plan Status:** Ready for implementation  
**Next Action:** Implement Phase 1 (revert to visual-only helpers)
