# Phase 2: Unified Subgraph Creation - Implementation Plan

**Date**: 2026-03-18  
**Goal**: Implement unified `_createSubgraph()` method using code from `stash@{0}`  
**Estimated Time**: 2-3 hours  
**Status**: Ready to implement

---

## Overview

Currently we have **two separate implementations**:
- `makeSubgraphFromSelection()` - for user-created subgraphs (lines 202-463 in Flowchart.py)
- `_createSubgraphFromImport()` - for imported subgraphs (lines 581-823 in Flowchart.py)

This causes:
- ❌ Code duplication (~400 lines)
- ❌ Inconsistent behavior
- ❌ **The current bug**: helper nodes not in view before `connectTo()` called

The stash has a **unified approach** where both methods delegate to a single `_createSubgraph()` that handles both cases.

---

## Current Bug Context

**Error**: `AttributeError: 'NoneType' object has no attribute 'addItem'`  
**Location**: When dragging from library → `instantiateSubgraphFromLibrary()` → `importSubgraphFromFile()` → `_createSubgraphFromImport()` → line 667 `sg_input_term.connectTo(internal_term, signal=False)`

**Root cause**: `connectTo()` creates a `ConnectionItem` which calls `self.source.getViewBox().addItem(self)`, but the helper node isn't in any ViewBox yet.

**Stash solution**: Add helper to view **immediately before** creating connections, using pattern:
```python
if subgraph.subgraphInputs.graphicsItem().scene() is None:
    view.viewBox().addItem(subgraph.subgraphInputs.graphicsItem())
    # position it...

# NOW create connection (helper is in view)
helper_term.connectTo(internal_term, signal=False)
```

---

## Implementation Strategy

We'll extract **three methods** from the stash and replace our current implementations:

1. **`_discoverBoundaries()`** - Extract from stash lines 202-269 (~67 lines)
2. **`_createSubgraph()`** - Extract from stash lines 270-530 (~260 lines)  
3. **Refactor `makeSubgraphFromSelection()`** - Replace with delegation (stash lines 532-561)
4. **Refactor `_createSubgraphFromImport()`** - Replace with delegation (stash lines 563-617)

**Total code change**:
- Remove: ~400 lines (current implementations)
- Add: ~360 lines (unified implementation)
- **Net reduction**: ~40 lines
- **Maintenance benefit**: Single code path for all subgraph creation

---

## Step-by-Step Implementation

### Step 1: Extract `_discoverBoundaries()` from Stash

**Location**: Insert around line 200 in `ami/flowchart/Flowchart.py` (before `makeSubgraphFromSelection`)

**Source**: `stash@{0}:ami/flowchart/Flowchart.py` lines 202-269

**Method signature**:
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
```

**What it does**:
- Scans `self._graph` edges to find boundaries
- For inputs: External → Internal connections
- For outputs: Internal → External connections
- Returns unified metadata format

**No changes needed**: Copy directly from stash

---

### Step 2: Extract `_createSubgraph()` from Stash

**Location**: Insert around line 270 in `ami/flowchart/Flowchart.py` (after `_discoverBoundaries`)

**Source**: `stash@{0}:ami/flowchart/Flowchart.py` lines 270-530

**Method signature**:
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
```

**What it does**:
1. If `boundary_metadata` is None, calls `_discoverBoundaries()` to auto-detect
2. Creates view and SubgraphNode placeholder
3. Adds placeholder to root view at specified position
4. **For each boundary**:
   - Adds terminal to placeholder
   - **Checks if helper is in scene, adds if not** ← **This fixes the bug!**
   - Disconnects original connection if it exists (for selection)
   - Creates visual connections (helper ↔ internal)
   - Moves visual connections to subgraph view
   - Creates direct graph edges if external node exists (for selection)
   - Stores boundary info
5. Moves internal nodes and connections to subgraph view
6. Stores subgraph metadata in `self._subgraphs`
7. Returns the placeholder

**Key pattern that fixes our bug** (appears twice, for inputs and outputs):
```python
# Add helper to subgraph view if not already added
if subgraph.subgraphInputs.graphicsItem().scene() is None:
    view.viewBox().addItem(subgraph.subgraphInputs.graphicsItem())
    # Position to left of internal nodes
    if nodes:
        leftmost_x = min(n.graphicsItem().pos().x() for n in nodes)
        first_y = nodes[0].graphicsItem().pos().y()
        subgraph.subgraphInputs.graphicsItem().setPos(leftmost_x - 200, first_y)

# ... then later ...

helper_term.connectTo(internal_term, signal=False)  # Now safe!
```

**Changes needed**:
- ✅ **None!** Copy directly from stash
- The method handles both selection and import cases automatically
- Uses `node_mapping` parameter to remap names for imports
- Uses `boundary_metadata` parameter to accept pre-defined boundaries for imports

---

### Step 3: Replace `makeSubgraphFromSelection()`

**Current location**: Lines 202-463 in `ami/flowchart/Flowchart.py`

**New implementation** (from stash lines 532-561):
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

**Changes from current**:
- From ~260 lines → ~30 lines
- All logic moved to `_createSubgraph()`
- `boundary_metadata=None` means auto-discover

---

### Step 4: Replace `_createSubgraphFromImport()`

**Current location**: Lines 581-823 in `ami/flowchart/Flowchart.py`

**New implementation** (from stash lines 563-617):
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

**Changes from current**:
- From ~240 lines → ~55 lines
- Converts import-specific metadata to unified format
- Passes to `_createSubgraph()` with `boundary_metadata` and `node_mapping`
- Key: `external_node=None` because imports have no external connections yet

---

## Detailed Execution Plan

### Phase A: Preparation (5 min)

1. **Verify current state**:
   ```bash
   git status  # Should show Flowchart.py and FlowchartGraphicsView.py modified
   ```

2. **Save current work**:
   ```bash
   git stash push -m "WIP: bug fix #1 (instantiateSubgraphFromLibrary)"
   ```

3. **Verify we're on clean commit**:
   ```bash
   git log --oneline -1  # Should show c16ec5d
   ```

### Phase B: Extract Methods from Stash (30 min)

4. **Extract `_discoverBoundaries()`**:
   ```bash
   git show 'stash@{0}:ami/flowchart/Flowchart.py' | sed -n '202,269p' > /tmp/discoverBoundaries.py
   ```
   - Review extracted code
   - Insert at line ~200 in Flowchart.py

5. **Extract `_createSubgraph()`**:
   ```bash
   git show 'stash@{0}:ami/flowchart/Flowchart.py' | sed -n '270,530p' > /tmp/createSubgraph.py
   ```
   - Review extracted code (~260 lines)
   - Insert at line ~270 in Flowchart.py

6. **Verify imports are present**:
   - Check that `from qtpy import QtGui, QtCore` exists
   - Check that `from ami.flowchart.Terminal import ConnectionItem` exists

### Phase C: Replace Existing Methods (30 min)

7. **Replace `makeSubgraphFromSelection()`**:
   - Extract new version from stash lines 532-561
   - Replace current implementation (lines 202-463)
   - Net: Remove ~260 lines, add ~30 lines

8. **Replace `_createSubgraphFromImport()`**:
   - Extract new version from stash lines 563-617
   - Replace current implementation (lines 581-823)
   - Net: Remove ~240 lines, add ~55 lines

### Phase D: Testing (45 min)

9. **Syntax check**:
   ```bash
   python -m py_compile ami/flowchart/Flowchart.py
   ```

10. **Test 1: Create subgraph from selection**:
    ```bash
    ami-local random://
    # Select nodes, create subgraph
    # Expected: Works as before
    ```

11. **Test 2: Save/load with subgraph**:
    ```bash
    # Save flowchart with subgraph
    # Reload
    # Expected: Loads correctly (regression test)
    ```

12. **Test 3: Import from library** (The critical test!):
    ```bash
    # Manage Libraries → Load export.fc → Apply
    # Drag from library tree to canvas
    # Expected: ✅ No AttributeError!
    # Expected: ✅ Subgraph instance appears
    # Expected: ✅ Helper nodes visible in subgraph view
    ```

13. **Test 4: Runtime connections**:
    ```bash
    # Add source node
    # Connect to imported subgraph placeholder
    # Expected: Works correctly
    ```

### Phase E: Cleanup and Commit (15 min)

14. **Re-apply bug fix #1**:
    ```bash
    git stash pop  # Restore instantiateSubgraphFromLibrary changes
    ```

15. **Review all changes**:
    ```bash
    git diff ami/flowchart/Flowchart.py | less
    git diff ami/flowchart/FlowchartGraphicsView.py
    ```

16. **Commit**:
    ```bash
    git add ami/flowchart/Flowchart.py ami/flowchart/FlowchartGraphicsView.py
    git commit -m "Implement Phase 2: Unified subgraph creation method

- Extract _discoverBoundaries() from stash (auto-detect boundaries)
- Extract _createSubgraph() unified method from stash (~260 lines)
- Refactor makeSubgraphFromSelection() to delegate to unified method
- Refactor _createSubgraphFromImport() to delegate to unified method

Bug Fix:
- Fixes AttributeError when dragging from library
- Helper nodes now added to view BEFORE creating connections
- Pattern: if helper.scene() is None: add to view

Code Reduction:
- Removed ~400 lines of duplicate logic
- Added ~360 lines of unified implementation
- Net: ~40 line reduction
- Maintenance: Single code path for all subgraph creation

Based on stash@{0} unified architecture.
Implements originally planned Phase 2 from subgraph-refactoring.md."
    ```

---

## Code Extraction Commands

For easy copy-paste during implementation:

```bash
# Extract _discoverBoundaries
git show 'stash@{0}:ami/flowchart/Flowchart.py' | sed -n '202,269p'

# Extract _createSubgraph
git show 'stash@{0}:ami/flowchart/Flowchart.py' | sed -n '270,530p'

# Extract new makeSubgraphFromSelection
git show 'stash@{0}:ami/flowchart/Flowchart.py' | sed -n '532,561p'

# Extract new _createSubgraphFromImport
git show 'stash@{0}:ami/flowchart/Flowchart.py' | sed -n '563,617p'
```

---

## Expected Results

### Before (Current State)
- ❌ Two separate implementations (~400 lines)
- ❌ Code duplication
- ❌ Bug: `AttributeError` when dragging from library
- ❌ Inconsistent behavior between selection and import

### After (Phase 2 Complete)
- ✅ Single unified implementation (~360 lines)
- ✅ No code duplication
- ✅ Bug fixed: Helper-in-view pattern prevents `AttributeError`
- ✅ Consistent behavior for all subgraph creation
- ✅ Easier to maintain and extend
- ✅ Matches proven stash architecture

---

## Risk Assessment

### Low Risk ✅
- **Proven code**: Extracted from working stash
- **Clear patterns**: Well-documented unified approach
- **Regression protection**: Existing save/load tests
- **Incremental**: Can test each step

### Mitigation Strategies
1. **Save work before starting**: `git stash` current changes
2. **Test after each phase**: Verify no regressions
3. **Keep stash as reference**: Easy to compare if issues arise
4. **Can revert easily**: Clean git history allows easy rollback

---

## Questions Before Implementation

1. **Timing**: Should we implement this now, or after completing the current testing session?
   - **Recommendation**: Now - fixes the blocking bug and simplifies remaining tests

2. **Testing scope**: Should we test all features after Phase 2, or just the critical path?
   - **Recommendation**: Test critical path (drag-and-drop), then regression test (save/load)

3. **Stash preservation**: Should we create a new stash with bug fix #1 before starting?
   - **Recommendation**: Yes - keeps our instantiateSubgraphFromLibrary fix safe

---

## Next Steps After Phase 2

Once Phase 2 is complete and tested:

1. ✅ Continue with remaining tests:
   - Test 3: Drag-and-drop from library (should now work!)
   - Test 4: Runtime connections
   - Test 5: Runtime disconnections
   - Test 6: Hover display

2. ✅ Review Node.py changes from stash (if needed)

3. ✅ Remove debug logging (emoji prints)

4. ✅ Final commit with all features working

5. ✅ Update documentation

---

## Estimated Timeline

| Phase | Task | Time | Running Total |
|-------|------|------|---------------|
| A | Preparation | 5 min | 5 min |
| B | Extract methods | 30 min | 35 min |
| C | Replace methods | 30 min | 65 min |
| D | Testing | 45 min | 110 min |
| E | Cleanup & commit | 15 min | **125 min** |

**Total: ~2 hours**

---

## Success Criteria

Phase 2 will be considered successful when:

1. ✅ All three methods extracted and integrated
2. ✅ Syntax check passes (no Python errors)
3. ✅ Create subgraph from selection works (regression)
4. ✅ Save/load with subgraphs works (regression)
5. ✅ **Drag from library works** (bug fixed!)
6. ✅ Runtime connections work
7. ✅ Code is cleaner and more maintainable
8. ✅ All changes committed with clear message

---

**Ready to proceed when you are!** 🚀
