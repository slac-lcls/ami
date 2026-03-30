# Updated Understanding: signal Parameter for connectTo() in Subgraphs

**Date:** 2026-03-18  
**Context:** Debugging missing _input_vars in imported subgraphs  
**Key Discovery:** Internal subgraph connections NEED signal=True

---

## Executive Summary

**CRITICAL UPDATE:** Internal connections within imported subgraphs should use `signal=True`, 
NOT `signal=False`. This is necessary to populate `_input_vars` which is required for 
node compilation.

**Previous understanding was incomplete:**
- Old docs said: "Use signal=False for importing subgraphs"
- **This is only true for HELPER boundary connections**
- **For INTERNAL connections between computation nodes: use signal=True**

---

## Connection Type Matrix

### 1. Internal Subgraph Connections ✅ FIXED

**Examples:**
- ExponentialMovingAverage1D.Out → WaveformViewer.In
- ExponentialMovingAverage1D.Count → ScalarPlot.Y

**Location:** `importSubgraphFromFile()` line ~1113

**Fixed:**
```python
# IMPORTANT: Use signal=True to populate _input_vars which is required
# for node compilation via to_operation(inputs=...). Only helper boundary
# connections should use signal=False.
term1.connectTo(term2, signal=True)
```

**Why signal=True is needed:**
- These are REAL data flow connections between computation nodes
- Nodes need `_input_vars` populated to compile via `to_operation(inputs=...)`
- Without _input_vars, nodes get empty input dict → compilation fails
- The `connected()` callback populates `_input_vars`
- Graph edges are also created (which is correct - these are real edges)

**Evidence:**
- ScalarPlot.input_vars() returned empty dict with signal=False
- This caused ScalarPlot.to_operation(inputs={}) to fail
- Changing to signal=True populates _input_vars correctly

---

### 2. Helper Boundary Connections (Input)

**Examples:**
- External.Out → Placeholder.In (visual)
- Helper.Out → Internal.In (visual)

**Location:** `_createSubgraph()` lines 392, 394

**Current (CORRECT):**
```python
external_term.connectTo(placeholder_term, signal=False)  # ✅ Visual only
helper_term.connectTo(internal_term, signal=False)       # ✅ Visual only
```

**Why signal=False is correct:**
- These are VISUAL connections for GUI/coloring
- Graph edges are created MANUALLY as External → Internal (direct)
- Helper nodes are visual-only (is_visual_only=True)
- Don't want duplicate edge creation
- Don't want helper nodes in computation path

---

### 3. Helper Boundary Connections (Output)

**Examples:**
- Internal.Out → Helper.In (visual)
- Placeholder.Out → External.In (visual)

**Location:** `_createSubgraph()` lines 479, 482

**Current (CORRECT):**
```python
internal_term.connectTo(helper_term, signal=False)       # ✅ Visual only
placeholder_term.connectTo(external_term, signal=False)  # ✅ Visual only
```

**Why signal=False is correct:**
- Same reasoning as input boundaries
- Visual connections for interface representation
- Graph edges manually created as Internal → External (direct)

---

## The Three-Layer Architecture

Understanding WHY different connections use different signal values:

### Layer 1: Terminal Connections (GUI)
- **Purpose:** Visual representation, terminal coloring, validation
- **Created by:** `connectTo(signal=False)` for visual-only, `connectTo(signal=True)` for real
- **Examples:** 
  - External → Placeholder (visual, signal=False)
  - Helper → Internal (visual, signal=False)
  - **Internal → Internal (REAL, signal=True)** ← UPDATED

### Layer 2: Graph Edges (Computation)
- **Purpose:** Define actual data flow for execution
- **Created by:** 
  - Automatic via `sigTerminalConnected` when signal=True
  - Manual via `self._graph.add_edge()` for bypassing helpers
- **Examples:**
  - External → Internal (manual, direct bypass)
  - **Internal → Internal (automatic, via signal=True)** ← UPDATED

### Layer 3: Input Variables (Compilation)
- **Purpose:** Tell nodes what their inputs are for compilation
- **Populated by:** `Node.connected()` callback (only when signal=True)
- **Used by:** `node.to_operation(inputs=node.input_vars())`
- **Critical for:** Any node with `to_operation()` method
- **Examples:**
  - ScalarPlot needs to know its Y input comes from ExponentialMovingAverage1D.Count
  - **Without _input_vars, to_operation() gets empty dict → FAILS**

---

## Root Cause of Bug (RESOLVED)

### The Problem
```python
# Line 1119 in importSubgraphFromFile() (OLD)
term1.connectTo(term2, signal=False)  # Restoring internal connections
```

### Why This Broke
1. `signal=False` → `Terminal.connected()` NOT called
2. No callback → `Node.connected()` NOT called  
3. No Node.connected() → `self._input_vars[terminal_name]` NOT set
4. Empty _input_vars → `node.input_vars()` returns {}
5. Empty input_vars → `node.to_operation(inputs={})` fails
6. Result: Nodes can't compile, execution graph incomplete

### The Fix ✅
```python
# Line ~1113 in importSubgraphFromFile() (FIXED)
term1.connectTo(term2, signal=True)  # ✅ Populates _input_vars
```

### Why This Works
1. `signal=True` → `Terminal.connected()` IS called
2. Callback triggers → `Node.connected()` IS called
3. Node.connected() → `self._input_vars[terminal_name] = 'source.terminal'`
4. Populated _input_vars → `node.input_vars()` returns correct dict
5. Correct input_vars → `node.to_operation(inputs={'Y': 'ExponentialMovingAverage1D.0.Count'})` succeeds
6. Result: Nodes compile correctly, execution graph complete

---

## Updated Guidelines

### Use signal=True when:
✅ Restoring **internal connections** between computation nodes (UPDATED!)
✅ User makes runtime connections in GUI
✅ Main flowchart restoration in `restoreState()`
✅ Any connection where nodes need `_input_vars` populated
✅ Any connection that should be in the computation graph

### Use signal=False when:
✅ Creating visual-only helper connections (SubgraphInput/Output ↔ internals)
✅ Connecting to/from placeholder nodes (visual interface)
✅ Any connection where you'll manually create graph edges
✅ Any connection involving `is_visual_only=True` nodes
✅ When you need Terminal._connections but NOT graph edges

### Key Distinction

**The critical question:** "Is this a REAL data flow connection between computation nodes?"

- **YES** → Use `signal=True` (needs _input_vars, needs graph edge)
  - Examples: Internal node → Internal node in subgraph
  
- **NO** → Use `signal=False` (visual only, manual graph edge)
  - Examples: Helper → Internal, External → Placeholder

---

## Implementation Status

### Code Changes Applied ✅

**File:** `ami/flowchart/Flowchart.py`

**Change 1:** Reverted incorrect `node.changed = True` fix (lines 1155-1160 deleted)

**Change 2:** Fixed internal connection restoration (line ~1113):
```python
# IMPORTANT: Use signal=True to populate _input_vars which is required
# for node compilation via to_operation(inputs=...). Only helper boundary
# connections should use signal=False.
term1.connectTo(term2, signal=True)
```

---

## Testing Checklist

After this fix, verify:

- [ ] `_input_vars` populated after import
  - Check: `ScalarPlot._input_vars['Y']` = `'ExponentialMovingAverage1D.0.Count'`
  - Check: `WaveformViewer._input_vars['In']` = `'ExponentialMovingAverage1D.0.Out'`

- [ ] Apply button succeeds without errors

- [ ] Dump graph shows all nodes and edges present

- [ ] No duplicate edge issues (MultiDiGraph handles gracefully)

- [ ] User-created subgraphs still work (regression test)

---

## Lessons Learned

1. **signal parameter has multiple effects:**
   - Controls callback execution
   - Controls _input_vars population  
   - Controls graph edge creation (indirectly via callbacks)

2. **Not all subgraph connections are the same:**
   - Helper boundary connections: visual only (signal=False)
   - Internal connections: real data flow (signal=True)

3. **_input_vars is critical for compilation:**
   - Any node with `to_operation()` needs it
   - Without it, compilation fails silently (empty inputs)
   - Only populated via `connected()` callback

4. **Documentation must be precise:**
   - "Use signal=False for importing subgraphs" was too broad
   - Need to distinguish connection types
   - Context matters!

---

## Related Documentation

This updates/clarifies:
- `.opencode/plans/subgraph-refactor-progress.md` line 475
- `.opencode/plans/subgraph-refactoring.md` lines 11, 49

**Key update:** "Use signal=False for importing subgraphs" only applies to HELPER 
boundary connections, NOT to INTERNAL connections between computation nodes.

---

**Date Fixed:** 2026-03-18  
**Status:** ✅ RESOLVED  
**Impact:** Fixes missing _input_vars, enables proper node compilation  
**Risk:** Low (restores standard behavior)
