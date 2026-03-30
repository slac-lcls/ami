# Unified Library Editor

## Overview
Consolidated the separate "Manage Library" and "Manage Subgraph Library" dialogs into a single **"Manage Libraries"** window that handles both `.py` files (nodes) and `.fc` files (subgraphs).

## Benefits

### User Experience
- **Single dialog** instead of two separate ones
- **Drag-and-drop both file types** at once
- **Clear visual separation** with side-by-side tree views
- **Consistent workflow** for managing all library content

### Implementation
- **Less code duplication** - shared file loading logic
- **Easier maintenance** - one place to update
- **Better UX** - natural to manage all libraries together

## UI Layout

```
┌─────────────────────────────────────────────┐
│         Manage Libraries                    │
├─────────────────────────────────────────────┤
│  [Load Files]  [Load Directory]             │
├───────────────────────┬─────────────────────┤
│  Nodes (.py)          │  Subgraphs (.fc)    │
│  ├─ module1           │  ├─ MyFilter        │
│  │  ├─ NodeA          │  ├─ ROI_Analyzer    │
│  │  └─ NodeB          │  └─ DataCleanup     │
│  └─ module2           │                     │
│     └─ NodeC          │                     │
├───────────────────────┴─────────────────────┤
│              [Apply]                        │
└─────────────────────────────────────────────┘
```

## How It Works

### File Selection
Users can load files in three ways:
1. **Load Files** button - multi-select `.py` and/or `.fc` files
2. **Load Directory** button - scans for both `.py` and `.fc` files
3. File filter: "Python and Flowchart files (*.py *.fc)"

### Automatic Routing
Files are automatically sorted by extension:
- `.py` files → Nodes tree (left panel)
- `.fc` files → Subgraphs tree (right panel)

### Apply Action
Single "Apply" button updates both libraries and their UI trees.

## Implementation Details

### New Class: `UnifiedLibraryEditor`

```python
class UnifiedLibraryEditor(QtWidgets.QWidget):
    def __init__(self, ctrlWidget, nodeLibrary, subgraphLibrary):
        # Manages both libraries
        self.nodeLibrary = nodeLibrary
        self.subgraphLibrary = subgraphLibrary
        
    def loadPythonFiles(self, pths):
        # Handle .py files → node library
        
    def loadFlowchartFiles(self, pths):
        # Handle .fc files → subgraph library
        
    def applyClicked(self):
        # Update both libraries and UI trees
```

### Backward Compatibility

The unified editor maintains backward compatibility:
- Old `paths` key in state → treated as node paths
- Old `subgraph_library` state → still loaded correctly
- New format uses `node_paths` and `subgraph_paths`

### State Format

**Old (separate editors):**
```json
{
  "library": {"paths": ["/path/to/nodes.py"]},
  "subgraph_library": {"paths": ["/path/to/subgraph.fc"]}
}
```

**New (unified editor):**
```json
{
  "library": {
    "node_paths": ["/path/to/nodes.py"],
    "subgraph_paths": ["/path/to/subgraph.fc"]
  }
}
```

## Migration Notes

### Removed Components
- ❌ `SubgraphLibraryEditor` class (old, separate dialog)
- ❌ "Manage Subgraph Library" button
- ❌ Separate subgraph library persistence

### Added Components
- ✅ `UnifiedLibraryEditor` class
- ✅ Single "Manage Libraries" button
- ✅ Dual-tree UI (nodes | subgraphs)

### UI Changes
**Before:**
```
[Manage Library]  [Manage Subgraph Library]  [Rate Label]
```

**After:**
```
[Manage Libraries]                            [Rate Label]
```

## Usage Workflow

### Example 1: Load Both Types
1. Click "Manage Libraries"
2. Click "Load Directory"
3. Select folder containing both `.py` and `.fc` files
4. Files automatically sorted to correct trees
5. Click "Apply"
6. Both libraries updated

### Example 2: Load Specific Files
1. Click "Manage Libraries"
2. Click "Load Files"
3. Multi-select:
   - `custom_node.py`
   - `roi_filter.fc`
   - `data_cleanup.fc`
4. Python file goes to Nodes tree
5. FC files go to Subgraphs tree
6. Click "Apply"

### Example 3: Directory Scan
1. Click "Load Directory"
2. Select project folder
3. Scans recursively for:
   - All `.py` files (except `_*.py`)
   - All `.fc` files
4. Populates both trees
5. Click "Apply" once to update both

## Code Changes

### Editor.py
- Added `UnifiedLibraryEditor` class
- Kept old `LibraryEditor` for reference (could be removed later)
- Updated button layout to single button

### Flowchart.py
- Changed from two editors to one:
  ```python
  # Old
  self.libraryEditor = EditorTemplate.LibraryEditor(...)
  self.subgraphLibraryEditor = EditorTemplate.SubgraphLibraryEditor(...)
  
  # New
  self.libraryEditor = EditorTemplate.UnifiedLibraryEditor(
      self, chart.library, chart.subgraph_library
  )
  ```
- Updated `saveState()` to use unified format
- Updated `restoreState()` with backward compatibility

## Testing Checklist

- [ ] Load `.py` files → appear in Nodes tree
- [ ] Load `.fc` files → appear in Subgraphs tree
- [ ] Load mixed files → correctly sorted
- [ ] Load directory → both types scanned
- [ ] Apply → both libraries updated
- [ ] Save/reload flowchart → libraries restored
- [ ] Old flowchart files → still load correctly

## Future Enhancements

### Possible Improvements
1. **Unified tree** - single tree with type icons
2. **Search across both** - filter both node and subgraph names
3. **Batch operations** - select multiple items to remove
4. **Reload support** - reload changed files
5. **Favorites** - mark commonly used items

### Not Implemented (Intentionally Simple)
- Tree merging (kept separate for clarity)
- Advanced filtering
- File watching
- Duplicate detection across types
