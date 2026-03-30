# Plan: Add "Dump Graph" Button to AMI Toolbar

**Status**: Ready for Implementation  
**Created**: 2026-03-18  
**Context**: Debugging missing internal edges in imported subgraphs

---

## Executive Summary

Add a "Dump Graph" button to the AMI flowchart editor toolbar that dumps `self._graph` (the client-side flowchart graph, pre-compilation) to a timestamped `.dot` file. This is critical for debugging why internal connections are missing in the compiled execution graph when importing subgraphs from the library.

**Key Finding**: Internal edges exist in `self._graph` after import (confirmed by debug logs), but are missing in the compiled execution graph (`broken_graph.dot`). Need to dump flowchart graph to determine if edges are lost during `_createSubgraph()` or during compilation.

---

## Background

### The Problem
When importing a subgraph from library:
- ✅ Connection restoration works (confirmed in `test_connections_debug.log` lines 55-58)
- ✅ Two internal edges exist: `ExponentialMovingAverage1D.0 → WaveformViewer.0` and `ExponentialMovingAverage1D.0 → ScalarPlot.0`
- ❌ After compilation, edges are missing in execution graph (`broken_graph.dot`)
- ❓ **Unknown**: Are edges still in `self._graph` after `_createSubgraph()` completes?

### Why We Need This Button
Currently we can only see the **compiled** execution graph. We need to see the **flowchart** graph to determine:
1. Do internal edges survive `_createSubgraph()` and `importSubgraphFromFile()`?
2. Are edges lost during compilation?
3. Does making runtime connections corrupt internal edges?

---

## Architecture Overview

**Files to modify:**
1. **`ami/flowchart/Editor.py`** - Define the UI button action
2. **`ami/flowchart/Flowchart.py`** - Connect button signal and implement dump functionality

**How it works:**
```
User clicks "Dump Graph" button
  ↓
Triggers actionDumpGraph.triggered signal
  ↓
Calls dumpGraphClicked() handler
  ↓
Calls chart.dumpFlowchartGraph()
  ↓
Writes self._graph to flowchart_graph_YYYYMMDD_HHMMSS.dot
  ↓
Shows success message: "Graph dumped to flowchart_graph_20260318_140532.dot"
```

---

## Implementation Details

### Step 1: Add Action to Editor Toolbar

**File**: `ami/flowchart/Editor.py`  
**Location**: After line 350 (after `actionHome` definition)

```python
# dump graph (for debugging)
self.actionDumpGraph = QtWidgets.QAction(parent)
self.actionDumpGraph.setIconText("Dump Graph")
self.actionDumpGraph.setObjectName("actionDumpGraph")
```

**Location**: After line 393 (after `actionHome` is added to toolbar)

```python
self.toolBar.addAction(self.actionDumpGraph)
```

**Result**: Button appears in toolbar after "Home", before "Pan"

---

### Step 2: Connect Button Signal

**File**: `ami/flowchart/Flowchart.py`  
**Location**: After line 2202 (after `actionHome.triggered.connect`)

```python
self.ui.actionDumpGraph.triggered.connect(self.dumpGraphClicked)
```

---

### Step 3: Implement Button Handler

**File**: `ami/flowchart/Flowchart.py`  
**Location**: After line 2383 (after `homeClicked()` method)

```python
def dumpGraphClicked(self):
    """Handler for Dump Graph button - dumps flowchart graph to .dot file"""
    try:
        filename = self.chart.dumpFlowchartGraph()
        if self._widget:
            self.widget().chartWidget.updateStatus(f"Graph dumped to {filename}")
        logger.info(f"✅ Flowchart graph dumped to {filename}")
    except Exception as e:
        logger.error(f"❌ Failed to dump graph: {e}")
        if self._widget:
            self.widget().chartWidget.updateStatus(f"Error dumping graph: {e}")
        import traceback
        traceback.print_exc()
```

---

### Step 4: Implement Graph Dump Method

**File**: `ami/flowchart/Flowchart.py`  
**Location**: After line 830 (near other file I/O methods like `saveFile`, `loadFile`)

```python
def dumpFlowchartGraph(self, filename=None):
    """Dump the flowchart graph (pre-compilation) to a .dot file for debugging
    
    Args:
        filename: Optional output filename (default: flowchart_graph.dot)
        
    Returns:
        The filename that was written
    """
    import os
    from datetime import datetime
    
    if filename is None:
        # Generate timestamped filename in current directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"flowchart_graph_{timestamp}.dot"
    
    logger.info(f"\n{'='*80}")
    logger.info(f"[Dump Flowchart Graph] Writing to {filename}")
    logger.info(f"  Nodes in self._graph: {len(self._graph.nodes)}")
    logger.info(f"  Edges in self._graph: {len(list(self._graph.edges()))}")
    
    # Create a simplified directed graph for visualization
    G = nx.DiGraph()
    
    # Add nodes with labels
    for node_name in self._graph.nodes:
        node_data = self._graph.nodes[node_name]
        node_obj = node_data.get('node')
        if node_obj:
            label = f"{node_name}\\n({node_obj.__class__.__name__})"
        else:
            label = node_name
        G.add_node(node_name, label=label, shape="box")
    
    # Add edges with labels (showing terminal connections)
    for from_n, to_n, key, data in self._graph.edges(keys=True, data=True):
        from_term = data.get('from_term', '')
        to_term = data.get('to_term', '')
        edge_label = f"{from_term} → {to_term}" if from_term and to_term else key
        G.add_edge(from_n, to_n, label=edge_label, key=key)
    
    # Write to dot file
    try:
        # Use networkx built-in write_dot if pydot is available
        nx.drawing.nx_pydot.write_dot(G, filename)
        logger.info(f"  ✅ Graph written using nx_pydot.write_dot")
    except ImportError:
        # Fallback: write simple DOT format manually
        logger.warning("  pydot not available, writing simple DOT format")
        with open(filename, 'w') as f:
            f.write("digraph flowchart {\n")
            f.write("  rankdir=LR;\n")
            f.write("  node [shape=box];\n\n")
            
            # Write nodes
            for node_name in G.nodes():
                label = G.nodes[node_name].get('label', node_name)
                f.write(f'  "{node_name}" [label="{label}"];\n')
            
            f.write("\n")
            
            # Write edges
            for from_n, to_n, data in G.edges(data=True):
                label = data.get('label', '')
                if label:
                    f.write(f'  "{from_n}" -> "{to_n}" [label="{label}"];\n')
                else:
                    f.write(f'  "{from_n}" -> "{to_n}";\n')
            
            f.write("}\n")
    
    logger.info(f"  ✅ Flowchart graph dumped to {filename}")
    logger.info(f"{'='*80}\n")
    
    return os.path.abspath(filename)
```

---

## Usage Workflow

### After Implementation

**Basic usage:**
1. Import subgraph from library
2. Click **"Dump Graph"** button in toolbar
3. File created: `flowchart_graph_20260318_140532.dot` (timestamped)
4. Status bar shows: "Graph dumped to flowchart_graph_20260318_140532.dot"

**For debugging the current issue:**

**Test A - Verify edges after import:**
```bash
ami-local random:// 2>&1 | tee test_dump.log

# In AMI GUI:
# 1. Tools → Manage Libraries → Load export.fc → Apply
# 2. Drag subgraph onto canvas
# 3. Click "Dump Graph" button → flowchart_graph_001.dot
# 4. Check if internal edges exist:
#    - ExponentialMovingAverage1D.0 → WaveformViewer.0
#    - ExponentialMovingAverage1D.0 → ScalarPlot.0
```

**Expected outcomes:**
- **If edges present**: Problem is in compilation, not in `_createSubgraph()`
- **If edges missing**: Problem is in `_createSubgraph()` or import process

**Test B - Verify edges after runtime connection:**
```bash
# Continuing from Test A:
# 5. Add waveform source
# 6. Connect: waveform → combined.0 input
# 7. Click "Dump Graph" button again → flowchart_graph_002.dot
# 8. Compare: Did internal edges disappear?
```

**Expected outcomes:**
- **If edges disappear**: Runtime connection corrupts internal edges
- **If edges persist**: Runtime connection is OK, problem is only in compilation

---

## Testing Plan

### Manual Testing Steps

**Test 1: Basic functionality**
```bash
ami-local random://
# Add 2-3 nodes, connect them
# Click "Dump Graph"
# Verify file created with nodes and edges
```

**Test 2: Subgraph import**
```bash
ami-local random://
# Import subgraph from library
# Click "Dump Graph" immediately
# Check if internal edges present in output file
```

**Test 3: Before/after runtime connection**
```bash
ami-local random://
# Import subgraph → Dump (before)
# Make connection → Dump (after)
# Compare the two .dot files
```

**Test 4: Error handling**
```bash
# Test with empty graph
# Test with complex graph
# Verify status messages appear
```

---

## Design Decisions

### Button Placement
**Chosen**: After "Home" button  
**Rationale**: Groups with navigation/debugging tools

### Filename Pattern
**Chosen**: `flowchart_graph_YYYYMMDD_HHMMSS.dot`  
**Rationale**: Timestamped allows multiple snapshots for before/after comparison

### Output Location
**Chosen**: Current working directory (where AMI was launched)  
**Rationale**: Same location as other AMI output files

### Error Handling
**Chosen**: Status bar message + logger output  
**Rationale**: Non-intrusive, doesn't interrupt workflow

### Fallback for Missing pydot
**Chosen**: Manual DOT file writing  
**Rationale**: Ensures functionality even if pydot not installed

---

## Expected Benefits

### Immediate Value
- ✅ Visibility into `self._graph` state at any point
- ✅ Compare flowchart graph vs compiled execution graph
- ✅ Verify internal edges exist before/after operations
- ✅ Identify where edges are lost (flowchart vs compilation)

### For Current Issue
Will definitively answer:
1. **Do internal edges survive `_createSubgraph()`?** (dump after import)
2. **Are edges lost during compilation?** (compare flowchart vs compiled)
3. **Do runtime connections corrupt edges?** (dump before/after connection)

---

## Files to Modify

### 1. `ami/flowchart/Editor.py`
- Line ~351: Add `actionDumpGraph` definition
- Line ~394: Add action to toolbar

### 2. `ami/flowchart/Flowchart.py`
- Line ~830: Add `dumpFlowchartGraph()` method
- Line ~2203: Connect signal to handler
- Line ~2384: Add `dumpGraphClicked()` handler

### Output Files
- **`flowchart_graph_YYYYMMDD_HHMMSS.dot`** - Timestamped dumps in current directory

---

## Implementation Checklist

When implementing:
- [ ] Add `actionDumpGraph` to `Editor.py`
- [ ] Add action to toolbar in correct position
- [ ] Connect signal in `Flowchart.py` `__init__`
- [ ] Implement `dumpGraphClicked()` handler
- [ ] Implement `dumpFlowchartGraph()` method
- [ ] Include fallback for missing pydot
- [ ] Add error handling for I/O failures
- [ ] Add logging statements
- [ ] Add status messages to user
- [ ] Test with empty graph
- [ ] Test with simple graph
- [ ] Test with subgraph import
- [ ] Verify .dot file format is valid
- [ ] Verify file can be visualized with graphviz

---

## After Implementation - Next Steps

1. **Test basic functionality** (create/dump simple graph)
2. **Test subgraph import**:
   - Import from library → Click "Dump Graph"
   - Analyze if internal edges present
3. **Test runtime connection**:
   - Dump before connection
   - Make connection
   - Dump after connection
   - Compare the two dumps
4. **Identify root cause**:
   - If edges missing in flowchart graph → Fix `_createSubgraph()` or import
   - If edges present in flowchart but missing in compiled → Fix compilation
5. **Create targeted fix** based on findings
6. **Verify fix** with before/after dumps
7. **Clean up debug logging** (the 116+ lines added earlier)
8. **Final commit** with all fixes

---

## Related Context

### Current Code State
- ✅ **Terminal coloring fix applied** (lines 416-417, 504-505, 1453-1454, 1510-1511)
  - Placeholder terminals now stay black when imported (not connected)
  - Turn white when runtime connections are made
- ✅ **Connection restoration debug logging added** (~60 lines in `importSubgraphFromFile`)
- ✅ **Extensive debug logging throughout** (~116 lines total)
  - `_createSubgraph()` - boundary processing, terminal creation, coloring
  - `_createSubgraphFromImport()` - metadata conversion
  - `importSubgraphFromFile()` - node restoration and connections
  - `nodeTermConnected()` - runtime connection handling

### Known Issues
1. **Terminal coloring** - FIXED (placeholder terminals now correctly colored)
2. **Missing internal edges in compiled graph** - INVESTIGATING (this button will help diagnose)

### Debug Log Files Available
- `test4_drag_debug.log` - Import from library test
- `test5_connect_debug.log` - Runtime connection test
- `test_connections_debug.log` - Connection restoration detailed debug
- Shows that edges exist in `self._graph` after import (line 55-58)

---

## Notes

- NetworkX already imported as `nx` in Flowchart.py (line 39)
- Follows existing pattern from `homeClicked()`, `saveClicked()`, etc.
- Button architecture: Action → Signal → Handler → Implementation
- Low risk: Read-only operation, won't break existing functionality
- High value: Critical debugging capability for current issue

---

## Status: READY FOR IMPLEMENTATION

All details specified, design decisions made, no blocking questions.
