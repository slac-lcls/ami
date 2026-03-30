# Subgraph Cleanup Fix - Implementation Plan

**Date**: 2026-03-21  
**Branch**: `subgraph-refactor-clean`  
**Issue**: Clicking "New" button doesn't clean up subgraph placeholders, views, and toolbar buttons

---

## Problem Summary

### Current Behavior
When clicking the "New" toolbar button:
- ✅ Regular nodes are cleared
- ❌ Subgraph placeholders remain visible on canvas
- ❌ Subgraph views remain in ViewManager
- ❌ Subgraph toolbar buttons remain in toolbar
- ❌ `self._subgraphs` dict is not cleared

### Root Cause
`Flowchart.clear()` (line 1945-1956) only iterates through `self._graph.nodes`, but SubgraphNodes are **not** in `self._graph` because they have `is_visual_only = True`. Therefore, they are never encountered during cleanup.

---

## Solution Overview

Modify `Flowchart.clear()` to explicitly clean up subgraph components **after** cleaning regular nodes. This ensures:
1. Child nodes (inside subgraphs) are closed first via normal graph cleanup
2. Then subgraph wrappers (placeholders, views, helpers) are cleaned up
3. No risk of double-closing nodes

---

## Implementation Details

### File to Modify
**File**: `ami/flowchart/Flowchart.py`  
**Method**: `Flowchart.clear()`  
**Lines**: 1945-1956

### Current Code
```python
async def clear(self):
    """
    Remove all nodes from this flowchart except the original input/output nodes.
    """
    for name, node in self._graph.nodes(data='node'):
        if node is None:
            continue
        await self.broker.send_string(name, zmq.SNDMORE)
        await self.broker.send_pyobj(fcMsgs.CloseNode())
        node.close(emit=False)

    self._graph = nx.MultiDiGraph()
```

### New Code
```python
async def clear(self):
    """
    Remove all nodes from this flowchart except the original input/output nodes.
    """
    # Step 1: Clean up regular nodes (including nodes inside subgraphs)
    for name, node in self._graph.nodes(data='node'):
        if node is None:
            continue
        await self.broker.send_string(name, zmq.SNDMORE)
        await self.broker.send_pyobj(fcMsgs.CloseNode())
        node.close(emit=False)
    
    self._graph = nx.MultiDiGraph()
    
    # Step 2: Clean up subgraph placeholders and views
    # (Now that their children are already closed)
    subgraph_names = list(self._subgraphs.keys())
    for sg_name in subgraph_names:
        if sg_name not in self._subgraphs:
            continue  # Safety check (should not happen, but defensive)
        
        sg_data = self._subgraphs[sg_name]
        placeholder = sg_data['placeholder']
        
        # Remove view and toolbar button
        self.viewManager().removeView(sg_name)
        
        # Remove placeholder graphics from root view
        item = placeholder.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)
        
        # Clean up helper nodes (SubgraphInputs/Outputs)
        placeholder._subgraphInputs.close(emit=False)
        placeholder._subgraphOutputs.close(emit=False)
        
        # Clean up boundary connections (visual-only)
        for bc in sg_data.get('boundary_connections', []):
            if hasattr(bc.get('root_visual'), 'close'):
                bc['root_visual'].close()
            if hasattr(bc.get('subgraph_visual'), 'close'):
                bc['subgraph_visual'].close()
        
        # Remove from tracking
        del self._subgraphs[sg_name]
    
    # NOTE: self.subgraph_library intentionally NOT cleared
    # Templates persist across flowcharts (like node library)
```

---

## Key Design Decisions

### 1. Clean Nodes First, Then Subgraphs
- **Why**: Child nodes are in `self._graph` and get closed normally
- **Benefit**: No risk of double-closing nodes
- **Order**: Regular nodes → Subgraph wrappers (placeholders, views, helpers)

### 2. Keep Safety Check
```python
if sg_name not in self._subgraphs:
    continue
```
- **Why**: Defensive programming against edge cases
- **Cost**: One dict lookup (negligible)
- **Benefit**: Prevents crashes if assumptions change

### 3. Don't Clear Subgraph Library
- **Behavior**: `self.subgraph_library` persists across "New" operations
- **Rationale**: Consistent with node library behavior (doesn't clear on "New")
- **User Benefit**: Templates remain available for reuse in new flowcharts
- **Mental Model**: Library is a persistent palette of reusable components

---

## Testing Plan

### Test 1: Basic Cleanup
**Steps**:
1. Launch `ami-local random://`
2. Create flowchart with 3-4 regular nodes
3. Select 2-3 nodes → right-click → "Make Subgraph"
4. Verify subgraph view and toolbar button appear
5. Click "New" button in toolbar

**Expected Results**:
- ✅ All nodes disappear
- ✅ Subgraph placeholder disappears from canvas
- ✅ Subgraph toolbar button removed
- ✅ Only "root" view remains
- ✅ Canvas is empty
- ✅ No errors in console

### Test 2: Multiple Subgraphs
**Steps**:
1. Create flowchart with 6-8 nodes
2. Create 2 different subgraphs from different node sets
3. Verify both subgraph views and toolbar buttons exist
4. Click "New"

**Expected Results**:
- ✅ All nodes cleared
- ✅ Both subgraph placeholders removed
- ✅ Both toolbar buttons removed
- ✅ Clean slate

### Test 3: Empty Flowchart
**Steps**:
1. Launch fresh session
2. Immediately click "New"

**Expected Results**:
- ✅ No errors or crashes
- ✅ Empty flowchart remains

### Test 4: After Clear - New Flowchart
**Steps**:
1. Create and clear flowchart with subgraphs (Test 1)
2. Create new flowchart with different nodes
3. Create new subgraph

**Expected Results**:
- ✅ No artifacts from previous session
- ✅ New subgraph works correctly
- ✅ No duplicate toolbar buttons
- ✅ Clean state

### Test 5: Library Persistence
**Steps**:
1. Create flowchart with 2-3 nodes
2. Create subgraph named "MySubgraph"
3. Verify "MySubgraph" appears in library panel
4. Click "New" button
5. Drag "MySubgraph" from library to canvas

**Expected Results**:
- ✅ Flowchart is empty after "New"
- ✅ "MySubgraph" still visible in library panel
- ✅ Can drag "MySubgraph" from library to create new instance
- ✅ New instance works correctly with same structure

---

## Verification Checklist

After implementing and testing, verify:

- [ ] `self._graph` is empty MultiDiGraph `{}`
- [ ] `self._subgraphs` is empty dict `{}`
- [ ] `viewManager().views` contains only `{'root': ...}`
- [ ] Root view canvas is visually empty
- [ ] Toolbar shows only "root" button
- [ ] No errors or warnings in console
- [ ] `self.subgraph_library` still contains templates
- [ ] Can create new flowchart and use library templates

---

## Risk Assessment

**Risk Level**: LOW

**Why Low Risk**:
- ✅ Only modifies one method
- ✅ Adds cleanup, doesn't change existing node cleanup behavior
- ✅ Clear order of operations (nodes first, then wrappers)
- ✅ No breaking changes to API
- ✅ Defensive programming with safety checks
- ✅ Mirrors cleanup logic from `SubgraphNode.close()`

**Potential Issues & Mitigations**:

1. **If `removeView()` throws exception → subsequent subgraphs won't clean up**
   - *Mitigation*: Could wrap in try/except if needed
   - *Likelihood*: Low (removeView should handle gracefully)

2. **If a subgraph view is already removed → `removeView()` might error**
   - *Mitigation*: Check `removeView()` implementation for proper error handling
   - *Likelihood*: Very low (views should be present)

3. **Memory leaks from incomplete cleanup**
   - *Mitigation*: Follow same cleanup pattern as `SubgraphNode.close()`
   - *Likelihood*: Low (comprehensive cleanup of all components)

---

## Next Steps (Future Enhancements)

### 1. Update Template Feature

**Problem**: When user modifies a subgraph, the library template becomes stale. New instances dragged from library have the old version.

**Solution**: Add "Update Library Template" menu item to SubgraphNode context menu

**Implementation**:
- **File**: `ami/flowchart/SubgraphNode.py`
- **Location**: `SubgraphNodeGraphicsItem.buildMenu()` around line 199
- **Code**:
  ```python
  # Add menu item
  update_action = menu.addAction("Update Library Template")
  update_action.triggered.connect(self.updateTemplate)
  
  # Add method
  def updateTemplate(self):
      """Update the library template with current subgraph state"""
      if hasattr(self.node, 'flowchart') and self.node.flowchart:
          self.node.flowchart._addSubgraphToLibrary(
              self.node.name(), 
              update=True  # Force update
          )
  ```

**User Workflow**:
1. Create subgraph
2. Modify subgraph (add nodes, change connections)
3. Right-click placeholder → "Update Library Template"
4. Template updated in library
5. New instances dragged from library now have current version

**Benefits**:
- ✅ Explicit user control
- ✅ Simple implementation (uses existing `_addSubgraphToLibrary` with `update=True`)
- ✅ Non-disruptive (manual action)
- ✅ Discoverable (in context menu)

**Optional Enhancement**: Add confirmation dialog before updating

---

### 2. Template Library Cleanup Options

**Current Behavior**: Library templates persist across "New" operations (like node library)

**Potential Enhancements**:

#### Option A: "Clear Library" Button
Add explicit button in Library Manager to clear all ad-hoc templates (keep file-based ones)

#### Option B: Distinguish File-Based vs Ad-Hoc
In library tree, show different icons:
- 📄 File-based templates (from .fc files)
- 🔧 Ad-hoc templates (created in flowchart)

#### Option C: Right-Click to Remove Individual Templates
Add context menu on library tree items:
- "Remove from Library"
- "Update from Current Instance" (if instance exists)

**Recommendation**: Start with simple behavior (templates persist), add enhancements based on user feedback.

---

## Implementation Steps

1. **Read current code** to understand context
2. **Modify `Flowchart.clear()`** with new cleanup logic
3. **Test all 5 test scenarios** manually
4. **Verify checklist items**
5. **Document any issues found**
6. **Commit changes** with clear message

**Estimated Time**: 1-2 hours (including testing)

---

## Commit Message Template

```
Fix: Clean up subgraph components when clicking "New" button

When clicking "New" in the toolbar, subgraph placeholders, views,
and toolbar buttons were not being removed because SubgraphNodes
are not in self._graph (they have is_visual_only=True).

Changes:
- Modified Flowchart.clear() to explicitly clean subgraphs after nodes
- Added cleanup of views, graphics items, helpers, and boundary connections
- Preserves subgraph library templates (consistent with node library)

Testing:
- Verified cleanup with single and multiple subgraphs
- Confirmed library templates persist for reuse
- No errors or memory leaks observed

Files changed:
- ami/flowchart/Flowchart.py (+32 lines in clear() method)
```

---

## References

- **Architecture Guide**: `AGENTS.md`
- **Current Status**: `.opencode/plans/current-status.md`
- **Visual-Only Design**: Commit `c16ec5d` and `5ef6f9b`
- **SubgraphNode.close()**: `ami/flowchart/SubgraphNode.py:68-116` (cleanup pattern reference)
- **SubgraphLibrary**: `ami/flowchart/SubgraphLibrary.py`

---

**Plan Status**: READY FOR IMPLEMENTATION  
**Approval Needed**: YES  
**Next Action**: User approval → Implementation → Testing → Commit
