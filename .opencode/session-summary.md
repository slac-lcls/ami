# AMI Subgraph Boundary Metadata Bug Fix - Session Summary

**Date:** March 17, 2026

## Goal

Fix critical bugs in AMI's subgraph boundary metadata export/import system. The subgraph library feature was previously implemented, but the export/import roundtrip is broken because it violates the **visual-only connection design principle** for subgraphs.

## Instructions

- **Critical Design Principle**: ALL subgraph boundary connections MUST be visual-only (using `ConnectionItem` objects), NOT actual Terminal connections (no `terminal._connections` entries)
- **Export must read from `sg_data['boundary_connections']`** - NOT from `terminal.connections()` which is always empty by design
- **Import must create visual-only connections** - NO `connectTo()` calls allowed
- **Maintain consistency**: Subgraphs created from selection and imported subgraphs must behave identically (both use visual-only connections)
- Three distinct fixes needed:
  1. Fix export logic to read from `boundary_connections` list
  2. Fix import logic to remove `connectTo()` calls (keep visual-only)
  3. Store `boundary_connections` during import for future re-exports

## Discoveries

1. **Root cause of broken export**: Current export code checks `terminal.connections()` which is always empty for visual-only connections, resulting in `null` values for `internal_node` and `internal_terminal` in exported metadata
2. **Root cause of broken import**: Current import code calls `connectTo()` which creates actual Terminal connections, violating the visual-only design principle
3. **The source of truth**: `sg_data['boundary_connections']` list contains all the information needed for export - it's built during `makeSubgraphFromSelection()` and stores visual connection info
4. **Inconsistency**: Imported subgraphs were creating Terminal connections while manually-created subgraphs used visual-only - this has been fixed
5. **Missing persistence**: Imported subgraphs didn't build `boundary_connections` list, so they couldn't be re-exported correctly - this has been fixed

## Accomplished

### ✅ Completed Changes

**Fix 1: Export Logic (DONE)**
- File: `ami/flowchart/Flowchart.py` lines ~688-744
- Changed from reading `terminal.connections()` to reading `sg_data['boundary_connections']`
- Builds maps (`input_bc_map` and `output_bc_map`) from boundary_connections list
- Exports correct `internal_node` and `internal_terminal` from the boundary connection objects
- Applied to both boundary inputs and boundary outputs

**Fix 2: Import Logic (DONE)**
- File: `ami/flowchart/Flowchart.py` lines ~1000-1017
- Removed `connectTo()` call that was creating Terminal connections
- Removed connection hiding logic (no longer needed)
- Now creates ONLY visual `ConnectionItem` connections
- Maintains terminal recoloring for visual feedback

**Fix 3: Boundary Connections Storage (DONE)**
- File: `ami/flowchart/Flowchart.py` lines ~1018-1054
- Added code after connection creation to build `boundary_connections` list
- Stores visual connection reference in `conn_info`
- Builds boundary_connections structure matching the format from `makeSubgraphFromSelection()`
- Stores in `self._subgraphs[name]['boundary_connections']` for future exports

### 🔄 Previous Session Work (Context)

Earlier in the conversation, we also:
- Fixed subgraph view cleanup on "New"/"Open" (added explicit cleanup in `Flowchart.clear()`)
- Improved exception handling throughout (removed overly-broad try-except blocks, used `printExc()`)
- Fixed export dialog to prefill description from existing subgraph
- Fixed `FileDialog.getSaveFileName()` tuple unpacking bug
- Attempted to add helper nodes to imported subgraphs (had issues with `updateTerminals()`)

### 📝 Todo Status

- [x] Fix export to read from boundary_connections
- [x] Fix import to create visual-only connections  
- [x] Add boundary_connections storage during import
- [ ] **NEXT: Test export/import roundtrip**

## Relevant files / directories

### Modified Files
- **`ami/flowchart/Flowchart.py`** - Main file with all three fixes applied
  - Lines 688-744: Export boundary metadata (reads from boundary_connections)
  - Lines 1000-1017: Import visual connection creation (no connectTo())
  - Lines 1018-1054: Build and store boundary_connections during import
  
### Test Files (for validation)
- **`test.fc`** - Original flowchart with all nodes
- **`subgraph.fc`** - Flowchart with a subgraph created from selection
- **`export.fc`** - Exported subgraph file (previously showed `null` values, should now have correct metadata)

### Related Files (context)
- **`ami/flowchart/SubgraphLibrary.py`** - Library management classes (already implemented)
- **`ami/flowchart/SubgraphNode.py`** - Subgraph placeholder node class
- **`ami/flowchart/Editor.py`** - Library editor UI
- **`.opencode/plans/subgraph-library.md`** - Original implementation plan (needs updating with bug fix info)

### Key Code Sections
- **`makeSubgraphFromSelection()` lines ~357-391** - Shows how boundary_connections are built for manually created subgraphs (this is the pattern we're matching)
- **`exportSubgraph()` lines ~675-767** - Export method now fixed to use boundary_connections
- **`importSubgraphFromFile()` lines ~769-1062** - Import method now fixed for visual-only connections

## Next Steps

**READY TO TEST:**
1. **Create a fresh subgraph** from selection with boundary inputs (e.g., external node → internal node)
2. **Export the subgraph** to a `.fc` file
3. **Verify export metadata** - check that `internal_node` and `internal_terminal` are NOT null
4. **Import the subgraph** into a new/different flowchart
5. **Verify imported structure**:
   - Placeholder has input terminals
   - SubgraphInputs node is visible in subgraph view
   - Visual connections exist (check scene items)
   - NO Terminal connections exist (verify `terminal.connections()` returns `{}`)
6. **Export the imported subgraph** again and verify metadata matches original

**If tests pass:** The bug is fixed! Visual-only design is preserved, export/import roundtrip works correctly.

**If tests fail:** Debug by checking which step fails and examining the actual vs expected behavior.

## Code Changes Summary

All changes were made to `ami/flowchart/Flowchart.py`:

### 1. Export Logic (exportSubgraph method)
```python
# Build maps from boundary_connections list
input_bc_map = {}
output_bc_map = {}
for bc in sg_data.get('boundary_connections', []):
    key = (bc['placeholder_node'], bc['placeholder_terminal'])
    if bc['direction'] == 'input':
        input_bc_map[key] = bc
    else:
        output_bc_map[key] = bc

# Use maps to get internal connection info
for term_name, term_type in inputs:
    bc = input_bc_map.get((name, term_name))
    if bc:
        boundary_inputs.append({
            'name': term_name,
            'type': term_type,
            'internal_node': bc['internal_node'],
            'internal_terminal': bc['internal_terminal']
        })
```

### 2. Import Logic (importSubgraphFromFile method)
```python
# Create visual-only connection (NO connectTo())
conn = ConnectionItem(ext_term, int_term, scene=self.scene())
ext_term.recolor()
```

### 3. Boundary Connections Storage (importSubgraphFromFile method)
```python
# Build boundary_connections list
boundary_connections = []
for conn_info in connections_to_create:
    boundary_connections.append({
        'direction': conn_info['direction'],
        'placeholder_node': name,
        'placeholder_terminal': conn_info['placeholder_terminal'],
        'internal_node': conn_info['internal_node'],
        'internal_terminal': conn_info['internal_terminal'],
        'connection': conn_info['connection']
    })

self._subgraphs[name]['boundary_connections'] = boundary_connections
```

## Testing Notes

When testing, pay special attention to:
- Visual connections should appear correctly in the GUI
- Exported `.fc` files should contain valid `internal_node` and `internal_terminal` values (not null)
- Multiple export/import cycles should work without data loss
- Subgraphs created manually vs imported should behave identically
- The `boundary_connections` list should persist through save/load cycles
