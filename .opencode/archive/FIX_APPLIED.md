# Fix Applied: Mark Imported Nodes as Changed ✅

**Date:** 2026-03-18  
**Issue:** WaveformViewer nodes missing from compiled execution graph after subgraph import  
**Fix:** Mark all imported nodes as `changed=True` to force processing in `applyClicked()`  
**Status:** IMPLEMENTED - Ready for testing

---

## The Fix

**File:** `ami/flowchart/Flowchart.py`  
**Location:** Line 1155-1160 (in `importSubgraphFromFile()` method)  
**Lines added:** 6

### Code Added

```python
# CRITICAL FIX: Mark all imported nodes as changed so they're processed in applyClicked()
# Display nodes (like WaveformViewer) have isChanged() returning False, which causes
# them to be skipped during compilation, resulting in missing nodes in execution graph
for node in restored_nodes:
    node.changed = True
logger.info(f"[FIX] Marked {len(restored_nodes)} imported nodes as changed=True")
```

### Location in Code Flow

```python
def importSubgraphFromFile(self, fileName, pos=None):
    # ... load file, restore nodes, restore connections ...
    
    if not restored_nodes:
        logger.error("No nodes were successfully restored")
        return None
    
    # ← FIX ADDED HERE
    for node in restored_nodes:
        node.changed = True
    
    # ... create subgraph ...
```

---

## Why This Works

### Before Fix ❌

1. Import subgraph from library
2. Nodes restored with `node.changed = node.isChanged(...)`
3. `WaveformViewer.isChanged()` returns `False` → `node.changed = False`
4. User clicks Apply
5. In `applyClicked()`: `if gnode.changed:` → False → **SKIP**
6. WaveformViewer never added to displays
7. WaveformViewer missing from execution graph

### After Fix ✅

1. Import subgraph from library
2. Nodes restored, but then:
3. **FIX: `node.changed = True` for all imported nodes**
4. User clicks Apply
5. In `applyClicked()`: `if gnode.changed:` → True → **PROCESS**
6. WaveformViewer added to displays
7. WaveformViewer present in execution graph (or displays list)

---

## Testing Plan

### Test 1: Basic Import (Critical Test)

**Objective:** Verify WaveformViewer appears in execution graph

```bash
ami-local random://
```

**Steps:**
1. Tools → Manage Libraries → Load `export.fc` → Apply
2. Drag subgraph `combined.0` from library tree onto canvas
3. **Check console for:** `[FIX] Marked 3 imported nodes as changed=True`
4. Add a waveform source node
5. Connect: `waveform.Out` → `combined.0.waveform.Out`
6. Click **Apply** button
7. Click **Dump Graph** button → `flowchart_graph_AFTER_FIX.dot`

**Expected Results:**
- ✅ Console shows: `[FIX] Marked 3 imported nodes as changed=True`
- ✅ Apply succeeds (no errors)
- ✅ WaveformViewer.0 appears (either in execution graph or displays)
- ✅ Both internal edges present

**Verify:**
```bash
cat flowchart_graph_AFTER_FIX.dot
```

Should show:
```dot
"ExponentialMovingAverage1D.0" -> "WaveformViewer.0" [label="Out → In"];
"ExponentialMovingAverage1D.0" -> "ScalarPlot.0" [label="Count → Y"];
waveform -> "ExponentialMovingAverage1D.0" [label="Out → In"];
```

---

### Test 2: Verify No Regression

**Objective:** Ensure user-created subgraphs still work

```bash
ami-local random://
```

**Steps:**
1. Add 3 nodes manually
2. Connect them
3. Select nodes → right-click → "Group Selected Nodes"
4. Enter name/description
5. Click **Apply**

**Expected Results:**
- ✅ Subgraph created normally
- ✅ Apply succeeds
- ✅ All nodes compiled/displayed correctly

---

### Test 3: Display Node Visibility

**Objective:** Verify WaveformViewer displays data

```bash
ami-local random://
```

**Steps:**
1. Import subgraph (Test 1 steps 1-5)
2. Click **Apply**
3. Double-click on `combined.0` placeholder to open subgraph view
4. Look for WaveformViewer.0 node
5. Check if it has a display window

**Expected Results:**
- ✅ WaveformViewer.0 visible in subgraph view
- ✅ Display window shows waveform data (if `viewed=True`)

---

### Test 4: Multiple Imports

**Objective:** Verify fix works for multiple subgraph instances

```bash
ami-local random://
```

**Steps:**
1. Import subgraph from library → `combined.0`
2. Import same subgraph again → `combined.1`
3. Import same subgraph again → `combined.2`
4. Connect all three to different sources
5. Click **Apply**

**Expected Results:**
- ✅ Console shows `[FIX] Marked 3 imported nodes as changed=True` for each import
- ✅ All 3 subgraph instances work correctly
- ✅ All 9 internal nodes (3 per subgraph) processed

---

## What to Look For

### Success Indicators ✅

1. **Console log:** `[FIX] Marked N imported nodes as changed=True`
2. **No errors** when clicking Apply
3. **Dump graph** shows all internal nodes and edges
4. **Display windows** work for WaveformViewer nodes
5. **No "disconnected" errors** for internal nodes

### Failure Indicators ❌

1. **No fix message** in console
2. **Errors** about disconnected nodes
3. **Missing nodes** in dumped graph
4. **Missing display windows**
5. **Same behavior as before** (nodes still missing)

---

## Rollback Plan

If the fix causes issues:

```bash
# Revert the change
git diff HEAD ami/flowchart/Flowchart.py > /tmp/fix.patch
git checkout ami/flowchart/Flowchart.py

# Remove just the fix lines (1155-1160)
```

The fix is **isolated** and **non-invasive** - easy to remove if needed.

---

## Expected Impact

### What Changes ✅

- **Imported subgraphs:** All internal nodes now have `changed=True`
- **applyClicked():** Display nodes now processed (added to displays)
- **Execution graph:** Internal display nodes now compiled/displayed

### What Doesn't Change 🔒

- **User-created subgraphs:** Already had `changed=True`, no change
- **Regular nodes:** Not affected (not imported via this path)
- **Graph structure:** No changes to `self._graph` or connections
- **Save/load:** No changes to serialization

---

## Performance Impact

**Negligible:**
- Simple loop: `for node in restored_nodes: node.changed = True`
- O(N) where N = number of nodes in imported subgraph (typically 3-10)
- Runs once per import, not in hot path

---

## Code Quality

### Style ✅
- Follows existing patterns
- Clear comments explaining the fix
- Informative logging

### Safety ✅
- Only affects imported nodes
- No side effects
- Easy to verify (console log)
- Easy to rollback

### Maintainability ✅
- Well-documented with comments
- Clear intent
- Linked to root cause analysis

---

## Files Modified

```
M  ami/flowchart/Flowchart.py   (+6 lines at line 1155)
M  ami/flowchart/Editor.py      (+6 lines, Dump Graph button)
```

**Total changes this session:**
- Dump Graph button implementation (~95 lines)
- Critical fix for imported nodes (6 lines)
- **Total:** ~101 lines added

---

## Documentation

Related files created:
- `ROOT_CAUSE_FINAL.md` - Complete root cause analysis
- `DUMP_GRAPH_TEST_GUIDE.md` - Dump Graph button usage guide
- `IMPLEMENTATION_COMPLETE.md` - Dump Graph button documentation
- `FIX_APPLIED.md` - This file

---

## Next Steps

1. **Test the fix** (Test 1 above - CRITICAL)
2. **Verify with Dump Graph** button
3. **Check console logs** for fix message
4. **Test regression** (user-created subgraphs)
5. **Report results**

---

## Commit Message (Draft)

```
Fix: Mark imported nodes as changed to include display nodes in compilation

When importing subgraphs from library, internal display nodes (like
WaveformViewer) were being excluded from the compiled execution graph
because their isChanged() method returns False, resulting in
changed=False after import. This caused them to be skipped during
applyClicked() processing.

Root cause:
- WaveformViewer.isChanged() always returns False (no UI controls)
- After import: node.changed = node.isChanged(...) → False
- In applyClicked(): if gnode.changed: → False → SKIP
- Display node never added to displays, missing from execution graph

Fix:
- Mark all imported nodes as changed=True in importSubgraphFromFile()
- Forces applyClicked() to process display nodes
- Adds them to displays list for proper compilation

Testing:
- Use "Dump Graph" button to verify nodes present in flowchart graph
- Import subgraph → Apply → Dump Graph
- Check for WaveformViewer.0 in execution graph or displays

Fixes missing internal edges issue discovered via Dump Graph debugging.

Files modified:
- ami/flowchart/Flowchart.py: Add changed=True loop in importSubgraphFromFile
```

---

**Status:** ✅ FIX IMPLEMENTED  
**Ready for:** Testing  
**Expected result:** All internal nodes now compiled/displayed correctly
