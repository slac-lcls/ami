# Subgraph Cleanup Fix - Commit Summary

**Date**: 2026-03-21  
**Branch**: `subgraph-refactor-clean`  
**Commit**: `7fadf3b`  
**Status**: ✅ COMMITTED

---

## Commit Details

**Hash**: `7fadf3bb322422b41c9a4d9ade72cecd58a39d55`  
**Author**: Seshu Yamajala <syamajala@gmail.com>  
**Date**: Sat Mar 21 00:45:25 2026 -0700

**Message**:
```
Fix: Clean up subgraph components when clicking 'New' button

When clicking 'New' in the toolbar, subgraph placeholders, views,
and toolbar buttons were not being removed because SubgraphNodes
are not in self._graph (they have is_visual_only=True).

Additionally, if user was viewing a subgraph when clicking 'New',
the currentView would point to a deleted view causing UI issues.

Changes:
- Switch to root view BEFORE cleanup to prevent view state issues
- Modified Flowchart.clear() to explicitly clean subgraphs after nodes
- Added cleanup of views, graphics items, helpers, and boundary connections
- Preserves subgraph library templates (consistent with node library)

Testing:
- Verified cleanup with single and multiple subgraphs
- Verified view switching when clearing from subgraph view
- Confirmed library templates persist for reuse
- No errors or memory leaks observed

Files changed:
- ami/flowchart/Flowchart.py (+44 lines in clear() method)
```

**Stats**:
```
 ami/flowchart/Flowchart.py | 39 +++++++++++++++++++++++++++++++++++++++
 1 file changed, 39 insertions(+)
```

---

## What Was Fixed

### Issue 1: Subgraph Components Not Cleaned Up ✅

**Problem**: When clicking "New" button in toolbar:
- Subgraph placeholders remained visible on canvas
- Subgraph views stayed in ViewManager
- Subgraph toolbar buttons persisted
- `self._subgraphs` dict was not cleared

**Root Cause**: `Flowchart.clear()` only iterated through `self._graph.nodes`, but SubgraphNodes have `is_visual_only=True` so they're not in the graph.

**Solution**: Added explicit subgraph cleanup loop in `clear()` method:
1. Remove views and toolbar buttons via `viewManager().removeView()`
2. Remove placeholder graphics from root view
3. Close helper nodes (SubgraphInputs/Outputs)
4. Close boundary connections
5. Clear `self._subgraphs` tracking dict

---

### Issue 2: View State Bug ✅

**Problem**: If user was viewing a subgraph when clicking "New":
- The subgraph view would be deleted
- But `viewManager().currentView` still pointed to the deleted view
- Result: blank/broken UI

**Root Cause**: Views were deleted without checking/updating currentView state.

**Solution**: Added view switch to root BEFORE any cleanup:
```python
# Switch to root view before clearing (in case we're on a subgraph view)
self.viewManager().displayView(name='root')
```

This ensures currentView is always valid during and after cleanup.

---

## Technical Details

### File Modified
**File**: `ami/flowchart/Flowchart.py`  
**Method**: `Flowchart.clear()` (lines 1945-1995)  
**Changes**: +39 insertions (Git shows 39, plan document had 44 - Git is correct)

### Code Structure

```python
async def clear(self):
    """Remove all nodes from this flowchart except the original input/output nodes."""
    
    # [NEW] Step 0: Switch to root view
    self.viewManager().displayView(name='root')
    
    # Step 1: Clean up regular nodes (existing, with new comment)
    for name, node in self._graph.nodes(data='node'):
        # ... existing code ...
    self._graph = nx.MultiDiGraph()
    
    # [NEW] Step 2: Clean up subgraph placeholders and views
    subgraph_names = list(self._subgraphs.keys())
    for sg_name in subgraph_names:
        if sg_name not in self._subgraphs:
            continue  # Safety check
        
        sg_data = self._subgraphs[sg_name]
        placeholder = sg_data['placeholder']
        
        # Remove view and toolbar button
        self.viewManager().removeView(sg_name)
        
        # Remove placeholder graphics
        item = placeholder.graphicsItem()
        if item.scene() is not None:
            item.scene().removeItem(item)
        
        # Clean up helper nodes
        placeholder._subgraphInputs.close(emit=False)
        placeholder._subgraphOutputs.close(emit=False)
        
        # Clean up boundary connections
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

## Design Decisions

### 1. Clean Nodes First, Then Subgraphs
**Reasoning**: Child nodes (inside subgraphs) are in `self._graph`, so they get closed normally in Step 1. Then Step 2 cleans up the subgraph wrappers. This avoids double-closing nodes.

### 2. Switch to Root View First
**Reasoning**: Prevents view state corruption. Simpler than checking currentView during cleanup. Consistent with other methods (see lines 611, 828, 1092).

### 3. Preserve Subgraph Library
**Reasoning**: Consistent with node library behavior - templates persist across "New" operations like a palette of reusable components.

### 4. Safety Check in Loop
**Reasoning**: Defensive programming. The `if sg_name not in self._subgraphs: continue` check prevents crashes if state changes unexpectedly (e.g., in async context).

---

## Testing Results

**Manual Testing**: ✅ Verified by user  
**Tests Performed**:
- Basic cleanup with single subgraph
- Multiple subgraphs cleanup
- View switching when clearing from subgraph view
- Library template persistence

**Results**:
- ✅ All placeholders removed
- ✅ All toolbar buttons removed
- ✅ View switches to root correctly
- ✅ Library templates persist
- ✅ No errors or crashes

---

## Future Enhancements (Documented)

### 1. Update Template Feature
Add "Update Library Template" menu item to SubgraphNode context menu to sync library templates with modified subgraphs.

**File**: `ami/flowchart/SubgraphNode.py`  
**Implementation**: ~5 lines using existing `_addSubgraphToLibrary(name, update=True)`  
**Documented In**: `.opencode/plans/subgraph-cleanup-fix.md`

### 2. Library Cleanup Options
Various approaches for managing subgraph library templates:
- Clear Library button
- Visual distinction (file-based vs ad-hoc icons)
- Right-click to remove individual templates

**Documented In**: `.opencode/plans/subgraph-cleanup-fix.md`

---

## Branch Status

**Current Branch**: `subgraph-refactor-clean`  
**Commits Ahead of Origin**: 1 (this commit)  
**Remote Branch**: `origin/subgraph-refactor-clean`

**To Push**:
```bash
git push origin subgraph-refactor-clean
```

---

## Related Commits

**Recent History**:
```
7fadf3b (HEAD) Fix: Clean up subgraph components when clicking 'New' button
5ef6f9b Fix subgraph import and improve UX
c16ec5d Implement visual-only subgraph architecture with library support
6ad9f81 Add dynamic output support for subgraphs and fix NetworkX API bugs
```

**Key Commit**: This fix builds on the visual-only architecture implemented in commit `c16ec5d`.

---

## Documentation

**Implementation Plans**:
- `.opencode/plans/subgraph-cleanup-fix.md` - Original implementation plan
- `.opencode/plans/implementation-status.md` - Implementation tracking and test plan
- `.opencode/plans/commit-summary.md` - This file

**Architecture Reference**:
- `AGENTS.md` - AMI architecture guide
- `.opencode/plans/current-status.md` - Overall subgraph system status

---

## Success Criteria Met

- ✅ Code committed successfully
- ✅ No compilation errors
- ✅ Manual testing verified both issues fixed
- ✅ Comprehensive commit message
- ✅ Future enhancements documented
- ✅ Clear implementation plan available

---

**Status**: COMPLETE  
**Next Steps**: Optional - Push to remote, merge to master (when ready)  
**Contact**: AI Assistant session completed successfully
