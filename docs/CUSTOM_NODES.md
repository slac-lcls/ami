# Custom Node Implementation Guide

Reference for implementing custom GUI nodes in the AMI flowchart system.
Covers the full stack: GUI layer → `to_operation()` → `graph_nodes` execution → display widgets.

---

## Table of Contents

1. [Quick Decision Maps](#1-quick-decision-maps)
2. [Node Anatomy](#2-node-anatomy)
3. [uiTemplate Reference](#3-uitemplate-reference)
4. [to_operation() Patterns](#4-to_operation-patterns)
5. [Display Integration](#5-display-integration)
6. [Key Invariants and Gotchas](#6-key-invariants-and-gotchas)
7. [Registration via Manage Library](#7-registration-via-manage-library)
8. [EPICS Ctrl Interface](#8-epics-ctrl-interface)

---

## 1. Quick Decision Maps

### Which `graph_nodes` type to use in `to_operation()`?

| Requirement | Node type | `global_op` flag |
|---|---|---|
| Pure per-shot function, no state | `gn.Map` | False |
| Make any value viewable / latest value | `gn.PickN(N=1)` | True |
| Collect N sequential samples as a list | `gn.PickN(N>1)` | True |
| Sum N frames numerically (numpy) | `gn.SumN` | True |
| Sliding window of last N values (continuous) | `gn.RollingBuffer` | True |
| Aggregate by a categorical key | `gn.ReduceByKey` | True |
| Custom multi-tier accumulation | `gn.Accumulator` | True |

**Rule of thumb:** anything that needs to aggregate across events or across workers is a `GlobalTransformation` → set `global_op=True` on the node and use one of the global graph node types.

### Which node flags to set?

| Flag | When to set | Effect |
|---|---|---|
| `global_op=True` | Any node returning a `GlobalTransformation` | Renders blue; adds "Latch Outputs" context menu |
| `viewable=True` | Node that only subscribes to an upstream value (no `to_operation`) | Manager publishes the input; `AsyncFetcher` requests it directly |
| `buffered=True` | Node whose `to_operation` emits buffer outputs for display | Uses `buffered_topics()`/`buffered_terms()` for subscription |
| `exportable=True` | Node that exports data via the export service | `graphCommHandler.export()` is called on build_views |
| `allowAddInput=True` | Node that accepts a variable number of inputs | Adds "Add input" to context menu |

---

## 2. Node Anatomy

### Base class hierarchy

```
Node                    (ami/flowchart/Node.py:29)
└── CtrlNode            (ami/flowchart/library/common.py:16)
    ├── SourceNode      (common.py:147)   — data source, viewable=True, no to_operation
    └── GroupedNode     (common.py:199)   — matched input/output terminal pairs
```

**Use `Node`** when there are no user-configurable parameters (no `uiTemplate` needed).
**Use `CtrlNode`** for everything else — it wires `uiTemplate` into `self.ctrls`/`self.values` automatically.

### Required class attributes

```python
class MyNode(CtrlNode):
    """One-line description of what this node does."""  # REQUIRED — used by NodeLibrary
    nodeName = "MyNode"                                 # REQUIRED — serialized in .fc files
```

Both are mandatory. `isNodeClass()` rejects classes missing `nodeName`; `getLabelTree()` asserts a docstring exists.

### Terminal definitions

```python
terminals = {
    "TermName": {
        "io": "in",           # REQUIRED: "in" or "out"
        "ttype": float,       # REQUIRED: type annotation
        "removable": True,    # optional
        "optional": True,     # optional
        "group": "grp_name",  # optional — pairs terminals into a named group
    }
}
```

**Common `ttype` values:**

| Type | Meaning |
|---|---|
| `float`, `int`, `bool` | Scalar |
| `str` | String |
| `typing.Any` | Any type |
| `amitypes.Array1d` | 1D numpy array |
| `amitypes.Array2d` | 2D numpy array |
| `amitypes.Array3d` | 3D numpy array |
| `amitypes.Array` | Any numpy array |
| `amitypes.MultiChannelWaveform` | Multi-channel waveform |
| `dict` | Python dict |
| `typing.Union[float, Array1d]` | Union type |

### Constructor pattern

```python
def __init__(self, name):
    super().__init__(
        name,
        terminals={
            "In":  {"io": "in",  "ttype": Array1d},
            "Out": {"io": "out", "ttype": Array1d},
        },
        global_op=True,   # set if to_operation returns a GlobalTransformation
    )
```

### `to_operation()` signature

Called by the flowchart on Apply with these kwargs:

```python
def to_operation(self, inputs, outputs, **kwargs):
    # inputs:  dict {term_name: variable_name_str}
    #          e.g. {"In": "SomeSource.0.Out"}
    # outputs: list [variable_name_str, ...]
    #          e.g. ["MyNode.0.Out"]
    # kwargs always contains: parent (str), latched (bool)
    # — pass **kwargs through to every gn.* constructor
```

Returns either a single `gn.*` node or a list of `gn.*` nodes (for multi-stage pipelines).

### `isChanged()` — when does `.fc` restore trigger graph resubmit?

```python
def isChanged(self, restore_ctrl, restore_widget):
    return False                        # viewer-only nodes (no to_operation)
    return restore_ctrl                 # ctrl values parameterize to_operation (most nodes)
    return restore_widget               # widget state parameterizes to_operation (code editors)
    return restore_ctrl or restore_widget  # default CtrlNode behavior
```

---

## 3. `uiTemplate` Reference

Defined as a class-level list; parsed by `generateUi()` in `ami/flowchart/library/WidgetGroup.py:439`.

```python
uiTemplate = [
    ("field_name", "widget_type"),
    ("field_name", "widget_type", {options}),
]
```

After `__init__`, the values are accessible as `self.values["field_name"]` and the widget as `self.ctrls["field_name"]`.

### Widget types

| Type string | Qt widget | Key options |
|---|---|---|
| `"intSpin"` | `QSpinBox` | `value` (int), `min`, `max` |
| `"doubleSpin"` | `ScientificDoubleSpinBox` | `value` (float), `min`, `max` |
| `"spin"` | pyqtgraph `SpinBox` | any pyqtgraph SpinBox opts |
| `"check"` | `QCheckBox` | `checked` (bool) |
| `"combo"` | `QComboBox` | `values` (list), `value` (initial) |
| `"color"` | pyqtgraph `ColorButton` | `value` (RGB tuple) |
| `"text"` | `QLineEdit` | `value` (str), `placeholder` (str) |
| `"file_in"` | `PushButtonSelectFile` | `value` (path str) |
| `"file_out"` | `PushButtonSelectFile` | `value` (path str) |

**Cross-cutting options** (any widget type):
- `"tip"` — tooltip string
- `"hidden"` — bool, hides the row initially
- `"group"` — str, wraps in a `QGroupBox`; creates `self.values[group][field]` and `self.ctrls[group][field]`

### Accessing values in `to_operation()`

```python
# Direct field
n = self.values["N"]

# Grouped field
label = self.values["X Axis"]["Label"]
```

### Reacting to ctrl changes (dynamic terminals)

Override `state_changed()` to add/remove terminals when a checkbox toggles:

```python
def state_changed(self, *args, **kwargs):
    super().state_changed(*args, **kwargs)
    name, group, val = args[0], args[1], args[2]
    if name == "weighted" and val:
        self.addTerminal("Weights", io="in", ttype=float)
    elif name == "weighted" and not val:
        self.removeTerminal("Weights")
```

### Setting ctrl values programmatically (without triggering signal loops)

```python
self.stateGroup.blockSignals(True)
self.ctrls["field"].setValue(new_value)
self.stateGroup.blockSignals(False)
```

---

## 4. `to_operation()` Patterns

### Pattern A — Simple Map (no UI, Node base)

Use for: pure per-shot transform, no user parameters, no state.

```python
import ami.graph_nodes as gn
from amitypes import Array1d
from ami.flowchart.Node import Node


class Abs1D(Node):
    """Element-wise absolute value of a 1D array."""
    nodeName = "Abs1D"

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "In":  {"io": "in",  "ttype": Array1d},
                "Out": {"io": "out", "ttype": Array1d},
            },
        )

    def to_operation(self, **kwargs):
        return gn.Map(name=self.name() + "_operation", **kwargs, func=lambda a: abs(a))
```

### Pattern B — Parametric Map (CtrlNode + uiTemplate)

Use for: per-shot transform with user-configurable parameters. Ctrl values are captured in the closure at compile time.

```python
import numpy as np
import ami.graph_nodes as gn
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode


class Threshold1D(CtrlNode):
    """Zero values below threshold in a 1D array."""
    nodeName = "Threshold1D"
    uiTemplate = [
        ("threshold", "doubleSpin", {"value": 0.0}),
        ("invert",    "check",      {"checked": False}),
    ]

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "In":  {"io": "in",  "ttype": Array1d},
                "Out": {"io": "out", "ttype": Array1d},
            },
        )

    def to_operation(self, **kwargs):
        threshold = self.values["threshold"]   # captured at compile time
        invert    = self.values["invert"]

        def func(arr):
            mask = arr < threshold if not invert else arr >= threshold
            result = arr.copy()
            result[mask] = 0
            return result

        return gn.Map(name=self.name() + "_operation", **kwargs, func=func)
```

### Pattern C — PickN → Map (collect N, then compute)

Use for: any computation that needs N samples before producing a result (frame average, statistics over a batch).
Requires `global_op=True`.

```python
import numpy as np
import ami.graph_nodes as gn
from amitypes import Array2d
from ami.flowchart.library.common import CtrlNode


class FrameAverage(CtrlNode):
    """Collect N frames and compute their pixel-wise mean."""
    nodeName = "FrameAverage"
    uiTemplate = [("N", "intSpin", {"value": 10, "min": 2})]

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "In":  {"io": "in",  "ttype": Array2d},
                "Out": {"io": "out", "ttype": Array2d},
            },
            global_op=True,
        )

    def to_operation(self, inputs, outputs, **kwargs):
        collected = [self.name() + "_collected"]

        return [
            gn.PickN(
                name=self.name() + "_pick",
                N=self.values["N"],
                inputs=inputs,
                outputs=collected,
                **kwargs,
            ),
            gn.Map(
                name=self.name() + "_mean",
                inputs=collected,
                outputs=outputs,
                func=lambda frames: np.mean(frames, axis=0),
                **kwargs,
            ),
        ]
```

**Gotcha:** `PickN` returns `None` until N samples are collected. The downstream `Map` is only called when `PickN` fires, so this is handled automatically — but any `Map` that directly consumes a `PickN` output must not assume the value is always present.

### Pattern D — SumN → Map (sum N frames, then normalize)

Use for: numeric sum of N shots (e.g., improve SNR on array detectors). Simpler than `Accumulator` but hardcoded to `np.add`.
`SumN` always produces **2 outputs**: `(count, sum)`.

```python
import ami.graph_nodes as gn
from amitypes import Array2d
from ami.flowchart.library.common import CtrlNode


class SumFrames(CtrlNode):
    """Sum N detector frames."""
    nodeName = "SumFrames"
    uiTemplate = [("N", "intSpin", {"value": 10, "min": 2})]

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "In":    {"io": "in",  "ttype": Array2d},
                "Sum":   {"io": "out", "ttype": Array2d},
                "Count": {"io": "out", "ttype": int},
            },
            global_op=True,
        )

    def to_operation(self, inputs, outputs, **kwargs):
        # SumN outputs are always [count_var, sum_var] — note the order
        sum_outputs = [self.name() + "_count", self.name() + "_sum"]

        def split(count, total):
            return total, count

        return [
            gn.SumN(
                name=self.name() + "_sumN",
                N=self.values["N"],
                inputs=inputs,
                outputs=sum_outputs,
                **kwargs,
            ),
            gn.Map(
                name=self.name() + "_split",
                inputs=sum_outputs,
                outputs=outputs,
                func=split,
                **kwargs,
            ),
        ]
```

### Pattern E — Accumulator (infinite or custom reduction)

Use for: custom multi-tier accumulation that doesn't fit PickN/SumN — running mean, variance, custom histograms, anything requiring user-supplied logic.
`Accumulator` also always produces **2 outputs**: `(count, result)`.

The reduction signature is: `reduction(res, *values, count=count, reset=reset)` where `reset=True` on the first call after a heartbeat boundary.

```python
import numpy as np
import ami.graph_nodes as gn
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode


class RunningMean1D(CtrlNode):
    """Continuously accumulate a running mean of 1D arrays."""
    nodeName = "RunningMean1D"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "In":  {"io": "in",  "ttype": Array1d},
                "Out": {"io": "out", "ttype": Array1d},
            },
            global_op=True,
        )

    def to_operation(self, inputs, outputs, **kwargs):
        acc_outputs = [self.name() + "_count", self.name() + "_sum"]

        def reduction(res, arr, count=1, reset=False):
            if reset:
                return arr
            return res + arr

        def normalize(count, total):
            return total / count

        return [
            gn.Accumulator(
                name=self.name() + "_acc",
                inputs=inputs,
                outputs=acc_outputs,
                res_factory=lambda: 0,
                reduction=reduction,
                **kwargs,
            ),
            gn.Map(
                name=self.name() + "_norm",
                inputs=acc_outputs,
                outputs=outputs,
                func=normalize,
                **kwargs,
            ),
        ]
```

**Worker/local/global reductions:** If you need different logic at each tier, pass `worker_reduction`, `local_reduction`, `global_reduction` separately instead of a single `reduction`.

### Pattern F — ReduceByKey → Map (bin by key, post-process)

Use for: aggregating by a categorical label (scan step index, detector channel, etc.).
Output is a `dict {key: accumulated_value}`.

```python
import numpy as np
import ami.graph_nodes as gn
from ami.flowchart.library.common import CtrlNode


class MeanByBin(CtrlNode):
    """Compute per-bin mean of a scalar keyed by an integer bin index."""
    nodeName = "MeanByBin"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "Key":    {"io": "in",  "ttype": int},
                "Value":  {"io": "in",  "ttype": float},
                "Result": {"io": "out", "ttype": dict},
            },
            global_op=True,
        )

    def to_operation(self, inputs, outputs, **kwargs):
        reduce_outputs = [self.name() + "_reduced"]

        # reduction receives (current_value, new_value) per key
        # accumulate (sum, count) tuples
        def reduction(cur, val):
            return (cur[0] + val[0], cur[1] + val[1])

        # map raw inputs to (value, 1) before keying
        map_outputs = [self.name() + "_key", self.name() + "_pair"]

        def make_pair(k, v):
            return k, (v, 1)

        def compute_means(d):
            return {k: v[0] / v[1] for k, v in d.items()}

        return [
            gn.Map(
                name=self.name() + "_pair_map",
                inputs=inputs,
                outputs=map_outputs,
                func=make_pair,
                **kwargs,
            ),
            gn.ReduceByKey(
                name=self.name() + "_reduce",
                inputs=map_outputs,
                outputs=reduce_outputs,
                reduction=reduction,
                **kwargs,
            ),
            gn.Map(
                name=self.name() + "_means",
                inputs=reduce_outputs,
                outputs=outputs,
                func=compute_means,
                **kwargs,
            ),
        ]
```

### Pattern G — RollingBuffer → Map (for buffered=True display nodes)

Use for: any node that maintains a sliding window of recent values for display (scatter plots, time-series). Use `buffered=True` on the node.
`RollingBuffer` always produces **2 outputs**: `(count, buffer_list)`.

```python
import ami.graph_nodes as gn
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode
from ami.flowchart.library.DisplayWidgets import ScatterWidget


class ScatterBuffer(CtrlNode):
    """Plot X vs Y from a rolling buffer of N events."""
    nodeName = "ScatterBuffer"
    uiTemplate = [("N", "intSpin", {"value": 100, "min": 1})]

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "X": {"io": "in", "ttype": float},
                "Y": {"io": "in", "ttype": float},
            },
            buffered=True,
        )

    def isChanged(self, restore_ctrl, restore_widget):
        return restore_ctrl

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, ScatterWidget, **kwargs)

    def to_operation(self, inputs, outputs, **kwargs):
        # outputs must be keyed by input terminal name for buffered nodes
        outputs = [self.name() + "." + k for k in inputs.keys()]
        buf_outputs = [self.name() + "_count", self.name() + "_buf"]

        return [
            gn.RollingBuffer(
                name=self.name() + "_buffer",
                N=self.values["N"],
                inputs=inputs,
                outputs=buf_outputs,
                **kwargs,
            ),
            gn.Map(
                name=self.name() + "_unzip",
                inputs=buf_outputs,
                outputs=outputs,
                func=lambda count, buf: zip(*buf),
                **kwargs,
            ),
        ]
```

### Pattern H — Map pre-processing → GlobalTransformation → Map post-processing

Use for: any pipeline where raw inputs need reshaping before the global accumulation step, and results need reshaping after.

```python
import numpy as np
import ami.graph_nodes as gn
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode


class NormalizedSumN(CtrlNode):
    """Sum N arrays and normalize by the max value."""
    nodeName = "NormalizedSumN"
    uiTemplate = [("N", "intSpin", {"value": 10, "min": 2})]

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "In":  {"io": "in",  "ttype": Array1d},
                "Out": {"io": "out", "ttype": Array1d},
            },
            global_op=True,
        )

    def to_operation(self, inputs, outputs, **kwargs):
        pre_outputs  = [self.name() + "_float"]
        sum_outputs  = [self.name() + "_count", self.name() + "_sum"]

        return [
            # Pre-processing Map: cast to float32 before accumulating
            gn.Map(
                name=self.name() + "_cast",
                inputs=inputs,
                outputs=pre_outputs,
                func=lambda a: a.astype(np.float32),
                **kwargs,
            ),
            gn.SumN(
                name=self.name() + "_sumN",
                N=self.values["N"],
                inputs=pre_outputs,
                outputs=sum_outputs,
                **kwargs,
            ),
            # Post-processing Map: normalize after accumulation
            gn.Map(
                name=self.name() + "_norm",
                inputs=sum_outputs,
                outputs=outputs,
                func=lambda count, total: total / (total.max() or 1),
                **kwargs,
            ),
        ]
```

---

## 5. Display Integration

### Option 1 — `viewable=True` (subscribe to upstream, no `to_operation`)

The node subscribes to an already-computed upstream variable. The manager publishes it on each heartbeat; the display widget requests it on demand.

```python
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode
from ami.flowchart.library.DisplayWidgets import WaveformWidget


class WaveformMonitor(CtrlNode):
    """Monitor a 1D waveform in real time."""
    nodeName = "WaveformMonitor"
    uiTemplate = []

    def __init__(self, name):
        super().__init__(
            name,
            terminals={"In": {"io": "in", "ttype": Array1d}},
            viewable=True,
        )

    def isChanged(self, restore_ctrl, restore_widget):
        return False   # viewer nodes never trigger graph resubmit

    def display(self, topics, terms, addr, win, **kwargs):
        return super().display(topics, terms, addr, win, WaveformWidget, **kwargs)
```

### Option 2 — `buffered=True` (node produces buffer outputs, display subscribes to those)

The node has a `to_operation()` that emits buffer outputs (e.g., via `RollingBuffer`). The display subscribes to those buffer variable names directly. See Pattern G above.

### Choosing a display widget

| Data shape | Widget class |
|---|---|
| Single `float`/`int` | `ScalarWidget` |
| Any Python object (str representation) | `ObjectWidget` |
| `Array1d` — one or multiple traces | `WaveformWidget` |
| 2D array of lines | `MultiWaveformWidget` |
| `Array2d` — image | `ImageWidget` |
| `Array2d` — image + click cursor | `PixelDetWidget` |
| `(bins, counts)` — 1D histogram | `HistogramWidget` |
| `(xbins, ybins, counts)` — 2D histogram | `Histogram2DWidget` |
| `(X, Y)` — scatter | `ScatterWidget` |
| `(X, Y)` — sorted line | `LineWidget` |
| `(X, Y)` — time-series (date axis) | `TimeWidget` |
| Binary event lanes | `CategoryWidget` |

All widget classes are in `ami/flowchart/library/DisplayWidgets.py`.

### Custom display widget

Use when none of the standard widgets fit.

```python
from qtpy import QtWidgets
import pyqtgraph as pg
from ami.flowchart.library.DisplayWidgets import AsyncFetcher


class MyWidget(QtWidgets.QWidget):
    def __init__(self, topics, terms, addr, parent=None, **kwargs):
        super().__init__(parent)
        self.node = kwargs.get("node", None)

        # AsyncFetcher subscribes to heartbeats and fetches data on each one
        self.fetcher = None
        if addr:
            self.fetcher = AsyncFetcher(topics, terms, addr, parent=self)
            self.fetcher.start()

        # Build UI
        self.label = QtWidgets.QLabel("waiting...", parent=self)
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

    def update(self):
        # Called on each heartbeat by AsyncFetcher signal
        while self.fetcher.ready:
            heartbeat_timestamp, reply = self.fetcher.reply
            # reply = {input_term_name: value}
            for k, v in reply.items():
                self.label.setText(str(v))

    def saveState(self):
        return {}   # return dict of serializable state

    def restoreState(self, state):
        pass

    def close(self):
        if self.fetcher:
            self.fetcher.close()   # REQUIRED — must close fetcher on widget close
```

Then in the node:

```python
def display(self, topics, terms, addr, win, **kwargs):
    if self.widget is None:
        self.widget = MyWidget(topics, terms, addr, parent=win, node=self, **kwargs)
    return self.widget
```

### Bidirectional coupling (interactive overlays that update ctrls)

When a plot overlay (e.g., a draggable ROI) should update the node's ctrl values and trigger a graph resubmit, use this pattern:

```python
def display(self, topics, terms, addr, win, **kwargs):
    super().display(topics, terms, addr, win, ImageWidget, **kwargs)
    if self.widget:
        self.roi = pg.RectROI([ox, oy], [ex, ey])
        self.roi.sigRegionChangeFinished.connect(self._roi_moved)
        self.widget.view.addItem(self.roi)
    return self.widget

def _roi_moved(self, roi):
    self.stateGroup.blockSignals(True)   # prevent loop
    # update self.values and self.ctrls from roi geometry
    self.stateGroup.blockSignals(False)
    self.sigStateChanged.emit(self)      # triggers graph resubmit

def update(self, *args, **kwargs):
    super().update(*args, **kwargs)
    if self.widget:
        # sync ROI position when ctrl spinboxes change
        self.roi.setPos(..., finish=False)
        self.roi.setSize(..., finish=False)
```

See `ami/flowchart/library/Roi.py:237` (`Roi2D`) for a complete implementation.

---

## 6. Key Invariants and Gotchas

1. **`nodeName` and docstring are mandatory.** `isNodeClass()` rejects classes without `nodeName`; `getLabelTree()` asserts a docstring. Always write both.

2. **`global_op=True` whenever returning a `GlobalTransformation`.** Any node whose `to_operation()` returns `PickN`, `SumN`, `Accumulator`, `ReduceByKey`, or `RollingBuffer` (or a pipeline containing one) must set `global_op=True`. Forgetting this means the node renders without the blue color and the latch context menu — and more importantly the graph compiler may color it incorrectly.

3. **Intermediate variable naming must be globally unique.** Convention: `self.name() + "_suffix"`. Since `self.name()` includes a unique instance number (e.g., `"FrameAverage.0"`), this is always unique across nodes. Never use a fixed string alone.

4. **`SumN` and `RollingBuffer` always produce exactly 2 outputs:** `(count, sum)` and `(count, buffer)` respectively. The downstream `Map` must unpack both even if only one is needed.

5. **`PickN` returns `None` until N samples are collected.** The downstream `Map` is only invoked when `PickN` fires (not on every event), so `None` is never passed to `Map` — but keep this in mind when reasoning about output cadence.

6. **`gn.Accumulator` reduction signature:** `reduction(res, *values, count=count, reset=reset)`. The `reset` kwarg is `True` on the very first call after a heartbeat boundary (use it to initialize `res` cleanly rather than relying on `res_factory` alone). `count` is the number of events being folded in at this call.

7. **`stateGroup.blockSignals(True/False)` when setting ctrl values programmatically.** Without blocking, `setValue()` triggers `sigChanged` → `state_changed()` → `update()` → potentially sets the widget again → infinite loop.

8. **`buffered=True` and `viewable=True` are mutually exclusive in practice.** `viewable=True` means no `to_operation`; `buffered=True` means a `to_operation` that emits buffer variable names which the display subscribes to.

9. **`isChanged()` must return truthy for `.fc` restore to trigger graph resubmit.** If your node's `to_operation()` depends on ctrl values (almost always true), return `restore_ctrl`. If it depends on widget state (code editor), return `restore_widget`. Viewer-only nodes return `False`.

10. **Custom widget `close()` must call `self.fetcher.close()`.** `CtrlNode.close()` calls `self.widget.close()` automatically; if your widget doesn't close its `AsyncFetcher`, the ZMQ socket leaks.

11. **Multi-input `Map` functions receive arguments in `inputs` dict order.** The function signature must match the number and order of inputs as they appear in the `inputs` dict passed to `to_operation()`.

12. **Per-worker vs per-heartbeat execution.** `Map` and the `_worker` clone of `GlobalTransformation` nodes run on every raw event. The `_localCollector` and `_globalCollector` clones run once per heartbeat after all contributions arrive. Design your reduction functions accordingly — they are not called at event rate.

---

## 7. Registration via Manage Library

Custom nodes do **not** need to be added to `ami/flowchart/library/__init__.py`. Use the Manage Library GUI instead:

### Workflow

1. **Write your node class** in a standalone `.py` file anywhere on disk. The file must contain at least one class that:
   - Subclasses `Node` (or `CtrlNode`, `GroupedNode`, etc.)
   - Has a `nodeName` class attribute
   - Has a docstring

2. **Open the flowchart GUI.** Click **"Manage Library"** in the toolbar (bottom of the flowchart canvas).

3. Click **"Load Files"** (or "Load Directory" to scan a directory recursively) and select your `.py` file.

4. Click **"Apply"** — `UnifiedLibraryEditor.applyClicked()` (`ami/flowchart/Editor.py:203`) calls `LIBRARY.addNodeType()` for each discovered class and refreshes the sidebar node tree.

5. **Your node now appears in the sidebar** and can be dragged into the flowchart.

### Persistence

The loaded file paths are saved into the `.fc` flowchart file automatically (`state["library"]` at `Flowchart.py:1808`). When the `.fc` file is reopened, `restoreState()` + `applyClicked()` re-imports the modules and re-registers the nodes — no manual steps required.

### Worker process propagation

After Apply, `libraryUpdated()` (`Flowchart.py:2584`) sends `fcMsgs.Library` to the `MessageBroker`, which propagates the extra `sys.path` entries to all spawned node display subprocesses. Each `NodeProcess` re-imports the module and calls `LIBRARY.addNodeType()` on spawn (`ami/client/flowchart.py:245-257`).

### Minimum viable `.py` file

```python
# my_nodes.py
import ami.graph_nodes as gn
from amitypes import Array1d
from ami.flowchart.library.common import CtrlNode


class MyCustomNode(CtrlNode):
    """One-line description."""
    nodeName = "MyCustomNode"
    uiTemplate = [("N", "intSpin", {"value": 10, "min": 1})]

    def __init__(self, name):
        super().__init__(
            name,
            terminals={
                "In":  {"io": "in",  "ttype": Array1d},
                "Out": {"io": "out", "ttype": Array1d},
            },
        )

    def to_operation(self, **kwargs):
        n = self.values["N"]
        return gn.Map(name=self.name() + "_operation", **kwargs, func=lambda a: a[:n])
```

Load this file via Manage Library → Load Files → Apply, and `MyCustomNode` will appear in the sidebar under its module name.

---

## 8. EPICS Ctrl Interface

The flowchart automatically exposes every `uiTemplate` ctrl parameter of every node as a writable **PVAccess PV** via `ami/flowchart/PvCtrlServer.py`. This allows external tools (EPICS screens, scripts, other processes) to read and change graph parameters without touching the GUI.

### PV naming

```
{prefix}:ctrl:{graph_name}:{NodeName.instance}:{param_name}
{prefix}:ctrl:{graph_name}:apply
```

where `prefix = "{hutch}:ami"` when `--hutch` is passed to `ami-client`, otherwise `"ami"`.

Grouped `uiTemplate` fields (those with a `"group"` key in opts) use `{group}__{param}` as the final component.

**Examples** (hutch = `rix`, graph = `rix101331225`):
```
rix:ami:ctrl:rix101331225:FrameAverage.0:N         ← NTScalar int64, writable
rix:ami:ctrl:rix101331225:Threshold1D.0:threshold  ← NTScalar float64, writable
rix:ami:ctrl:rix101331225:Threshold1D.0:invert     ← NTScalar bool, writable
rix:ami:ctrl:rix101331225:apply                    ← NTScalar bool, write to trigger Apply
```

### Workflow

PV writes update the GUI widget and mark the node changed (Apply button turns green), **but do not immediately change the running graph**. This lets you batch multiple parameter changes:

```bash
# 1. Change parameters
pvput rix:ami:ctrl:rix101331225:FrameAverage.0:N 50
pvput rix:ami:ctrl:rix101331225:Threshold1D.0:threshold 0.5

# 2. Apply all changes at once
pvput rix:ami:ctrl:rix101331225:apply 1

# Or via PVA RPC (returns immediately after scheduling apply)
pvacall rix:ami:ctrl:rix101331225:apply
```

### Supported parameter types

| `uiTemplate` type | EPICS NTScalar type | Notes |
|---|---|---|
| `intSpin` | `int64` | Clamped to `min`/`max` from uiTemplate |
| `doubleSpin` / `spin` | `float64` | Clamped to `min`/`max` from uiTemplate |
| `check` | `bool` | |
| `combo` | `string` | Must match one of the combo items |
| `text` | `string` | |
| `file_in` / `file_out` / `color` | — | Not exposed (unsafe) |

### Implementation

`PvCtrlServer` (`ami/flowchart/PvCtrlServer.py`) is instantiated in `FlowchartCtrlWidget.__init__()` and requires `p4p` (already a dependency). It starts automatically — no configuration needed beyond `--hutch`.

**For nodes you implement:** no changes are needed. Any node with a non-empty `uiTemplate` automatically gets EPICS PVs after the first Apply. Nodes with `uiTemplate = []` or no `uiTemplate` are silently skipped.
