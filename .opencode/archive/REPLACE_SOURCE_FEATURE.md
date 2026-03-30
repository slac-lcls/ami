# Source Node Replacement Feature

## Overview
Added a "Replace with..." feature to SourceNode right-click menus that allows users to replace a source node with another source of the same type.

## Implementation Details

### Files Modified

#### 1. `ami/flowchart/Flowchart.py`
- **Line 187**: Added `node._flowchart = self` in `addNode()` to give nodes access to flowchart
- **Lines 198-253**: Added `replaceSourceNode(old_node, replacement_source_name)` method
  - Handles both merge (if replacement exists) and create scenarios
  - Transfers all connections from old node to replacement
  - Preserves node position when creating new node
  - Clears source kwargs (detector-specific)

#### 2. `ami/flowchart/NodeLibrary.py`
- **Lines 140-170**: Added `getSourcesByType(target_type, exclude_name=None)` to SourceLibrary
  - Filters sources by exact type match
  - Preserves hierarchical tree structure
  - Excludes specified source name (current node)
  - Returns OrderedDict matching sourceTree format

#### 3. `ami/flowchart/Node.py`
- **Lines 949-952**: Modified `SourceNodeGraphicsItem.buildMenu()` to add replace submenu
- **Lines 956-1000**: Added three new methods:
  - `buildReplaceMenu()`: Creates replace menu if alternatives exist
  - `_buildReplaceSubmenu()`: Recursively builds hierarchical submenu
  - `replaceTriggered()`: Handles menu selection and calls flowchart.replaceSourceNode()

### User Experience

1. **Right-click on SourceNode** → Menu appears with "Replace with..." option
2. **Hover over "Replace with..."** → Hierarchical submenu shows compatible sources
3. **Click on replacement source** → Node is replaced with selected source

### Behavior

#### When Replacement Source Already Exists
- Connections are transferred to the existing node
- Old node is removed
- No duplicate nodes created

#### When Replacement Source Doesn't Exist
- New node created at same position as old node
- Connections transferred to new node
- Old node removed
- Source kwargs cleared

### Menu Filtering

**Only shows sources that match ALL criteria:**
- ✅ Same exact type (e.g., Array2d → Array2d, int → int)
- ✅ Not the current source itself
- ✅ Available in current source_library

**Menu organization:**
- Hierarchical structure matches source tree
- Nested sources appear in submenus (e.g., delta → delta_t)
- Menu only appears if alternatives exist

### Examples

**Example 1: Replace cspad with jungfrau (both Array2d)**
```
Before: cspad → Roi2D
After:  jungfrau → Roi2D
```

**Example 2: Replace cspad with existing jungfrau**
```
Before: 
  cspad → Roi2D
  jungfrau → Binning
  
After:
  jungfrau → Roi2D
  jungfrau → Binning
  (cspad removed)
```

**Example 3: Nested source replacement**
```
Before: delta_t → SomeNode
Menu shows: delta → delta_t2 (if delta_t2 exists and is type int)
After: delta_t2 → SomeNode
```

### Edge Cases Handled

- ✅ No flowchart reference yet → Menu doesn't appear
- ✅ source_library is None → Menu doesn't appear
- ✅ No alternative sources of same type → Menu doesn't appear
- ✅ Replacement already exists → Connections merge
- ✅ Source kwargs → Cleared when replacing
- ✅ Display widgets → Automatically preserved by existing code
- ✅ Connection type compatibility → Guaranteed by exact type matching

### Testing

**Manual Testing Steps:**
1. Open AMI flowchart with multiple sources
2. Add a source node (e.g., cspad)
3. Connect it to a downstream node
4. Right-click source node → "Replace with..." → select alternative
5. Verify connections transferred correctly
6. Try replacing with existing node → verify merge behavior

**Automated Testing:**
- `test_replace_source.py` contains unit tests for `getSourcesByType()`
- Integration tests should be added to `tests/test_gui.py`

### Future Enhancements

Potential improvements (not implemented):
- Undo/redo support for replacements
- Confirmation dialog for destructive operations
- Visual feedback during replacement
- Batch replacement of multiple nodes
- Type-compatible replacement (e.g., int → float)

### Technical Notes

**Why store _flowchart reference on node?**
- source_library gets replaced dynamically via ZMQ
- Direct reference would become stale
- node._flowchart.source_library always gets current library

**Why clear source kwargs?**
- Source kwargs are detector-specific (e.g., ROI settings)
- Not meaningful when switching detectors
- User can re-enter if needed

**Why exact type matching?**
- Guarantees connection compatibility
- Prevents downstream type errors
- Simpler UX (no ambiguous choices)

**Connection transfer safety:**
- SourceNodes only have one 'Out' terminal
- All connections from old → new
- Type-safe by design (exact match)
- No partial states possible

## Dependencies

No new dependencies added. Uses existing:
- QtWidgets for menu building
- OrderedDict for tree structures
- Terminal.connectTo/disconnectFrom for connections

## Compatibility

- ✅ Backward compatible (new feature only)
- ✅ No changes to file formats
- ✅ No changes to existing APIs
- ✅ Gracefully degrades if source_library unavailable
