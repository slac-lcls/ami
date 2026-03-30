# Clean Subgraph Implementation Plan

**Starting Point**: Commit `6ad9f81` - "Add dynamic output support for subgraphs and fix NetworkX API bugs"

This commit already has a clean visual-only subgraph architecture. We just need to add runtime connection handling and import/export.

---

## Current State Analysis

### ✅ Already Implemented (Phase 1)
- Helper nodes (`SubgraphNodeInput`, `SubgraphNodeOutput`) have `is_visual_only = True`
- Helpers are NOT added to `self._graph`
- Helpers have NO `to_operation()` methods
- `makeSubgraphFromSelection()` works correctly for creating visual subgraphs
- Visual-only architecture is in place

### ❌ What's Missing
- Runtime connection handling (when user connects to subgraph placeholder)
- Runtime disconnection handling
- `_input_vars` tracing through subgraph boundaries
- Import/export functionality

---

## Implementation Plan

### Phase 3: Runtime Connection Handling (CRITICAL)

**File**: `ami/flowchart/Flowchart.py`

**Modify `nodeTermConnected()` method**:

When a connection is made to a subgraph placeholder, create a DIRECT graph edge from the external node to the internal node (bypassing the visual-only helpers).

```python
async def nodeTermConnected(self, localTerm, remoteTerm):
    # ... existing normalization code ...
    
    # CHECK: Is this a subgraph boundary connection?
    if hasattr(remoteTerm.node(), 'isSubgraph') and remoteTerm.node().isSubgraph:
        subgraph = remoteTerm.node()
        
        if remoteTerm.isInput():
            # External → Placeholder Input
            if subgraph.name() in self._subgraphs:
                sg_data = self._subgraphs[subgraph.name()]
                
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'input':
                        # Create DIRECT graph edge: External → Internal
                        edge_key = f"{localTerm.node().name()}.{localTerm.name()}->{bc['internal_node'].name()}.{bc['internal_term'].name()}"
                        
                        self._graph.add_edge(
                            localTerm.node().name(),
                            bc['internal_node'].name(),
                            key=edge_key,
                            from_term=localTerm.name(),
                            to_term=bc['internal_term'].name()
                        )
                        
                        # ⭐ CRITICAL BUG FIX: Update internal node's _input_vars
                        # Without this, the internal node doesn't know its input source
                        # and graph compilation will fail!
                        bc['internal_node'].connected(bc['internal_term'], localTerm)
                        
                        self.sigNodeChanged.emit(localTerm.node())
                        return
        
        elif remoteTerm.isOutput():
            # Similar logic for Placeholder Output → External
            # Create direct edge: Internal → External
            # Call: external_node.connected(external_term, internal_term)
    
    # ... existing default edge creation code ...
```

**Why This is Critical**:
- The graph edge alone is not enough!
- When nodes are compiled to operations via `to_operation()`, they use `input_vars()` to determine dependencies
- `input_vars()` reads from `_input_vars`, which is populated by the `connected()` method
- Without calling `.connected()`, the internal node's `_input_vars` is empty, so the compiled operation has no inputs
- This causes the "missing waveform node" bug we discovered

---

### Phase 4: Runtime Disconnection Handling

**File**: `ami/flowchart/Flowchart.py`

**Modify `nodeTermDisconnected()` method**:

```python
async def nodeTermDisconnected(self, localTerm, remoteTerm):
    # ... existing normalization code ...
    
    # CHECK: Is this a subgraph boundary disconnection?
    if hasattr(remoteTerm.node(), 'isSubgraph') and remoteTerm.node().isSubgraph:
        subgraph = remoteTerm.node()
        
        if remoteTerm.isInput():
            # Disconnecting External → Placeholder Input
            # Remove DIRECT graph edge: External → Internal
            if subgraph.name() in self._subgraphs:
                for bc in sg_data['boundary_connections']:
                    if bc['terminal_name'] == remoteTerm.name() and bc['type'] == 'input':
                        edge_key = f"{localTerm.node().name()}.{localTerm.name()}->{bc['internal_node'].name()}.{bc['internal_term'].name()}"
                        
                        if self._graph.has_edge(localTerm.node().name(), bc['internal_node'].name(), key=edge_key):
                            self._graph.remove_edge(localTerm.node().name(), bc['internal_node'].name(), key=edge_key)
                        
                        # Update internal node's _input_vars
                        bc['internal_node'].disconnected(bc['internal_term'], localTerm)
                        return
        
        elif remoteTerm.isOutput():
            # Similar logic for disconnecting outputs
    
    # ... existing default edge removal code ...
```

---

### Phase 5: Fix _input_vars Tracing

**File**: `ami/flowchart/Node.py`

**Modify `connected()` method**:

The issue: when an internal node receives a connection from a helper, it needs to trace back through the helper → placeholder → external chain to find the REAL source.

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
                else:
                    # No external connection yet, try fallback
                    remoteTerm = node.getInputTerm(remoteTerm)
                    if remoteTerm:
                        node = remoteTerm.node()
                    else:
                        node = None
            else:
                # Fallback to existing logic
                remoteTerm = node.getInputTerm(remoteTerm)
                if remoteTerm:
                    node = remoteTerm.node()
                else:
                    node = None
        
        # Existing subgraph tracing logic (for placeholder outputs)
        elif hasattr(node, 'isSubgraph') and node.isSubgraph:
            # Trace through SubgraphNode to find actual internal source
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

        # Set _input_vars based on traced source
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

**Note**: Phase 5 might not be strictly necessary if Phase 3's bug fix (calling `.connected()` with the correct terminals) is implemented correctly. The bug fix passes the external terminal directly, so tracing may not be needed. We can test and see.

---

### Phase 6: Add Import/Export

**File**: `ami/flowchart/Flowchart.py`

Add three methods (can be copied from commit `c8a57f9` with minor adjustments):

1. **`exportSubgraph(subgraph_name, fileName=None)`**
   - Collects nodes in the subgraph
   - Collects internal connections
   - Collects boundary metadata (inputs/outputs with terminal names and types)
   - Saves to .fc file with `subgraph_metadata` section

2. **`importSubgraphFromFile(fileName, pos=None)`**
   - Loads .fc file
   - Restores nodes with unique names (node_mapping)
   - Restores internal connections
   - Calls `_createSubgraphFromImport()` to build subgraph structure

3. **`_createSubgraphFromImport(name, nodes, boundary_inputs, boundary_outputs, node_mapping, pos, description)`**
   - Creates subgraph view and placeholder
   - Creates SubgraphInput/Output helper nodes
   - Processes boundary metadata to create placeholder terminals
   - Creates Terminal._connections between helpers and internal nodes (using `connectTo(signal=False)`)
   - Moves nodes and visual connections to subgraph view
   - Stores in `self._subgraphs`

**Key Point**: The import method creates the visual structure (Terminal._connections), but does NOT create graph edges. Those edges are created later when the user makes runtime connections (Phase 3).

---

## Architecture Summary

After these changes, the three-layer architecture will be:

1. **Terminal Layer (GUI/Visual)**:
   - Terminal._connections for visual ConnectionItems
   - Created by `connectTo(signal=False)` during subgraph creation
   - Used for GUI coloring and validation

2. **Graph Layer (Execution)**:
   - Direct edges: External → Internal (bypassing helpers)
   - Created by `nodeTermConnected()` during runtime connections
   - Created by manual `add_edge()` calls (NOT by Terminal signals)

3. **Visual Layer (UI)**:
   - ConnectionItems displayed in appropriate views
   - Moved between views during subgraph creation

Helpers are visual-only and never participate in execution.

---

## Testing Strategy

### Test 1: Selection-based Subgraph Creation
1. Create nodes: SourceNode → ProcessNode → ViewNode
2. Select ProcessNode + ViewNode
3. Create subgraph
4. **Expected**: Subgraph placeholder with one input
5. Connect SourceNode → placeholder
6. **Expected**: Graph compiles successfully, execution works

### Test 2: Subgraph Export
1. Create subgraph from selection
2. Export to .fc file
3. **Expected**: File contains nodes, connections, and boundary_inputs metadata

### Test 3: Subgraph Import (The Critical Test)
1. Import .fc file created in Test 2
2. **Expected**: Placeholder appears with correct input terminals
3. Connect external SourceNode → placeholder input
4. **Expected**: 
   - Direct graph edge created: SourceNode → internal ProcessNode ✓
   - Internal node's `_input_vars` set correctly ✓
   - Graph compiles with SourceNode → ProcessNode connection ✓
   - Execution works ✓

### Test 4: Runtime Disconnection
1. Disconnect external source from placeholder
2. **Expected**: Direct graph edge removed, `_input_vars` cleared

---

## Key Insight: The Root Cause

The bug we discovered was:

**Problem**: `self._graph` (NetworkX graph) had the correct edge, but the compiled execution graph was missing the source node.

**Root Cause**: When we created the direct graph edge in `nodeTermConnected()`, we forgot to call `.connected()` on the internal node. This meant:
- The edge existed in `self._graph` ✓
- But the internal node's `_input_vars` was empty ✗
- So when `to_operation()` was called, it had no input dependencies ✗
- The compiled graph was disconnected ✗

**Fix**: Call `internal_node.connected(internal_term, external_term)` right after creating the edge. This ensures `_input_vars` is populated correctly, and the compiled graph has the proper dependencies.

---

## Estimated Implementation Time

- Phase 3 (Runtime connections): 1 hour
- Phase 4 (Runtime disconnections): 30 minutes
- Phase 5 (_input_vars tracing): 30 minutes (may not be needed)
- Phase 6 (Import/Export): 2 hours
- Testing: 1 hour

**Total**: ~5 hours

---

## Rollback Plan

If issues arise:
1. Commit is `6ad9f81` - clean starting point
2. Changes are in git, easy to revert
3. Can compare with HEAD commit `c8a57f9` if needed

---

## Success Criteria

- ✅ Selection-based subgraphs work (already working)
- ✅ Can export subgraph to .fc file
- ✅ Can import .fc file as subgraph
- ✅ Runtime connections to imported subgraphs work
- ✅ Graph compiles correctly with all nodes and edges
- ✅ Execution works end-to-end
- ✅ No helper nodes in execution graph
- ✅ Direct edges (External → Internal) exist in execution graph
