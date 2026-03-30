# AMI Subgraph System - Current Status

**Last Updated**: March 18, 2026  
**Branch**: `subgraph-refactor-clean`  
**Latest Commit**: `5ef6f9b` - "Fix subgraph import and improve UX"

## Architecture Overview

### Visual-Only Subgraph Design

The current implementation uses a **visual-only architecture** where:

- **Placeholder nodes** (SubgraphNode) are NOT in `self._graph`
- **Helper nodes** (SubgraphInputs/SubgraphOutputs) are NOT in `self._graph`
- **Internal nodes** ARE in `self._graph` and participate in compilation
- **Graph edges** skip helpers and connect external → internal directly

This is cleaner than the previous "helpers in graph" approach (commit c8a57f9).

### Key Components

```
Root View (execution graph):
  External → Placeholder → External
              (visual only)

Subgraph View (visual only):
  SubgraphInput → Internal Nodes → SubgraphOutput
    (helpers)        (in graph)        (helpers)

Execution Graph:
  External → Internal Nodes → External
          (direct edges)
```

## Recent Changes (Commit 5ef6f9b)

### Critical Bug Fixes
1. **Fixed internal connections** - Changed `signal=False` → `signal=True` in `importSubgraphFromFile()`
   - **File**: `ami/flowchart/Flowchart.py` line 1051
   - **Impact**: Internal nodes now populate `_input_vars` correctly and compile
   - **Root Cause**: `signal=False` prevented `connected()` callback, leaving `_input_vars` empty

2. **Fixed view switching** - Explicit view management during import
   - **Files**: `Flowchart.py` lines 611-631, 1001-1003, 1088-1090
   - **Impact**: User stays on root view after drag-drop, sees placeholder
   - **Implementation**: Switch to subgraph view → create nodes → switch to root

### UX Improvements

3. **Hierarchical subgraph library tree**
   - **Files**: `Flowchart.py` lines 1227-1275, `Editor.py` lines 159-197, 232-251
   - **Structure**:
     ```
     Subgraph Library
     ├── file1
     │   ├── subgraph_a
     │   └── subgraph_b
     └── Root
         └── subgraph_created_in_flowchart
     ```
   - **Impact**: Better organization, clear source file tracking

4. **Grid snapping for placeholders**
   - **File**: `Flowchart.py` lines 618-632
   - **Implementation**: Uses `find_nearest()` for 100-unit grid
   - **Impact**: Cleaner flowchart layouts

5. **Improved view cleanup**
   - **File**: `FlowchartGraphicsView.py` lines 269-285
   - **Changes**: 
     - Remove widget from layout
     - Delete with `deleteLater()`
     - Remove from action group
   - **Impact**: Better memory management (partial fix)

6. **Better default names**
   - Subgraphs from selection: `combined.X` → `subgraph.X`
   - Created in flowchart: `[Created in flowchart]` → `Root`

### Code Cleanup

7. **Removed debug logging**
   - 22 logger statements (emojis, verbose output)
   - 2 print statements
   - All [DEBUG] tags

8. **Removed Dump Graph feature**
   - Removed debugging button and method
   - Was temporary debugging tool

## Known Issues

### 1. Placeholder Cleanup Bug (High Priority)

**Symptom**: When clicking X button on placeholder, the placeholder graphics item and toolbar button remain visible.

**Workaround**: Use right-click "Remove" instead (works correctly).

**Analysis**:
- `SubgraphNode.close()` is called correctly
- Child nodes ARE deleted ✅
- Subgraph view IS removed from dict ✅
- View widget cleanup IS improved ✅
- BUT placeholder graphics item NOT removed from root view ❌
- AND toolbar button NOT removed ❌

**Likely Cause**:
- `Node.close(self, emit=False)` at line 116 of SubgraphNode.py
- The graphics item removal in `Node.close()` might not be working
- Or the order of operations causes issues

**Investigation Needed**:
- Why does right-click "Remove" work but X button doesn't?
- Both call the same `close()` method
- Check if `item.scene().removeItem(item)` is actually removing the placeholder
- May need explicit removal: `root_view.viewBox().scene().removeItem(placeholder_item)`

**Next Steps**:
1. Add explicit placeholder removal from root view before calling `Node.close()`
2. Test if emit=True vs emit=False matters
3. Verify toolbar button cleanup in `removeView()`

## File Organization

### Modified Files (Commit 5ef6f9b)
```
ami/flowchart/Flowchart.py             (+119, -73 lines)
ami/flowchart/Editor.py                (+38, -6 lines)
ami/flowchart/FlowchartGraphicsView.py (+18, -6 lines)
```

### Key Methods

**Flowchart.py**:
- `importSubgraphFromFile()` - Import from .fc file or template (lines 968-1095)
- `instantiateSubgraphFromLibrary()` - Create instance from library (lines 1088-1117)
- `_createSubgraphFromImport()` - Build subgraph structure (lines 581-835)
- `_updateSubgraphLibraryUI()` - Update hierarchical tree (lines 1227-1275)
- `_addSubgraphToLibrary()` - Add to library and update UI (lines 1119-1226)

**Editor.py**:
- `UnifiedLibraryEditor` - Manages both .py and .fc files
- `loadFlowchartFiles()` - Load .fc files as templates (lines 159-197)
- `applyClicked()` - Update UI trees hierarchically (lines 232-251)

**FlowchartGraphicsView.py**:
- `ViewManager.removeView()` - Proper view cleanup (lines 269-285)

**SubgraphNode.py**:
- `SubgraphNode.close()` - Cleanup placeholder and children (lines 68-116)
- ⚠️ Known issue with placeholder graphics removal

## Testing Checklist

### ✅ Working Features
- [x] Import subgraph from .fc file
- [x] Drag-and-drop from library
- [x] Internal nodes compile correctly
- [x] View switching (stay on root after import)
- [x] Grid snapping
- [x] Hierarchical library tree
- [x] Boundary connections work
- [x] Double-click placeholder to enter subgraph view

### ⚠️ Known Issues
- [ ] Placeholder cleanup via X button (use right-click Remove)

### 🔄 Needs Testing
- [ ] Multiple subgraphs in one flowchart
- [ ] Nested subgraphs
- [ ] Save/load with subgraphs
- [ ] Export subgraph to library
- [ ] Update subgraph template

## Branch History

### Divergence from `subgraph` branch

```
6ad9f81 (common ancestor)
  |
  +-- c8a57f9 [subgraph branch]
  |     "Add helper nodes to graph with identity operations"
  |     - Helpers in self._graph
  |     - Identity operations for pass-through
  |     - Step 1.5 in close() to remove helpers
  |
  +-- c16ec5d [subgraph-refactor-clean]
        "Implement visual-only subgraph architecture"
        - Helpers NOT in self._graph
        - Cleaner execution graph
        - Better library support
        |
        +-- 5ef6f9b [HEAD]
              "Fix subgraph import and improve UX"
              - Today's fixes and improvements
```

### Stash Status
- `stash@{0}`: Bug fix for `instantiateSubgraphFromLibrary` - **Now in 5ef6f9b, can discard**
- `stash@{1}`: WIP refactor changes - **Now in c16ec5d, can discard**

## Next Steps

### Immediate (Bug Fixes)
1. **Fix placeholder cleanup** - Make X button work like right-click Remove
   - Debug why `Node.close()` doesn't remove graphics item
   - May need explicit removal before calling parent close()
   - Test toolbar button cleanup

2. **Verify all cleanup paths**
   - Test "New" flowchart command
   - Test closing flowchart with subgraphs
   - Check for memory leaks

### Short Term (Features)
3. **Nested subgraphs** - Allow subgraphs inside subgraphs
4. **Update template** - Allow updating library template from modified instance
5. **Export improvements** - Better metadata capture

### Long Term (Architecture)
6. **Runtime connection handling** (Phase 3)
   - When external connects to placeholder
   - Create direct edge external → internal
   - Update helper visual connections

7. **Save/Load improvements**
   - Verify subgraph metadata persists
   - Test library restoration
   - Handle version compatibility

## Code Quality

### Clean Code Principles Applied
- ✅ Removed all debug logging
- ✅ Clear separation: visual vs execution
- ✅ Explicit view switching (no hidden state changes)
- ✅ Comments explain "why" not "what"
- ✅ Consistent naming (placeholder, helper, internal)

### Areas for Improvement
- ⚠️ Placeholder cleanup needs fixing
- 📝 Could add more unit tests
- 📝 Documentation for library format (.fc file structure)
- 📝 Error handling for corrupt .fc files

## Development Guidelines

### When Adding Features
1. **Maintain visual-only architecture** - Don't add helpers to `self._graph`
2. **Use explicit view switching** - Don't rely on currentView side effects
3. **Test both paths**: selection → subgraph AND import → subgraph
4. **Preserve metadata** - Ensure save/load works

### When Debugging
1. **Check view vs graph** - Item in viewBox vs node in `self._graph`
2. **Verify signal flow** - `signal=True` for real connections
3. **Trace view switches** - Use `displayView()` explicitly
4. **Test cleanup paths** - X button, Remove, New, Close

### Commit Message Format
```
<Type>: <Short description>

<Detailed explanation>
- Bullet points for changes
- Note any breaking changes
- Reference issues/PRs if applicable

Files changed: <summary>
```

Types: Fix, Feature, Refactor, Cleanup, Docs, Test

## References

### Related Documents
- `.opencode/plans/signal-parameter-understanding.md` - When to use `signal=True` vs `signal=False`
- `.opencode/plans/subgraph-refactor-progress.md` - Previous refactor progress
- `AGENTS.md` - Architecture guide for AI agents

### Key Commits for Reference
- `c16ec5d` - Visual-only architecture refactor
- `5ef6f9b` - Import fixes and UX improvements
- `c8a57f9` - Previous approach (helpers in graph) - on `subgraph` branch

---

**Active Development Branch**: `subgraph-refactor-clean`  
**Status**: Functional with one known issue (placeholder cleanup)  
**Ready for**: Continued development, testing, eventual merge to master
