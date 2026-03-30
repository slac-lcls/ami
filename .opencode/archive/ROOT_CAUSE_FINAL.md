# ROOT CAUSE IDENTIFIED ✅

**Date:** 2026-03-18
**Issue:** Internal nodes (WaveformViewer) missing from compiled execution graph after subgraph import
**Status:** ROOT CAUSE CONFIRMED

---

## The Problem

When importing a subgraph from library:
- ✅ Internal edges exist in `self._graph` (flowchart graph)
- ✅ Internal connections are restored correctly  
- ❌ WaveformViewer.0 node is MISSING from compiled execution graph
- ❌ The edge ExponentialMovingAverage1D.0 → WaveformViewer.0 is lost

---

## Root Cause Analysis

### Step 1: Dump Graph Button Reveals Truth

Using the new "Dump Graph" button, we confirmed:

**Flowchart Graph (`flowchart_graph_20260318_112032.dot`):**
```
✅ ExponentialMovingAverage1D.0 → WaveformViewer.0 [label="Out → In"]
✅ ExponentialMovingAverage1D.0 → ScalarPlot.0 [label="Count → Y"]  
✅ waveform → ExponentialMovingAverage1D.0 [label="Out → In"]
```

**Compiled Execution Graph (`broken_graph.dot`):**
```
✅ ExponentialMovingAverage1D.0 (10+ operation nodes)
✅ ScalarPlot.0 (10+ operation nodes)
❌ WaveformViewer.0 - COMPLETELY MISSING!
✅ waveform
```

**Conclusion:** Internal edges exist in flowchart graph but nodes are lost during compilation.

---

### Step 2: Code Analysis

**File:** `ami/flowchart/Flowchart.py`  
**Method:** `FlowchartCtrlWidget.applyClicked()` (line 2300-2414)

**The Compilation Loop:**
```python
for name, gnode in self.chart._graph.nodes(data='node'):
    if gnode is None or not gnode.enabled():
        continue
    
    if not gnode.hasInput():  # Check 1: Has all inputs connected?
        disconnectedNodes.append(gnode)
        continue
    
    if gnode.changed and gnode not in changed_nodes:  # Check 2: Is changed?
        changed_nodes.add(gnode)
        
        if not hasattr(gnode, 'to_operation'):  # Display-only node?
            if gnode.viewable() and gnode.viewed:
                displays.add(gnode)  # Add to display list
            continue  # Skip compilation
        
        # Compile nodes with to_operation()...
```

**For WaveformViewer.0:**
- ✅ Pass Check 1: `hasInput()` returns True (In terminal is connected)
- ❌ **FAIL Check 2**: `gnode.changed` is FALSE!
- Result: Node is never added to `displays`, never compiled, completely skipped!

---

### Step 3: Why is `changed=False`?

**File:** `ami/flowchart/Flowchart.py:2133`

When nodes are restored from file:
```python
node.changed = node.isChanged(restore_ctrl, restore_widget)
```

**File:** `ami/flowchart/library/Display.py:135-136`

WaveformViewer class:
```python
def isChanged(self, restore_ctrl, restore_widget):
    return False  # ← ALWAYS RETURNS FALSE!
```

**Why?**
- WaveformViewer is a display-only node
- It has no control widgets that change state
- `isChanged()` is meant to return True only if controls/widgets changed
- For WaveformViewer: no controls → always return False

**Result:**
- When imported from file, `node.changed = False`
- In `applyClicked()`, `if gnode.changed:` is False → SKIP!
- Node never processed, never added to displays, missing from execution graph

---

## Why ScalarPlot Works

**ScalarPlot has `to_operation()`:**
```python
def to_operation(self, inputs, outputs, **kwargs):
    # ... compiles to operation nodes ...
```

So ScalarPlot:
1. Passes `if gnode.changed:` check (or doesn't need to - has to_operation)
2. Gets compiled via `to_operation()`  
3. Appears in execution graph as ~10 operation nodes

**WaveformViewer has NO `to_operation()`:**
- It's display-only (viewable=True)
- Should be added to `displays` set
- But only if `gnode.changed=True`!
- Since `isChanged()` returns False, it's never added

---

## The Design Flaw

The `applyClicked()` logic assumes:
- **Nodes with `to_operation()`** → Always compile if changed
- **Display nodes without `to_operation()`** → Add to `displays` if changed AND viewed

**But for imported subgraphs:**
- Internal display nodes are restored from file
- `isChanged()` returns False (no user modifications)
- `changed=False` → never processed → missing from execution graph!

**This works fine for user-created subgraphs** because:
- User selects nodes → creates subgraph
- Nodes already exist in graph, already have `changed=True`
- When Apply is clicked, they're processed normally

**But breaks for imported subgraphs** because:
- Nodes are created fresh from file
- `isChanged()` returns False
- `changed=False` → SKIP!

---

## The Fix

### Option 1: Mark imported nodes as changed

**In `importSubgraphFromFile()` or `_createSubgraphFromImport()`:**
```python
for node in restored_nodes:
    node.changed = True  # Force imported nodes to be processed
```

### Option 2: Change applyClicked() logic

**Don't require `changed=True` for display nodes:**
```python
# Instead of:
if gnode.changed and gnode not in changed_nodes:
    ...
    
# Use:
if not hasattr(gnode, 'to_operation'):
    # Always process display nodes, regardless of changed flag
    if gnode.viewable() and gnode.viewed:
        displays.add(gnode)
    continue

if gnode.changed and gnode not in changed_nodes:
    # Only require changed=True for nodes with to_operation()
    ...
```

### Option 3: Fix isChanged() for WaveformViewer

**Make it return True if it has connected inputs:**
```python
def isChanged(self, restore_ctrl, restore_widget):
    # If restored from file with connections, mark as changed
    if restore_ctrl or restore_widget:
        return self.hasInput()
    return False
```

---

## Recommended Fix: Option 1

**Simplest and safest:**
- Add one line in `_createSubgraphFromImport()` after nodes are restored
- Marks all imported nodes as `changed=True`
- Forces them to be processed in next `applyClicked()`
- Minimal code change, low risk

**Implementation location:** After line ~750 in `importSubgraphFromFile()` where nodes are restored.

---

## Testing the Fix

After applying fix:
1. Import subgraph from library
2. Click Apply
3. Dump execution graph
4. Check if WaveformViewer.0 appears
5. Check if internal edge exists

**Expected:**
- ✅ WaveformViewer.0 in execution graph (or in displays)
- ✅ All internal connections preserved
- ✅ Subgraph works correctly

---

## Files Involved

1. **`ami/flowchart/Flowchart.py`**
   - Line 1010: `importSubgraphFromFile()` - where to add fix
   - Line 2300: `applyClicked()` - where filtering happens
   - Line 2133: where `changed` flag is set from `isChanged()`

2. **`ami/flowchart/library/Display.py`**
   - Line 135: `WaveformViewer.isChanged()` - returns False

---

**Status:** Ready to implement fix ✅  
**Estimated time:** 5 minutes  
**Risk:** Low (one-line change)

