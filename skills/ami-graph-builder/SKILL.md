---
name: ami-graph-builder
description: Domain tips and workflow guidance for building AMI computation graphs via MCP tools. Load when creating/connecting nodes, working with sources or subgraphs, or diagnosing graph issues.
---

# AMI Graph Builder

You are building computation graphs for AMI (Analysis Monitoring Interface), the LCLS-II online data analysis system. You interact with AMI via MCP tools — NOT by generating Python code.

## Workflow (follow this order)

1. Read `ami://graph/sources` — see what data is available from the experiment
2. Read `ami://subgraph-templates` — check if a template already does what's needed
3. If template exists → `import_subgraph`, connect source to boundary inputs, done
4. If not → build incrementally: `ensure_source` → `create_node` → `connect_nodes`
5. Always finish with: `validate_graph` → `apply_graph` → `get_graph_errors` → `auto_layout`

## Verification (MANDATORY — never skip)

After all nodes are connected, always run this sequence before responding to the user:

### 1. Structural check
Call `validate_graph()`. It returns:
- `{"ok": true, "issues": []}` → no problems, continue
- `{"ok": false, "issues": ["Node 'X' has disconnected required input 'Y'"]}` → fix each issue, then call `validate_graph()` again

### 2. Submit to workers
Call `apply_graph()`. This submits the graph to AMI workers for execution. It is fire-and-forget and returns `{"status": "applied"}`.

### 3. Check runtime errors
Call `get_graph_errors()`. It returns:
- `{"ok": true, "errors": []}` → graph is running cleanly
- `{"ok": false, "errors": [...]}` → runtime issues (type mismatches, missing data, node exceptions). Fix and re-apply.

### 4. Arrange layout
Call `auto_layout()` to arrange nodes neatly in the GUI.

### 5. Report to user
Tell the user:
- Which nodes were created (name + type)
- Which connections were made
- Any manual steps required (e.g., ROI drawing, PythonEditor code)
- Any warnings from `get_graph_errors`

### Optional: Confirm graph structure
For complex graphs (3+ nodes), call `get_graph_state()` to confirm expected nodes and connections exist before reporting done. It returns `{"nodes": [...], "connections": [...], "sources": {...}}`.

### Optional: Confirm data is flowing
Call `list_features()` to see what outputs have live data, then `fetch_data("FeatureName")` to sample a value. Use this if the user wants to verify the graph is producing results, or if `get_graph_errors` reported issues.

## Source Terminal Naming (CRITICAL)

Source node terminals are always named "Out".

    WRONG:   connect_nodes("cspad", "cspad", "Mean.0", "In")
    CORRECT: connect_nodes("cspad", "Out", "Mean.0", "In")

Source nodes always have a single output terminal named "Out", regardless of the source name.

## Node Naming

AMI assigns unique names: BinningNode.0, BinningNode.1, ScatterPlot.0, etc.
Always use the `node_name` returned by `create_node` — never assume the suffix.

## Sources Are Self-Displaying

SourceNodes have built-in viewers. When a user clicks a source node in the GUI:
- Scalar → ScalarWidget
- 1D array → WaveformWidget
- 2D array → ImageWidget

DO NOT create display nodes just to view raw source data.
Only create display nodes for PROCESSED results (after Mean, Sum, ROI, etc.).

If user says "show me the detector" — just `ensure_source("detector_name")` and tell them to click it.

## When to Use Which Node

| User wants... | Use this node | Key inputs |
|---|---|---|
| X vs Y correlation | ScatterPlot | X, Y (both float or Array1d) |
| Value over time | ScalarPlot | In (float) |
| 1D spectrum/profile | LinePlot | X, Y (both Array1d) |
| 2D image of processed data | ImageViewer | In (Array2d) |
| Simple arithmetic (x*2+5, a/b) | Calculator | In (float/Array1d/Array2d) |
| Boolean filter (x > 100) | Filter | In (Any) |
| Histogram | Binning | In (float/Array1d/Array2d) |
| ROI on 2D detector | Roi2D | In (Array2d) |
| Mean of signal | Average0D / Average1D / Average2D | In (match dimensionality) |
| Scan analysis (mean vs step) | MeanVsScan | Bin (float), Value (float) |
| Numpy/scipy transforms, custom logic | PythonEditor | (user writes code in GUI) |

When unsure which node to use, query `ami://node-types` for the full list with terminal specs.

## Display Nodes Are Self-Viewing

ScatterPlot, LinePlot, ScalarPlot, Histogram, Histogram2D, ImageViewer —
these all open their own plot window automatically. No extra viewer needed after them.

## ROI Workflow

ROI nodes (Roi2D, Roi1D) require manual interaction after creation:
1. Create the ROI node and connect the detector source to it
2. Tell the user they MUST click the source node and draw the ROI rectangle in the GUI
3. Only after the ROI is drawn will data flow through the ROI output

Always warn the user about this step — it's not something the agent can do remotely.

## Common Patterns

### Scalar monitoring
```
ensure_source("laser_power") → create_node("ScalarPlot") → connect(source→In)
```

### X vs Y correlation
```
ensure_source(A) + ensure_source(B) → create_node("ScatterPlot") → connect(A→X, B→Y)
```

### ROI intensity tracking
```
ensure_source("detector") → create_node("Roi2D") → create_node("Sum") → create_node("ScalarPlot")
connect: detector→Roi2D.In, Roi2D.Out→Sum.In, Sum.Out→ScalarPlot.In
```

### Azimuthal integration
```
ensure_source("detector") → create_node("RoiArch") → create_node("LinePlot")
connect: detector→RoiArch.In, RoiArch.Bins→LinePlot.X, RoiArch.Counts→LinePlot.Y
(RoiArch geometry must be configured in GUI)
```

### Scan analysis
```
ensure_source("motor") + ensure_source("signal")
→ create_node("MeanVsScan")
connect: motor→MeanVsScan.Bin, signal→MeanVsScan.Value
→ create_node("LinePlot")
connect: MeanVsScan.Bins→LinePlot.X, MeanVsScan.Counts→LinePlot.Y
```

## Labels

Use descriptive Title Case labels when creating nodes:
- Good: "Laser Vs Detector Correlation", "CSPAD Signal Region", "ROI Total Counts"
- Bad: "node1", "my_plot", "ScatterPlot for data"

## Type Compatibility

Check `ami://node-types` for terminal types before connecting. Common rules:
- float sources → float inputs (ScalarPlot.In, Calculator.In, MeanVsScan.Value)
- Array2d sources → Array2d inputs (Roi2D.In, ImageViewer.In, Projection.In)
- Array1d → Array1d inputs (LinePlot.Y, FFT.In, Average1D.In)
- ScatterPlot accepts float or Array1d on both X and Y

If types don't match, you need a conversion node in between.

## Subgraph Boundaries

When you import a subgraph template:
- It has **boundary inputs** — connect external sources to these
- It has **boundary outputs** — connect these to display nodes or downstream processing
- The `import_subgraph` tool returns the boundary terminal names

## Configuring Calculator and Filter

These nodes require expressions/conditions set AFTER connecting inputs.
Expression variables are the **connected wire names** (e.g., `cspad.Out`), NOT terminal names.

### Calculator Workflow
1. Create Calculator node and connect inputs
2. Call `get_node_inputs("Calculator.0")` to see available variable names
3. Call `set_calculator_expression("Calculator.0", "cspad.Out * 2 + 5")`

Expression examples (simple arithmetic only):
- Single input: `"cspad.Out * 2 + 5"`
- Two inputs: `"cspad.Out / laser.Out"` (need `add_node_terminal` for second input)

For numpy/scipy operations (np.sqrt, np.mean, etc.) use PythonEditor instead — it is more reliable and readable for complex expressions.

### Filter Workflow (Event Code Filtering)
1. Create Filter node
2. Add extra input terminal if needed: `add_node_terminal("Filter.0", "In.1", "in", "Any")`
3. Connect sources (e.g., laser event code + detector)
4. Call `get_node_inputs("Filter.0")` to see variable names and output terminals
5. Call `set_filter_conditions("Filter.0", conditions)` with JSON:

```json
{
  "If": {
    "condition": "laser.Out == 1",
    "Filter.0.Out": "cspad.Out"
  },
  "Else": {
    "Filter.0.Out": "None"
  }
}
```

This passes cspad images through only when laser is on (event code == 1).

### Adding Extra Terminals
```
add_node_terminal("Calculator.0", "In.1", "in", "float")  # extra Calculator input
add_node_terminal("Filter.0", "In.1", "in", "Any")        # extra Filter input
add_node_terminal("Filter.0", "Out.1", "out", "Any")      # extra Filter output
```

## Common Pitfalls

### Stack Nodes Need Sequence Inputs
Stack1d and Stack2d expect list/tuple inputs, not single scalars. Connect them to collection nodes:
- `timestamp → PickN (N=5) → Stack1d` ✓
- `timestamp → Stack1d` ✗ (will fail: "arrays to stack must be passed as a sequence type")

### CurveFit Variables Must Include Independent Variable
When using CurveFit, include the independent variable first in the `variables` parameter:
- `variables="x,a,b"` for function `f="a*x+b"` ✓
- `variables="a,b"` ✗ (will fail: lambdify argument mismatch)

### Calculator/Filter Must Be Connected Before Configuring
Expression variables are the connected wire names (e.g., `cspad.Out`), not terminal
names (`In`). Always: connect inputs → call `get_node_inputs()` → then set expression/conditions.

### Accumulator/PythonEditor Nodes
These nodes work out-of-the-box with default templates for MCP usage. Custom code requires GUI editor interaction.

### Calculator Is for Simple Arithmetic Only
Use Calculator for basic math (addition, subtraction, multiplication, division, comparisons).
For numpy or scipy functions, use PythonEditor — it handles complex expressions more reliably.
- `"cspad.Out * 2 + offset.Out"` ✓ Calculator
- `"np.sqrt(cspad.Out)"` ✗ Calculator → use PythonEditor

## Node Configuration

Most nodes have configurable parameters (bin counts, sigma values, axis settings, etc.).

### Reading current parameters
```
get_node_parameters("GaussianFilter1D.0")
# Returns: {"node": "GaussianFilter1D.0", "parameters": {"sigma": 1.0, "axis": -1}}
```

### Setting parameters
```
set_node_parameters("GaussianFilter1D.0", {"sigma": 2.0, "axis": 0})
# Returns: {"node": "GaussianFilter1D.0", "parameters": {"sigma": 2.0, "axis": 0}}
```

Use `get_node_parameters` first to see what parameters are available and their current values before making changes. After `set_node_parameters`, call `apply_graph()` for the change to take effect.

Calculator and Filter nodes have dedicated tools (`set_calculator_expression`, `set_filter_conditions`) — use those instead for expression/condition changes.

## Graph Management

### Save and load
```
save_graph("/path/to/graph.fc")   # save current graph to file
load_graph("/path/to/graph.fc")   # load graph from file (replaces current)
clear_graph()                      # remove all nodes (use with caution)
```

### Creating subgraphs
To group existing nodes into a visual subgraph container:
```
create_subgraph(["PythonEditor.0", "Average2D.0"], "Jungfrau Processing", "Description here")
# Returns: {"subgraph_name": "Jungfrau Processing", "terminals": {...}}
```

Source nodes are automatically excluded. Boundary terminals are auto-detected from existing cross-boundary connections.

To inspect an existing subgraph's terminals:
```
list_subgraphs()                              # list all subgraphs with child nodes
list_subgraph_terminals("Jungfrau Processing") # detailed boundary terminal info
```

To save a subgraph as a reusable template:
```
export_subgraph("Jungfrau Processing", "/path/to/template.fc")
```

## Error Recovery

All MCP tools return helpful error context:
- Wrong node type → response includes available types
- Wrong terminal name → response includes available terminals for that node
- Source doesn't exist → response includes available sources

Use this feedback to self-correct. Don't guess — read the error response.

### Removing nodes and connections
If a node was created incorrectly or a connection is wrong:
```
delete_node("BinningNode.0")              # removes node and all its connections
disconnect_nodes("cspad", "Out", "Mean.0", "In")  # removes a single connection
remove_node_terminal("Calculator.0", "In.1")      # removes a user-added terminal
```

Always `validate_graph()` after making corrections to confirm the issue is resolved.
