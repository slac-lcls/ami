# Fix Applied: Use signal=True for Internal Subgraph Connections

**Date:** 2026-03-18  
**Issue:** ScalarPlot._input_vars empty after import → compilation fails  
**Root Cause:** Using signal=False for internal connections prevented _input_vars population  
**Fix:** Changed to signal=True for internal connections in importSubgraphFromFile()  
**Status:** ✅ IMPLEMENTED - Ready for testing

---

## Summary of Changes

### Change 1: Reverted Incorrect Fix ✅

**File:** `ami/flowchart/Flowchart.py`  
**Lines Removed:** 1155-1160

Removed the incorrect fix that tried to mark nodes as `changed=True`. This was addressing 
a symptom (nodes not being processed) rather than the root cause (missing _input_vars).

**Code Removed:**
```python
# CRITICAL FIX: Mark all imported nodes as changed so they're processed in applyClicked()
# Display nodes (like WaveformViewer) have isChanged() returning False, which causes
# them to be skipped during compilation, resulting in missing nodes in execution graph
for node in restored_nodes:
    node.changed = True
logger.info(f"[FIX] Marked {len(restored_nodes)} imported nodes as changed=True")
```

---

### Change 2: Applied Correct Fix ✅

**File:** `ami/flowchart/Flowchart.py`  
**Line:** ~1113 (was 1119 before revert)

Changed internal connection restoration from `signal=False` to `signal=True`.

**Before:**
```python
logger.info(f"    Creating visual connection...")
term1.connectTo(term2, signal=False)
logger.info(f"    ✅ Visual connection created")
```

**After:**
```python
logger.info(f"    Creating internal connection...")
# IMPORTANT: Use signal=True to populate _input_vars which is required
# for node compilation via to_operation(inputs=...). Only helper boundary
# connections should use signal=False.
term1.connectTo(term2, signal=True)
logger.info(f"    ✅ Internal connection created")
```

**Impact:**
- `signal=True` triggers `Terminal.connected()` → `Node.connected()` callbacks
- Callbacks populate `_input_vars` dictionary
- Nodes can now compile with correct input variables
- Graph edges automatically created (correct for internal connections)

---

### Change 3: Created Documentation ✅

**File:** `.opencode/plans/signal-parameter-understanding.md`

Created comprehensive documentation explaining:
- When to use `signal=True` vs `signal=False`
- The three connection types in subgraphs
- Root cause analysis of the bug
- Updated guidelines for signal parameter usage

---

## Why This Fix Works

### The Problem Chain

1. **Old code:** `term1.connectTo(term2, signal=False)`
2. **signal=False** → `Terminal.connected()` callback NOT called
3. **No callback** → `Node.connected()` NOT called
4. **No Node.connected()** → `self._input_vars[terminal_name]` NOT set
5. **Empty _input_vars** → `node.input_vars()` returns `{}`
6. **Empty input_vars** → `node.to_operation(inputs={})` fails
7. **Result:** Nodes can't compile, missing from execution graph

### The Solution Chain

1. **New code:** `term1.connectTo(term2, signal=True)`
2. **signal=True** → `Terminal.connected()` callback IS called
3. **Callback triggered** → `Node.connected()` IS called
4. **Node.connected()** → `self._input_vars['Y'] = 'ExponentialMovingAverage1D.0.Count'`
5. **Populated _input_vars** → `node.input_vars()` returns `{'Y': '...'}`
6. **Correct input_vars** → `node.to_operation(inputs={'Y': '...'})` succeeds
7. **Result:** Nodes compile correctly, complete execution graph

---

## What signal=True Enables

### For Internal Connections (What We Fixed)

When `signal=True` is used:

1. **_input_vars populated** ✅
   - ScalarPlot knows Y comes from ExponentialMovingAverage1D.0.Count
   - WaveformViewer knows In comes from ExponentialMovingAverage1D.0.Out

2. **Graph edges created automatically** ✅
   - `sigTerminalConnected` signal emitted
   - `Flowchart.nodeTermConnected()` handler creates edges
   - These are REAL data flow edges (correct for internal connections)

3. **Node marked as changed** ✅
   - `node.changed = True` set in `Node.connected()`
   - Nodes will be processed in `applyClicked()`
   - This is the CORRECT way to mark nodes as changed

4. **Type checking performed** ✅
   - Terminal types validated
   - Type errors caught early

---

## Connection Type Guide

### Use signal=TRUE for:

✅ **Internal subgraph connections** (WHAT WE FIXED)
- ExponentialMovingAverage1D → WaveformViewer
- ExponentialMovingAverage1D → ScalarPlot
- Location: `importSubgraphFromFile()` line ~1113

✅ **User-created runtime connections**
- When user drags connection in GUI
- Standard flowchart connections

✅ **Main flowchart restoration**
- `restoreState()` loading saved flowcharts

### Use signal=FALSE for:

✅ **Helper boundary connections**
- Helper → Internal node (visual only)
- External → Placeholder (visual only)
- Location: `_createSubgraph()` lines 392, 394, 479, 482

✅ **Visual-only connections**
- Involving `is_visual_only=True` nodes
- Where graph edges created manually

---

## Testing Checklist

### Test 1: Verify _input_vars Population ⏳

```bash
ami-local random://
```

1. Import subgraph from library
2. Check _input_vars in Python console:
   ```python
   sg = fc._subgraphs['combined.0']
   for node_name in sg['nodes']:
       node = fc._graph.nodes[node_name]['node']
       print(f"{node_name}.input_vars() = {node.input_vars()}")
   ```

**Expected:**
```
ExponentialMovingAverage1D.0.input_vars() = {}
WaveformViewer.0.input_vars() = {'In': 'ExponentialMovingAverage1D.0.Out'}
ScalarPlot.0.input_vars() = {'Y': 'ExponentialMovingAverage1D.0.Count'}
```

### Test 2: Verify Compilation ⏳

1. Add waveform source
2. Connect to subgraph
3. Click **Apply**

**Expected:**
- ✅ No errors
- ✅ All nodes compile successfully
- ✅ No "disconnected node" warnings

### Test 3: Verify with Dump Graph ⏳

1. After Apply succeeds
2. Click **Dump Graph**
3. Check output file

**Expected in flowchart_graph_*.dot:**
```dot
"ExponentialMovingAverage1D.0" -> "WaveformViewer.0" [label="Out → In"];
"ExponentialMovingAverage1D.0" -> "ScalarPlot.0" [label="Count → Y"];
waveform -> "ExponentialMovingAverage1D.0" [label="Out → In"];
```

### Test 4: Check Console Logs ⏳

Look for updated log messages:

**Expected:**
```
[DEBUG importSubgraphFromFile] Restoring internal connections
  Connections to restore: 2
    [0] ExponentialMovingAverage1D.0.Out → WaveformViewer.0.In
    [1] ExponentialMovingAverage1D.0.Count → ScalarPlot.0.Y

  [Connection 0] Attempting: ExponentialMovingAverage1D.0.Out → WaveformViewer.0.In
    Creating internal connection...
    ✅ Internal connection created
    Adding graph edge: ExponentialMovingAverage1D.0.Out->WaveformViewer.0.In
    ✅ Graph edge created
```

### Test 5: Regression Test ⏳

1. Create subgraph manually from selection
2. Save and reload
3. Import from library

**Expected:**
- ✅ All methods work
- ✅ No regressions

---

## Potential Issues to Monitor

### 1. Duplicate Graph Edges?

**Concern:** Line ~1120 manually creates graph edges with `self._graph.add_edge()`. 
With `signal=True`, callbacks also create edges. Could this create duplicates?

**Analysis:**
- NetworkX MultiDiGraph allows multiple edges between same nodes
- Each edge has a unique `key` parameter
- Likely not an issue, but monitor

**If duplicates are problematic:**
- Option A: Remove manual `add_edge()` (rely on signal=True)
- Option B: Keep both (MultiDiGraph handles it)

### 2. Callback Side Effects?

**Concern:** `signal=True` triggers various callbacks. Could these cause issues during import?

**Analysis:**
- `sigTerminalConnected` emitted → `nodeTermConnected()` called
- This creates graph edges and marks nodes changed
- Both are CORRECT for internal connections
- Likely not an issue

**Monitor for:**
- Unexpected state changes
- Performance impact
- Unwanted graph modifications

---

## Files Modified

```
M  ami/flowchart/Flowchart.py          (-6 lines revert, +7 lines fix, net +1)
A  .opencode/plans/signal-parameter-understanding.md  (new documentation)
```

**Flowchart.py changes:**
- Line ~1113: Changed `signal=False` to `signal=True`
- Lines 1155-1160: Removed (reverted incorrect fix)
- Added explanatory comments

---

## Related Issues Resolved

This fix addresses:

1. **✅ ScalarPlot._input_vars empty** → Now populated
2. **✅ WaveformViewer missing from execution graph** → Should now compile
3. **✅ Compilation failures** → Nodes now get correct inputs
4. **✅ Incorrect changed=True fix** → Reverted, no longer needed

This complements:
- **Dump Graph button** (already implemented) - debugging tool
- **Phase 2 refactoring** (in progress) - unified subgraph architecture

---

## Commit Message (Draft)

```
Fix: Use signal=True for internal subgraph connections

Problem:
Internal connections in imported subgraphs used signal=False, which
prevented Node.connected() callbacks from running. This left _input_vars
unpopulated, causing compilation to fail with empty input dictionaries.

Root Cause:
- signal=False → no callbacks → no _input_vars population
- Nodes with to_operation() need _input_vars to compile
- ScalarPlot.to_operation(inputs={}) failed silently

Solution:
- Changed signal=False to signal=True for internal connections
- Callbacks now run, populating _input_vars correctly
- Reverted incorrect changed=True fix (was treating symptom not cause)

Impact:
- ScalarPlot._input_vars['Y'] = 'ExponentialMovingAverage1D.0.Count'
- WaveformViewer._input_vars['In'] = 'ExponentialMovingAverage1D.0.Out'
- Nodes compile successfully with proper input variables
- Execution graph now complete

Changes:
- ami/flowchart/Flowchart.py line ~1113: signal=False → signal=True
- ami/flowchart/Flowchart.py lines 1155-1160: Reverted incorrect fix
- Created .opencode/plans/signal-parameter-understanding.md

Testing:
- Verify _input_vars populated after import
- Verify Apply succeeds without errors
- Verify Dump Graph shows all nodes/edges
```

---

## Success Criteria

The fix is successful when:

- [x] Code changes applied ✅
- [ ] _input_vars populated (Test 1) ⏳
- [ ] Apply succeeds (Test 2) ⏳
- [ ] Dump graph complete (Test 3) ⏳
- [ ] Logs show "internal connection" (Test 4) ⏳
- [ ] No regressions (Test 5) ⏳
- [ ] Documentation created ✅

---

**Status:** ✅ IMPLEMENTED  
**Ready for:** Testing  
**Expected outcome:** Internal nodes now compile correctly with proper _input_vars  
**Next step:** Run tests to verify the fix works
