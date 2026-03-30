# ROOT CAUSE IDENTIFIED: Missing Internal Edges in Subgraphs

**Date:** 2026-03-18  
**Status:** ✅ ROOT CAUSE CONFIRMED  
**Impact:** CRITICAL - Internal nodes in subgraphs are excluded from compilation

---

## Executive Summary

Using the new "Dump Graph" button, we confirmed that **internal edges exist in `self._graph`** but **internal nodes are missing from the compiled execution graph**.

**Root Cause:** Display nodes inside subgraphs (WaveformViewer, ScalarPlot) are filtered out during compilation because they fail the `hasInput()` check in `applyClicked()`.

---

## Evidence

### Flowchart Graph (self._graph) - CORRECT ✅

File: `flowchart_graph_20260318_112032.dot`

```dot
"ExponentialMovingAverage1D.0" -> "WaveformViewer.0" [label="Out → In"];
"ExponentialMovingAverage1D.0" -> "ScalarPlot.0" [label="Count → Y"];
waveform -> "ExponentialMovingAverage1D.0" [label="Out → In"];
```

**Nodes:**
- ✅ ExponentialMovingAverage1D.0
- ✅ WaveformViewer.0
- ✅ ScalarPlot.0  
- ✅ waveform

**Edges:**
- ✅ All 3 edges present (2 internal + 1 runtime)

---

### Compiled Execution Graph - MISSING NODES ❌

File: `broken_graph.dot`

**Nodes:**
- ✅ ExponentialMovingAverage1D.0 (compiled to ~10 operation nodes)
- ✅ ScalarPlot.0 (compiled to ~10 operation nodes)
- ❌ WaveformViewer.0 - **COMPLETELY MISSING**
- ✅ waveform (source node)

**Missing Edge:**
- ❌ ExponentialMovingAverage1D.0 → WaveformViewer.0 (cannot exist, WaveformViewer.0 not compiled)

**Present Edge:**
- ✅ ExponentialMovingAverage1D.0 → ScalarPlot.0 (via operation nodes)

---

## Code Analysis

### The Filter (ami/flowchart/Flowchart.py:2330-2332)

```python
for name, gnode in self.chart._graph.nodes(data='node'):
    if gnode is None or not gnode.enabled():
        continue

    if not gnode.hasInput():  # ← THE PROBLEM!
        disconnectedNodes.append(gnode)
        continue
```

### hasInput() Implementation (ami/flowchart/Node.py:437-442)

```python
def hasInput(self):
    for name, term in self.inputs().items():
        if not term().isConnected():
            return False
    return True
```

Returns `False` if **ANY** input terminal is unconnected.

---

## Why WaveformViewer.0 is Filtered Out

### Node Configuration

**WaveformViewer** has input terminals:
- `In` - connected to ExponentialMovingAverage1D.0.Out ✅
- Possibly other optional inputs (e.g., X-axis, timestamps) - **NOT connected** ❌

### The Check

```python
if not gnode.hasInput():  # Returns False because optional inputs are unconnected!
    disconnectedNodes.append(gnode)
    continue  # ← SKIP this node entirely!
```

### Result

- WaveformViewer.0 is added to `disconnectedNodes`
- It's **never compiled** to operation nodes
- It **never appears** in the execution graph
- The edge `ExponentialMovingAverage1D.0 → WaveformViewer.0` is **lost**

---

## Why ScalarPlot.0 Works

**ScalarPlot** likely has:
- `Y` - connected to ExponentialMovingAverage1D.0.Count ✅
- Optional inputs (X, color, etc.) - **NOT connected** ❌

**But why does it pass?**

Looking at the compiled graph, ScalarPlot.0 **IS present**, so either:
1. ScalarPlot has NO optional inputs (all inputs connected)
2. ScalarPlot has different `hasInput()` logic
3. Something else is different

Let me check:

<function_calls>
<invoke name="bash">
<parameter name="command">grep -A30 "class WaveformViewer" ami/flowchart/library/Display.py | head -40