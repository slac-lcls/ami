# Critical Analysis: API Mismatch Between Skill and Implementation

**Date:** April 1, 2026  
**Status:** CRITICAL ISSUE IDENTIFIED  
**Priority:** HIGH - Blocks all agent code execution

---

## The Problem

The skill documentation tells the agent to use an API that **DOESN'T EXIST**.

### What the Skill Documents (What Agent Learns)

```python
# Primary API (from SKILL.md)
node = amicli.create_node('ScatterPlot', 'My Plot')
amicli.connect_nodes('source', 'Out', node.name(), 'In')
amicli.ensure_source('cspad')
```

### What Actually Exists

**AmiCli class** (from Flowchart.py lines 1213-1221):
```python
class AmiCli:
    def __init__(self, ctrl, chartWidget, chart, graph, graphCommHandler):
        self.ctrl = ctrl
        self.chartWidget = chartWidget
        self.chart = chart
        self.graph = graph
        self.graphCommHandler = graphCommHandler
    
    # NO OTHER METHODS!
```

**Result:** AmiCli has **ZERO** methods. It's just a data holder.

---

## What Code Agent Generates

Based on current skill documentation:

```python
scatter = amicli.create_node('ScatterPlot', 'Laser Vs Detector')
# ERROR: 'AmiCli' object has no attribute 'create_node'

amicli.connect_nodes('laser', 'Out', scatter.name(), 'X')
# ERROR: 'AmiCli' object has no attribute 'connect_nodes'

amicli.ensure_source('cspad')
# ERROR: 'AmiCli' object has no attribute 'ensure_source'
```

**Every single line of agent-generated code will fail!**

---

## How Did This Happen?

The skill documentation was written describing an **aspirational API** that was never implemented. The magic commands code in `graph_builder.py` has `ensure_source()` as a standalone function, but `create_node()` and `connect_nodes()` were never created.

---

## The Solutions

### Option 1: Implement the Missing Methods on AmiCli (RECOMMENDED)

Add methods to AmiCli that wrap the underlying flowchart API.

**Where to add:** `ami/flowchart/Flowchart.py` in the `chatModeClicked` method

**Implementation:**

```python
class AmiCli:
    def __init__(self, ctrl, chartWidget, chart, graph, graphCommHandler):
        self.ctrl = ctrl
        self.chartWidget = chartWidget
        self.chart = chart
        self.graph = graph
        self.graphCommHandler = graphCommHandler
    
    def create_node(self, node_type, label=None):
        """
        Create a node in the flowchart.
        
        Args:
            node_type: Type of node (e.g., 'ScatterPlot', 'Sum')
            label: Optional descriptive label
        
        Returns:
            The created node
        """
        if label:
            node = self.chart.createNode(node_type)
            node.setLabel(label)
        else:
            node = self.chart.createNode(node_type)
        return node
    
    def connect_nodes(self, src_name, src_term, dst_name, dst_term):
        """
        Connect two nodes in the flowchart.
        
        Args:
            src_name: Source node name
            src_term: Source terminal name
            dst_name: Destination node name
            dst_term: Destination terminal name
        """
        # Get nodes from graph
        src_node = None
        dst_node = None
        
        for name, data in self.graph.nodes(data=True):
            if name == src_name:
                src_node = data.get('node')
            if name == dst_name:
                dst_node = data.get('node')
        
        if src_node and dst_node:
            self.chart.connectTerminals(
                src_node[src_term],
                dst_node[dst_term]
            )
        else:
            raise ValueError(f"Could not find nodes: src={src_name}, dst={dst_name}")
    
    def ensure_source(self, source_name):
        """
        Ensure a source node exists in the graph.
        
        Args:
            source_name: Name of the source
        
        Returns:
            The source node (existing or newly created)
        """
        from ami.flowchart.graph_builder import ensure_source
        return ensure_source(self, source_name)
    
    def disconnect_nodes(self, src_name, src_term, dst_name, dst_term):
        """Disconnect two nodes."""
        # Implementation similar to connect_nodes
        pass
    
    def node_info(self, name):
        """Get information about a node."""
        for node_name, data in self.graph.nodes(data=True):
            if node_name == name:
                return data
        return None
```

**Benefits:**
- ✅ Agent code works immediately
- ✅ Matches skill documentation
- ✅ Clean API for users
- ✅ No skill documentation changes needed

**Drawbacks:**
- Need to implement ~100 lines of wrapper methods
- Need to test node creation/connection API

### Option 2: Update Skill to Use Lower-Level API

Change skill to use `chart.createNode()` directly.

**Skill changes:**
```python
# OLD (documented):
node = amicli.create_node('ScatterPlot', 'Label')

# NEW:
node = amicli.chart.createNode('ScatterPlot')
node.setLabel('Label')
```

**Benefits:**
- ✅ Uses existing API
- ✅ No new code needed

**Drawbacks:**
- ❌ More complex for agent
- ❌ Exposes implementation details
- ❌ Less clean API
- ❌ Agent needs to learn lower-level flowchart API

### Option 3: Hybrid - Minimal AmiCli Methods

Add just the essential methods to AmiCli, use chart for everything else.

**Minimal implementation:**
```python
class AmiCli:
    # ... existing __init__ ...
    
    def create_node(self, node_type, label=None):
        """Simplified node creation."""
        node = self.chart.createNode(node_type)
        if label:
            node.setLabel(label)
        return node
    
    def ensure_source(self, source_name):
        """Simplified source creation."""
        from ami.flowchart.graph_builder import ensure_source
        return ensure_source(self, source_name)
```

Then document in skill: Use `chart.connectTerminals()` directly for connections.

---

## Recommended Solution

**Option 1** - Implement full AmiCli API with all methods.

**Rationale:**
1. Clean separation - users don't need to know flowchart internals
2. Matches existing skill documentation (minimal changes)
3. Future-proof - can add validation, error checking
4. Better UX - simple, consistent API

**Implementation Steps:**
1. Add methods to AmiCli class definition
2. Test each method works
3. Update chat widget execution namespace (already provides amicli)
4. Minor skill updates to clarify API

---

## Current Execution Namespace

In `chat_widget.py` `_execute_code()` method:

```python
namespace = {
    "chart": self.ctrl.chart,          # Flowchart instance
    "graph": self.ctrl.chart._graph,   # NetworkX graph
    "amicli": amicli,                  # AmiCli instance (needs methods!)
    "ensure_source": lambda ...        # Standalone function
    "np": np,
    "pg": pg,
}
```

**What happens now:**
- Agent calls `amicli.create_node()` 
- AttributeError!

**What needs to happen:**
- amicli needs these methods implemented
- Then agent code just works

---

## Testing the Fix

After implementing AmiCli methods:

### Test 1: Create Node
```python
node = amicli.create_node('Sum', 'My Sum')
assert node is not None
assert node.label() == 'My Sum'
```

### Test 2: Connect Nodes
```python
src = amicli.ensure_source('source_0')
sum_node = amicli.create_node('Sum', 'Total')
amicli.connect_nodes('source_0', 'Out', sum_node.name(), 'In')
# Verify connection exists
```

### Test 3: Full Agent Code
```python
# What agent actually generates:
scatter = amicli.create_node('ScatterPlot', 'Laser Vs Detector')
amicli.ensure_source('laser')
amicli.ensure_source('detector')
amicli.connect_nodes('laser', 'Out', scatter.name(), 'X')
amicli.connect_nodes('detector', 'Out', scatter.name(), 'Y')
# Should all work!
```

---

## Impact Assessment

**Current State:**
- ❌ 100% of agent-generated code fails
- ❌ Chat widget is unusable
- ❌ Critical blocker

**After Fix:**
- ✅ Agent code executes successfully
- ✅ Chat widget works end-to-end
- ✅ User can build graphs with natural language

---

## Files to Modify

### 1. `ami/flowchart/Flowchart.py`
- Update AmiCli class definition in `chatModeClicked()` method
- Add: `create_node()`, `connect_nodes()`, `ensure_source()`, `disconnect_nodes()`, `node_info()`
- **Estimate:** +100 lines

### 2. `ami/flowchart/chat_widget.py`
- Already provides amicli in namespace
- No changes needed (once AmiCli has methods)

### 3. `skills/ami-graph-builder/SKILL.md` (optional)
- Add more examples showing the API
- Clarify method signatures
- **Estimate:** Minor updates

---

## Questions to Resolve

1. **Method signatures:** Are the proposed signatures correct?
   - Need to verify `chart.createNode()` signature
   - Need to verify `chart.connectTerminals()` signature
   - Need to check if `node.setLabel()` exists

2. **Node references:** How are nodes referenced?
   - By name string?
   - By node object?
   - Need to check flowchart API

3. **Error handling:** What errors should we raise?
   - Node not found?
   - Invalid connection?
   - Source doesn't exist?

---

## Next Steps

1. **FIRST:** Investigate actual Flowchart API
   - Check `chart.createNode()` signature
   - Check how to set labels
   - Check how to connect terminals
   - Check how to reference nodes

2. **THEN:** Implement AmiCli methods
   - Based on actual API signatures
   - With proper error handling
   - With clear docstrings

3. **FINALLY:** Test end-to-end
   - Agent generates code
   - Code executes successfully
   - Nodes appear in graph

---

## Priority

**CRITICAL** - This must be fixed before any other chat widget improvements.

Without this fix:
- Chat widget is completely broken
- No agent code will ever execute
- Users can't use natural language feature at all

---

**Status:** Awaiting investigation of Flowchart API and implementation approval
