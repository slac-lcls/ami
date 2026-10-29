---
name: ami-graph-builder
description: Domain tips and workflow guidance for building AMI computation graphs via MCP tools. Load when creating/connecting nodes, working with sources or subgraphs, or diagnosing graph issues.
---

# AMI Graph Builder

You are building computation graphs for AMI (Analysis Monitoring Interface), the LCLS-II online data analysis system. You interact with AMI via MCP tools — NOT by generating Python code.

## Workflow (follow this order)

1. Read `ami://graph/sources` — see what data is available from the experiment
2. Read `ami://subgraph-templates` (or call `list_subgraph_templates()`) — check if a template already does what's needed
3. If template exists → `import_subgraph`, connect source to boundary inputs, done
4. If not → build incrementally: `ensure_source` → `create_node` → `connect_nodes`
5. Always finish with: `validate_graph` → `apply_graph` → `get_graph_errors`

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

### 4. Layout — do NOT auto-arrange existing graphs
New nodes are placed automatically next to the node they are first connected to,
and existing nodes are never moved. Do **not** call `auto_layout()` when modifying
an existing graph — it rearranges every node and destroys the user's layout.
Only call it when you built the whole graph from an empty canvas, or the user asks.

### 5. Report to user
Tell the user:
- Which nodes were created (name + type)
- Which connections were made
- Any manual steps required
- Any warnings from `get_graph_errors`

### Optional: Confirm graph structure
For complex graphs (3+ nodes), call `get_graph_state()` to confirm expected nodes and connections exist before reporting done. It returns `{"nodes": [...], "connections": [...], "sources": {...}}`.

### Optional: Confirm data is flowing — and that it's right
Call `list_features()` to see what outputs have live data, then `fetch_data("FeatureName")` to sample a value. Use this if the user wants to verify the graph is producing results, or if `get_graph_errors` reported issues.

Flowing isn't the same as correct. To check a result (e.g. that a normalization peaks at 1.0, or an ROI
sum moves with the detector), look at the data itself — see **Looking at Data** below.

## Source Terminal Naming (CRITICAL)

Source node terminals are always named "Out".

    WRONG:   connect_nodes("cspad", "cspad", "Average2D.0", "In")
    CORRECT: connect_nodes("cspad", "Out", "Average2D.0", "In")

Source nodes always have a single output terminal named "Out", regardless of the source name.

## Node Naming

AMI assigns unique names: Binning.0, Binning.1, ScatterPlot.0, etc.
Always use the `node_name` returned by `create_node` — never assume the suffix.

## Sources Are Self-Displaying

SourceNodes have built-in viewers. When a user clicks a source node in the GUI:
- Scalar → ScalarWidget
- 1D array → WaveformWidget
- 2D array → ImageWidget

DO NOT create display nodes just to view raw source data.
Only create display nodes for PROCESSED results (after Mean, Sum, ROI, etc.).

If user says "show me the detector" — call `ensure_source("detector_name")` first (sources aren't
in the graph until you do), then either tell them to click it in the GUI or call
`render_plot("detector_name")` yourself to see it.

## When to Use Which Node

| User wants... | Use this node | Key inputs |
|---|---|---|
| X vs Y correlation | ScatterPlot | X, Y (both float) |
| Value over time | ScalarPlot | Y (float) |
| 1D spectrum/profile | LinePlot | X, Y (both Array1d) |
| 2D image of processed data | ImageViewer | In (Array2d) |
| Simple arithmetic (x*2+5, a/b) | Calculator | In (float/Array1d/Array2d) |
| Boolean filter (x > 100) | Filter | In (Any) |
| Histogram | Binning | In (float/Array1d/Array2d) |
| ROI on 2D detector | Roi2D | In (Array2d) |
| Mean of signal | Average0D / Average1D / Average2D | In (match dimensionality) |
| Scan analysis (mean vs step) | MeanVsScan | Bin (float), Value (float) |
| Per-event numpy/scipy logic no built-in node covers | PythonEditor | terminals you add (see PythonEditor section) |

When unsure which node to use, call `list_node_types()` (or read `ami://node-types`) for the full
list with terminal specs: `[{"type": "ScatterPlot", "inputs": ["X", "Y"], "outputs": []}, ...]`.

## Display Nodes Are Self-Viewing

ScatterPlot, LinePlot, ScalarPlot, Histogram, Histogram2D, ImageViewer —
these all open their own plot window automatically. No extra viewer needed after them.

## ROI Workflow

ROI geometry is ordinary node parameters, so the agent can set it directly with
`set_node_parameters` — no manual drawing required:

| ROI node | Parameters |
|---|---|
| Roi2D | `origin x`, `origin y`, `extent x`, `extent y` |
| Roi1D, ScatterRoi | `origin`, `extent` |
| RoiArch | `center x`, `center y`, `radius o`, `radius i`, `angdeg o`, `angdeg i`, `nbins rad`, `nbins ang` |

Workflow:
1. Create the ROI node, connect the detector to it, and call `apply_graph()`.
2. `render_plot("Roi2D.0")` — see the image with the current box drawn on it.
3. `fetch_data("<detector>", detail="normal")` — get the peak position or block means as numbers.
4. `set_node_parameters("Roi2D.0", {"origin x": ..., "origin y": ..., "extent x": ..., "extent y": ...})`.
   The box moves in the open window immediately, but the workers still use the old region —
   nothing has been applied yet.
5. `render_plot("Roi2D.0")` again and show the image to the user.
6. **Wait for the user's OK, then call `apply_graph()`.** Applying changes what runs on the live
   experiment workers, the same rule as PythonEditor code.
7. Optionally `fetch_data("Roi2D.0.Out")` to confirm the cropped region.

Notes:
- **The window must stay open between steps 4 and 6.** `render_plot` on a node with pending
  upstream changes fails with "apply_graph() first" once its window is closed — ask the user to
  reopen it, or get their OK to apply first, before trying again.
- **Rotate/Flip caveat:** if Rotate or Flip is enabled in the ROI window's display settings,
  `Roi2D` crops the *rotated* image, so the parameter values won't line up with an unrotated
  `fetch_data` array. Tell the user rather than guessing at the right values. A dedicated
  `set_roi` tool that accounts for this is planned.
- The user can still drag the box by hand; `get_node_parameters` reads back what they set.

## Common Patterns

### Scalar monitoring
```
ensure_source("laser_power") → create_node("ScalarPlot") → connect(source→Y)
```

### X vs Y correlation
```
ensure_source(A) + ensure_source(B) → create_node("ScatterPlot") → connect(A→X, B→Y)
```

### ROI intensity tracking
```
ensure_source("detector") → create_node("Roi2D") → create_node("Sum") → create_node("ScalarPlot")
connect: detector→Roi2D.In, Roi2D.Out→Sum.In, Sum.Out→ScalarPlot.Y
```

### Azimuthal integration
```
ensure_source("detector") → create_node("RoiArch") → create_node("LinePlot")
connect: detector→RoiArch.image, RoiArch.RBinCent→LinePlot.X, RoiArch.RProj→LinePlot.Y
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
- float sources → float inputs (ScalarPlot.Y, Calculator.In, MeanVsScan.Value)
- Array2d sources → Array2d inputs (Roi2D.In, ImageViewer.In, Projection.In)
- Array1d → Array1d inputs (LinePlot.Y, FFT.In, Average1D.In)
- ScatterPlot X and Y are both float (one point per event)

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

### Accumulator Nodes
Accumulator works out-of-the-box with its default template for MCP usage. Custom reduction code requires GUI editor interaction.

### Calculator Is for Simple Arithmetic Only
Use Calculator for basic math (addition, subtraction, multiplication, division, comparisons).
For numpy or scipy functions, use PythonEditor — it handles complex expressions more reliably.
- `"cspad.Out * 2 + offset.Out"` ✓ Calculator
- `"np.sqrt(cspad.Out)"` ✗ Calculator → use PythonEditor

## PythonEditor

PythonEditor runs your Python code on **every event, on every worker**. It is a per-event
transform (a `Map`) — nothing more.

### When to use it
Use PythonEditor only when no built-in node does the job. Check these first:
- Arithmetic on one or more inputs → **Calculator**
- ROI / projection / sum / histogram → **Roi2D, Roi1D, Projection, Sum, Binning**
- Averaging or combining across events → **Average0D/1D/2D, PickN, SumN, Accumulator, MeanVsScan**
- Fitting → **CurveFit**; filtering → **Filter**

Good uses: a custom formula with numpy/scipy, multi-input per-event logic, a detector-specific correction.

### Contract
The code must define `class EventProcessor` with an `on_event` method. `on_event` takes one
argument per input terminal (in terminal order) and returns one value per output terminal
(a tuple if there are several), matching each output's declared type.
`begin_run`, `end_run`, `begin_step(step)` and `end_step(step)` are **required** — the workers call
them at run/step boundaries. Leave them as `pass` unless you need them (e.g. reset per-step setup).

```python
import numpy as np


class EventProcessor():

    def __init__(self):
        self.background = 100.0

    def begin_run(self):
        pass

    def end_run(self):
        pass

    def begin_step(self, step):
        pass

    def end_step(self, step):
        pass

    def on_event(self, image, *args, **kwargs):
        return float(np.sum(np.clip(image - self.background, 0, None)))
```

### Workflow
1. `create_node("PythonEditor")` — it starts with **no terminals**
2. Add terminals: `add_node_terminal("PythonEditor.0", "In", "in", "Array2d")`,
   `add_node_terminal("PythonEditor.0", "Out", "out", "float")`
3. Connect inputs and outputs with `connect_nodes`
4. `get_python_code("PythonEditor.0")` — shows the input/output order (and existing code, if editing)
5. `set_python_code("PythonEditor.0", code)` — rejects syntax errors, a missing `EventProcessor.on_event`
   or lifecycle hook, or an argument count that doesn't match the inputs. Start from the template
   `get_python_code` returns and only change `__init__` and `on_event`. If the node's editor window
   is already open in the GUI, this overwrites its text too — any unsaved edits made directly in
   that window are lost.
6. **Show the code to the user and get their OK before `apply_graph()`** — it will run on live experiment workers
7. `apply_graph()` → `get_graph_errors()` to catch runtime exceptions; fix with `set_python_code` and re-apply

### Rules (AMI anti-patterns)
- **No state carried between events.** Don't accumulate into `self` (lists, running sums, counters).
  Each worker sees only some of the events and this state is never combined across workers, so results
  are partial and differ per worker. Put PickN / SumN / Accumulator / Average* downstream instead.
- **No I/O.** No file reads/writes, network calls, or printing/logging in `on_event`.
- **Do setup once.** Load masks, calibration constants, or build lookup tables in `__init__` or
  `begin_run`, not in `on_event`.
- **Keep `on_event` cheap.** It runs at the event rate; slow code delays every heartbeat. If the graph
  slows down after applying, see the performance monitor skill.
- **Return the right shape.** Exactly one value per output, in terminal order, of the declared type.

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

If the node's display window is already open (e.g. an ROI box), `set_node_parameters` also updates
it immediately — the box moves on screen even before `apply_graph()` runs. See **ROI Workflow**.

Calculator and Filter nodes have dedicated tools (`set_calculator_expression`, `set_filter_conditions`) — use those instead for expression/condition changes.

## Reference Traces

Plot nodes (LinePlot, WaveformViewer, ScalarPlot, ScatterPlot, Histogram, ...) can overlay
reference curves loaded from CSV files — e.g. a known-good spectrum to compare against.
This is the same as "Add CSV Reference" in the plot window's CSV dialog.

```
set_reference("LinePlot.0", "/path/to/good_spectrum.csv")             # name defaults to file name
set_reference("LinePlot.0", "/path/to/run12.csv", name="Run 12")      # explicit legend name
list_references("LinePlot.0")    # {"references": {"good_spectrum": "/path/...", "Run 12": "/path/..."}}
remove_reference("LinePlot.0", "Run 12")
```

- CSV format: two columns `x,y`, or one column `y` (plotted against index); a header row is optional
- Setting an existing name replaces that reference
- References are display-only: no `apply_graph()` needed, and open plot windows update immediately
- References are saved with the graph (`save_graph`)
- To plot a reference through the graph (e.g. subtract it), use the `LoadReference1D` node instead

### Taking and comparing references (LinePlot and WaveformViewer only)
```
take_reference("LinePlot.0", name="Golden")        # snapshot the current live trace as a reference
compare_to_reference("LinePlot.0", "Golden")       # live vs reference
```
- A plot can have several traces (extra `X.1`/`Y.1` or `In.1` inputs). References are taken from **one
  trace**. If the plot has more than one, call `list_plot_traces(node)` and pass `trace=` with the legend
  name (e.g. `"PythonEditor.0.Out vs waveform"`). If the user didn't say which trace, **ask them** — don't pick one.
- `take_reference` writes the live data to `~/.cache/ami/references/` and sets it like `set_reference`.
  The data is from a single heartbeat — if the signal is noisy, average it upstream (Average1D) first.
- `compare_to_reference` returns `rms_diff`, `max_abs_diff`, `mean_offset`, `correlation`, both peaks and
  `peak_shift` (in x units), and a downsampled residual (live − reference). Use it to answer "has this
  changed?" instead of comparing two curves by eye.

## Looking at Data

Pick the cheapest tool that answers the question:

| Question | Tool |
|---|---|
| Is data flowing? Rough range? | `fetch_data(name)` — shape, min/max/mean/std |
| Where's the peak? Any NaNs? What does the curve/image look like numerically? | `fetch_data(name, detail="normal")` |
| Does it match a known-good trace? | `compare_to_reference(node, ref)` |
| What does it *look like* (image features, peak shapes, an ROI box) | `render_plot(node_name)` |

- `detail="normal"` adds peak position/value, NaN/inf counts, and either a ~200-point curve (1D) or
  16×16 block means plus row/column means (2D). Curves keep the min **and** max of each bin, so narrow
  peaks aren't averaged away. `detail="full"` is ~5× larger — only use it when `normal` isn't enough.
- `render_plot(node_name)` takes any node with a display window — display nodes, ROI nodes, or
  source nodes — **not** a bare output feature name (e.g. `Roi2D.0.Out` needs a viewer node
  connected to it first; use `fetch_data` for that). It opens the window if it's closed (and
  leaves it open), waits for the next live update, and returns a screenshot of exactly what the
  window shows on screen: the user's own styling, colour scale, legend, reference overlays, and
  any ROI box.
- `render_plot` fails with an "apply_graph() first" error if upstream nodes have unapplied
  changes, and times out after 30s if no data is flowing (check `get_graph_errors()`).
- All of these show **one heartbeat** of data, not a history.

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

### Editing an existing subgraph

Move a root-level node into a subgraph. Connections to nodes already inside become internal;
connections to nodes outside become new boundary terminals automatically:
```
move_node_to_subgraph("Average2D.0", "Jungfrau Processing")   # returns the boundary terminals created
```
Only root → subgraph moves are supported (not subgraph → root, or between subgraphs).

Add or remove boundary terminals by hand:
```
add_subgraph_input("Jungfrau Processing", "jungfrau1M:raw:image", "Out")    # -> {"terminal_name": ...}
add_subgraph_output("Jungfrau Processing", "Average2D.0", "Out")            # internal node must be in the subgraph
remove_subgraph_input("Jungfrau Processing", "jungfrau1M:raw:image.Out")
remove_subgraph_output("Jungfrau Processing", "Average2D.0.Out")
```
- `add_subgraph_input` only wires the *external* side. To feed an internal node, call
  `connect_nodes(source_node, source_term, internal_node, internal_term)` — it routes through the boundary.
- `add_subgraph_output` only exposes the terminal. To use it outside, call
  `connect_nodes(internal_node, internal_term, target_node, target_term)` — same routing.
- Terminal names for removal come from `list_subgraph_terminals(...)`; don't guess them.

## Error Recovery

All MCP tools return helpful error context:
- Wrong node type → response includes available types
- Wrong terminal name → response includes available terminals for that node
- Source doesn't exist → response includes available sources

Use this feedback to self-correct. Don't guess — read the error response.

### Removing nodes and connections
If a node was created incorrectly or a connection is wrong:
```
delete_node("Binning.0")              # removes node and all its connections
disconnect_nodes("cspad", "Out", "Average2D.0", "In")  # removes a single connection
remove_node_terminal("Calculator.0", "In.1")      # removes a user-added terminal
```

Always `validate_graph()` after making corrections to confirm the issue is resolved.

## Performance Monitoring

If a graph change causes performance degradation (GUI updates slowing, latency growing,
high processing time), refer to the AMI Performance Monitor skill for Grafana MCP tool
patterns — diagnosing whether graph execution time, send backpressure, or worker
starvation is the bottleneck using Prometheus metrics and Tempo distributed traces.
That guidance is available via the `ami-performance-monitor` skill.

Key signal after `apply_graph`: if `rate(ami_event_time_seconds_total{type="Datagram"}[30s])` or
`ami_heartbeat_duration_seconds` increases significantly, the new graph operations may
be too expensive.
