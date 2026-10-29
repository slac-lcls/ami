"""AMI MCP Server - exposes graph manipulation via Model Context Protocol."""

import concurrent.futures
import json
import logging
import os
import re
import shutil
import socket
import tempfile
import threading

from mcp.server.mcpserver import Image, MCPServer

logger = logging.getLogger(__name__)

# MCP server instance
mcp = MCPServer("ami", log_level="WARNING")

# Global references (set by McpServerThread)
_amicli = None
_qt_dispatch = None


def _find_free_port(start=9100, max_tries=100):
    """Find first available port starting from `start`."""
    for offset in range(max_tries):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in range {start}-{start + max_tries}")


def _round(arr):
    """Round floats to 4 significant figures and turn NaN/inf into None so they stay valid JSON."""
    import numpy as np

    arr = np.asarray(arr, dtype=float)
    out = [float(f"{v:.4g}") if np.isfinite(v) else None for v in arr.ravel()]
    return np.array(out, dtype=object).reshape(arr.shape).tolist()


def _downsample_1d(data, points):
    """Min/max-per-bin downsample so narrow peaks survive. Returns (x_bin_start, min, max)."""
    import numpy as np

    n = len(data)
    if n <= points:
        idx = np.arange(n)
        return idx.tolist(), _round(data), _round(data)
    edges = np.linspace(0, n, points + 1).astype(int)
    mins = [np.nanmin(data[a:b]) if np.isfinite(data[a:b]).any() else np.nan for a, b in zip(edges[:-1], edges[1:])]
    maxs = [np.nanmax(data[a:b]) if np.isfinite(data[a:b]).any() else np.nan for a, b in zip(edges[:-1], edges[1:])]
    return edges[:-1].tolist(), _round(mins), _round(maxs)


def _block_means(data, blocks):
    """Coarse grid of block means for a 2D array."""
    import numpy as np

    rows = np.array_split(np.arange(data.shape[0]), min(blocks, data.shape[0]))
    cols = np.array_split(np.arange(data.shape[1]), min(blocks, data.shape[1]))
    with np.errstate(all="ignore"):
        grid = [[np.nanmean(data[np.ix_(r, c)]) for c in cols] for r in rows]
    return _round(grid)


def _summarize_data(data, detail="summary"):
    """Convert fetched data to LLM-friendly JSON summary.

    Args:
        data: Data from feature store (scalar, ndarray, dict, or None)
        detail: 'summary' (statistics only), 'normal' (+ peak, NaN count, ~200-point curve or
                16x16 block means and projections) or 'full' (+ larger curve/grid)

    Returns:
        Dict with type, shape, statistics suitable for JSON serialization
    """
    import numpy as np

    if data is None:
        return {"status": "no_data", "hint": "Data not flowing. Check connections and apply_graph."}
    elif isinstance(data, (int, float, bool)):
        return {"type": "scalar", "value": float(data) if isinstance(data, (int, float)) else data}
    elif isinstance(data, np.ndarray):
        summary = {
            "type": f"Array{data.ndim}d",
            "shape": list(data.shape),
            "dtype": str(data.dtype),
            "min": float(np.nanmin(data)),
            "max": float(np.nanmax(data)),
            "mean": float(np.nanmean(data)),
            "std": float(np.nanstd(data)),
        }
        if detail == "summary" or data.size == 0 or not np.issubdtype(data.dtype, np.number):
            return summary
        values = data.astype(float)
        finite = np.isfinite(values)
        summary["nan_count"] = int(np.isnan(values).sum())
        summary["inf_count"] = int(np.isinf(values).sum())
        if finite.any():
            peak = np.unravel_index(np.nanargmax(np.where(finite, values, np.nan)), values.shape)
            summary["peak"] = {"index": [int(i) for i in peak], "value": float(values[peak])}
        if values.ndim == 1:
            idx, mins, maxs = _downsample_1d(values, 200 if detail == "normal" else 1000)
            summary["curve"] = {"index": idx, "min": mins, "max": maxs}
        elif values.ndim == 2:
            with np.errstate(all="ignore"):
                summary["blocks"] = _block_means(values, 16 if detail == "normal" else 64)
                for axis, key in ((0, "column_means"), (1, "row_means")):
                    proj = np.nanmean(values, axis=axis)
                    idx, mins, maxs = _downsample_1d(proj, 200 if detail == "normal" else 1000)
                    summary[key] = {"index": idx, "min": mins, "max": maxs}
        return summary
    elif isinstance(data, dict):
        # Recursively summarize dict values
        summary = {}
        for k, v in data.items():
            summary[k] = _summarize_data(v, detail)
        return {"type": "dict", "keys": list(data.keys()), "values": summary}
    else:
        return {"type": type(data).__name__, "repr": repr(data)[:200]}


# ──────────────────────────────────────────────────────────────────────
# TOOLS
# ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def create_node(node_type: str, label: str = "") -> str:
    """
    Create a node in the AMI flowchart.

    Args:
        node_type: Type of node (e.g., 'Binning', 'ScatterPlot')
        label: Optional descriptive label

    Returns:
        JSON with node_name, inputs, outputs, or error
    """
    try:
        node = _qt_dispatch(lambda: _amicli.create_node(node_type, label))
        return json.dumps(
            {
                "node_name": node.name(),
                "inputs": list(node.inputs().keys()),
                "outputs": list(node.outputs().keys()),
            }
        )
    except Exception as e:
        # Return helpful error with available types
        available = _qt_dispatch(lambda: _amicli.list_node_types())
        return json.dumps(
            {"error": str(e), "available_types": available[:20], "hint": "Use list_node_types tool for full list"}
        )


@mcp.tool()
def delete_node(node_name: str) -> str:
    """
    Delete a node from the graph.

    Removes the node and all its connections. This is necessary because
    disconnected nodes will stop graph execution.

    Args:
        node_name: Node name (e.g., 'Average.0', 'Roi2D.0')

    Returns:
        JSON with status or error
    """
    try:
        _qt_dispatch(lambda: _amicli.delete_node(node_name))
        return json.dumps({"status": "deleted", "node": node_name})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def connect_nodes(source_node: str, source_terminal: str, dest_node: str, dest_terminal: str) -> str:
    """
    Connect two node terminals.

    Args:
        source_node: Source node name (e.g., 'cspad')
        source_terminal: Source terminal name (e.g., 'cspad' for source nodes, 'Out' for others)
        dest_node: Destination node name (e.g., 'Binning.0')
        dest_terminal: Destination terminal name (e.g., 'In')

    Returns:
        JSON with status or error + available terminals
    """
    try:
        _qt_dispatch(lambda: _amicli.connect_nodes(source_node, source_terminal, dest_node, dest_terminal))
        return json.dumps({"status": "connected"})
    except Exception as e:
        # If error, show available terminals
        try:
            src_info = _qt_dispatch(lambda: _amicli.node_info(source_node))
            dst_info = _qt_dispatch(lambda: _amicli.node_info(dest_node))
            return json.dumps(
                {
                    "error": str(e),
                    "source_outputs": list(src_info["outputs"].keys()) if src_info else None,
                    "dest_inputs": list(dst_info["inputs"].keys()) if dst_info else None,
                }
            )
        except Exception:
            return json.dumps({"error": str(e)})


@mcp.tool()
def disconnect_nodes(source_node: str, source_terminal: str, dest_node: str, dest_terminal: str) -> str:
    """Disconnect two node terminals."""
    try:
        _qt_dispatch(lambda: _amicli.disconnect_nodes(source_node, source_terminal, dest_node, dest_terminal))
        return json.dumps({"status": "disconnected"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def ensure_source(source_name: str) -> str:
    """
    Ensure a data source node exists in the graph.

    Args:
        source_name: Name of the source (e.g., 'cspad', 'laser_power')

    Returns:
        JSON with source_node name and terminals
    """
    try:
        result = _qt_dispatch(lambda: _amicli.ensure_source(source_name))
        return json.dumps({"source_node": result, "terminal": "Out"})
    except Exception as e:
        available = _qt_dispatch(lambda: _amicli.list_sources())
        return json.dumps(
            {
                "error": str(e),
                "available_sources": available,
                "hint": "Source may not be available yet. Check list_sources tool.",
            }
        )


@mcp.tool()
def get_node_parameters(node_name: str) -> str:
    """
    Get current parameter values for a node.

    Args:
        node_name: Node name (e.g., 'GaussianFilter1D.0')

    Returns:
        JSON with node name and current parameter values
    """
    try:
        result = _qt_dispatch(lambda: _amicli.get_node_parameters(node_name))
        return json.dumps({"node": node_name, "parameters": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_node_parameters(node_name: str, parameters: dict) -> str:
    """
    Set parameters on a node.

    Args:
        node_name: Node name (e.g., 'GaussianFilter1D.0')
        parameters: Dict of parameter name to value (e.g., {"sigma": 2.0, "axis": -1})

    Returns:
        JSON with updated parameter values
    """
    try:
        result = _qt_dispatch(lambda: _amicli.set_node_parameters(node_name, parameters))
        return json.dumps({"node": node_name, "parameters": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_graph_errors() -> str:
    """
    Get runtime errors from all nodes in the graph.

    Returns:
        JSON with list of node errors (empty if no errors)
    """
    try:
        errors = _qt_dispatch(lambda: _amicli.get_graph_errors())
        if not errors:
            return json.dumps({"ok": True, "errors": []})
        return json.dumps({"ok": False, "errors": errors})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def apply_graph() -> str:
    """
    Apply the current graph (submit to workers for execution).

    This is fire-and-forget. The apply runs asynchronously.
    Call get_graph_errors after a few seconds to check for issues.

    Returns:
        JSON with status
    """
    try:
        _qt_dispatch(lambda: _amicli.apply_graph())
        return json.dumps({"status": "applied"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_graph_state() -> str:
    """
    Get full graph state: all nodes, connections, available sources.

    Returns:
        JSON with nodes, connections, sources
    """
    try:
        state = _qt_dispatch(lambda: _amicli.get_graph_state())
        return json.dumps(state, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def validate_graph() -> str:
    """
    Check graph for issues (disconnected terminals, type mismatches).

    Returns:
        JSON with list of issues or {"ok": true}
    """
    try:
        issues = _qt_dispatch(lambda: _amicli.validate_graph())
        if not issues:
            return json.dumps({"ok": True, "issues": []})
        return json.dumps({"ok": False, "issues": issues})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def import_subgraph(template_name: str) -> str:
    """
    Instantiate a subgraph template.

    Args:
        template_name: Name of template in library or path to .fc file

    Returns:
        JSON with subgraph_name and boundary terminals (inputs/outputs)
    """
    try:
        result = _qt_dispatch(lambda: _amicli.import_subgraph(template_name))
        return json.dumps(
            {
                "subgraph_name": result["name"],
                "inputs": result["boundary_inputs"],
                "outputs": result["boundary_outputs"],
            }
        )
    except Exception as e:
        available = _qt_dispatch(lambda: _amicli.list_subgraph_templates())
        return json.dumps(
            {
                "error": str(e),
                "available_templates": available,
            }
        )


@mcp.tool()
def list_subgraph_templates() -> str:
    """List all registered subgraph templates with descriptions."""
    try:
        templates = _qt_dispatch(lambda: _amicli.list_subgraph_templates())
        return json.dumps(templates, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def create_subgraph(node_names: list[str], name: str, description: str = "") -> str:
    """
    Group existing nodes into a visual subgraph container.

    Source nodes are automatically excluded (they stay in root view).
    Boundary terminals are auto-detected from existing connections.

    Args:
        node_names: List of node names to group (e.g., ['PythonEditor.0', 'Average2D.0'])
        name: Name for the subgraph (e.g., 'Jungfrau Image View')
        description: Description text

    Returns:
        JSON with subgraph_name and auto-detected boundary inputs/outputs
    """
    try:
        result = _qt_dispatch(lambda: _amicli.create_subgraph(node_names, name, description))
        # After creation, get the boundary info
        sg_info = _qt_dispatch(lambda: _amicli.list_subgraph_terminals(name))
        return json.dumps({"subgraph_name": result, "terminals": sg_info})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def export_subgraph(subgraph_name: str, filename: str) -> str:
    """
    Save a subgraph as a reusable .fc template file.

    Args:
        subgraph_name: Name of existing subgraph
        filename: Path to save the .fc file

    Returns:
        JSON with confirmation
    """
    try:
        _qt_dispatch(lambda: _amicli.export_subgraph(subgraph_name, filename))
        return json.dumps({"exported": subgraph_name, "filename": filename})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_subgraphs() -> str:
    """
    List all subgraphs with their child nodes and boundary terminal names.

    Returns:
        JSON array of subgraphs with name, description, nodes, inputs, outputs
    """
    try:
        result = _qt_dispatch(lambda: _amicli.list_subgraphs())
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_subgraph_terminals(subgraph_name: str) -> str:
    """
    Get detailed boundary terminal info for a subgraph including connections.

    Args:
        subgraph_name: Name of existing subgraph

    Returns:
        JSON with inputs and outputs, each showing terminal name, type,
        external connection, and internal connections
    """
    try:
        result = _qt_dispatch(lambda: _amicli.list_subgraph_terminals(subgraph_name))
        return json.dumps(result, indent=2)
    except Exception as e:
        available = _qt_dispatch(lambda: _amicli.list_subgraphs())
        names = [sg["name"] for sg in available] if available else []
        return json.dumps({"error": str(e), "available_subgraphs": names})


@mcp.tool()
def add_subgraph_input(subgraph_name: str, source_node: str, source_term: str) -> str:
    """
    Add a boundary input terminal to a subgraph.

    Creates an input on the subgraph placeholder and connects the external source.
    To wire the internal side, use connect_nodes(source_node, source_term, internal_node, internal_term)
    which will automatically route through the boundary.

    Args:
        subgraph_name: Name of existing subgraph
        source_node: External node providing data (e.g., 'jungfrau1M:raw:image')
        source_term: Terminal on that node (e.g., 'Out')

    Returns:
        JSON with terminal_name created
    """
    try:
        result = _qt_dispatch(lambda: _amicli.add_subgraph_input(subgraph_name, source_node, source_term))
        return json.dumps({"terminal_name": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def remove_subgraph_input(subgraph_name: str, terminal_name: str) -> str:
    """
    Remove a boundary input terminal from a subgraph.

    Disconnects execution edges and removes visual connections.

    Args:
        subgraph_name: Name of existing subgraph
        terminal_name: Terminal name to remove (e.g., 'jungfrau1M:raw:image.Out')

    Returns:
        JSON with confirmation
    """
    try:
        _qt_dispatch(lambda: _amicli.remove_subgraph_input(subgraph_name, terminal_name))
        return json.dumps({"removed": terminal_name, "subgraph": subgraph_name})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def add_subgraph_output(subgraph_name: str, internal_node: str, internal_term: str) -> str:
    """
    Add a boundary output terminal to a subgraph.

    Exposes an internal node's output on the subgraph boundary.
    To wire the external side, use connect_nodes(internal_node, internal_term, target_node, target_term)
    which will automatically route through the boundary.

    Args:
        subgraph_name: Name of existing subgraph
        internal_node: Internal node to expose (must be child of subgraph)
        internal_term: Terminal on that node (e.g., 'Out')

    Returns:
        JSON with terminal_name created
    """
    try:
        result = _qt_dispatch(lambda: _amicli.add_subgraph_output(subgraph_name, internal_node, internal_term))
        return json.dumps({"terminal_name": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def remove_subgraph_output(subgraph_name: str, terminal_name: str) -> str:
    """
    Remove a boundary output terminal from a subgraph.

    Disconnects execution edges and removes visual connections.

    Args:
        subgraph_name: Name of existing subgraph
        terminal_name: Terminal name to remove (e.g., 'Calculator.0.Out')

    Returns:
        JSON with confirmation
    """
    try:
        _qt_dispatch(lambda: _amicli.remove_subgraph_output(subgraph_name, terminal_name))
        return json.dumps({"removed": terminal_name, "subgraph": subgraph_name})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def move_node_to_subgraph(node_name: str, subgraph_name: str) -> str:
    """
    Move a node from root view into an existing subgraph.

    Only supports root → subgraph moves. Automatically detects and creates
    boundary terminals for cross-boundary connections. Connections between
    the moved node and other nodes already in the subgraph become internal.

    Args:
        node_name: Node to move (must be in root view, not in any subgraph)
        subgraph_name: Target subgraph name

    Returns:
        JSON with new boundary terminals created
    """
    try:
        result = _qt_dispatch(lambda: _amicli.move_node_to_subgraph(node_name, subgraph_name))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def save_graph(filename: str) -> str:
    """Save current graph to .fc file."""
    try:
        path = _qt_dispatch(lambda: _amicli.save_graph(filename))
        return json.dumps({"saved_to": path})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def load_graph(filename: str) -> str:
    """Load graph from .fc file."""
    try:
        _qt_dispatch(lambda: _amicli.load_graph(filename))
        return json.dumps({"loaded_from": filename})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def clear_graph() -> str:
    """Remove all nodes from the graph."""
    try:
        _qt_dispatch(lambda: _amicli.clear_graph())
        return json.dumps({"status": "cleared"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def auto_layout() -> str:
    """
    Re-arrange ALL node positions in the current view.

    This discards the user's own layout. Only call it for a graph you built from
    scratch, or when the user asks for it. Nodes created with create_node are
    already placed next to whatever they get connected to.
    """
    try:
        _qt_dispatch(lambda: _amicli.auto_layout())
        return json.dumps({"status": "arranged"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_references(node_name: str) -> str:
    """
    List the CSV reference overlays on a plot node.

    Args:
        node_name: Plot node name (e.g., 'LinePlot.0', 'WaveformViewer.0')

    Returns:
        JSON with references {name: csv_path} or error
    """
    try:
        refs = _qt_dispatch(lambda: _amicli.list_references(node_name))
        return json.dumps({"node": node_name, "references": refs})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_reference(node_name: str, path: str, name: str = "") -> str:
    """
    Overlay a CSV file as a reference trace on a plot node.

    The CSV must have two columns (x, y) or one column (y, plotted against index),
    with an optional header row. Setting an existing name replaces that reference.
    Takes effect immediately; apply_graph is not needed.

    Args:
        node_name: Plot node name (e.g., 'LinePlot.0', 'WaveformViewer.0')
        path: Path to the CSV file
        name: Reference name shown in the legend (defaults to the file name)

    Returns:
        JSON with the reference name and all references on the node, or error
    """
    try:
        ref_name = _qt_dispatch(lambda: _amicli.set_reference(node_name, path, name))
        refs = _qt_dispatch(lambda: _amicli.list_references(node_name))
        return json.dumps({"node": node_name, "reference": ref_name, "references": refs})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def remove_reference(node_name: str, name: str) -> str:
    """
    Remove a CSV reference overlay from a plot node.

    Args:
        node_name: Plot node name (e.g., 'LinePlot.0')
        name: Reference name (see list_references)

    Returns:
        JSON with the remaining references, or error
    """
    try:
        _qt_dispatch(lambda: _amicli.remove_reference(node_name, name))
        refs = _qt_dispatch(lambda: _amicli.list_references(node_name))
        return json.dumps({"node": node_name, "removed": name, "references": refs})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_plot_traces(node_name: str) -> str:
    """
    List the live traces of a LinePlot or WaveformViewer by their legend names.

    Use these names as the `trace` argument of take_reference / compare_to_reference.

    Args:
        node_name: Plot node name (e.g., 'LinePlot.0')

    Returns:
        JSON with {legend name: {"x": feature or null, "y": feature}}, or error
    """
    try:
        traces = _qt_dispatch(lambda: _amicli.plot_traces(node_name))
        return json.dumps({"node": node_name, "traces": traces})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def take_reference(node_name: str, name: str = "", trace: str = "") -> str:
    """
    Capture the current live data of a LinePlot or WaveformViewer as a reference overlay.

    The data is written to a CSV under ~/.cache/ami/references/ and set with set_reference,
    so it shows in open plot windows and is saved with the graph.

    Args:
        node_name: Plot node name (e.g., 'LinePlot.0', 'WaveformViewer.0')
        name: Reference name shown in the legend (defaults to node name + timestamp)
        trace: Which trace to capture, by its legend name (see list_plot_traces). Required when
               the plot has more than one trace; if omitted then, the error lists the traces —
               ask the user which one they mean.

    Returns:
        JSON with the reference name, trace, CSV path, number of points, and all references, or error
    """
    try:
        features = _qt_dispatch(lambda: _amicli.plot_features(node_name, trace))
        x, y = _amicli.fetch_xy(features)
        path = _amicli.write_reference_csv(node_name, x, y, name)
        ref_name = _qt_dispatch(lambda: _amicli.set_reference(node_name, path, name))
        refs = _qt_dispatch(lambda: _amicli.list_references(node_name))
        return json.dumps(
            {
                "node": node_name,
                "reference": ref_name,
                "trace": trace or features["y"],
                "path": path,
                "points": len(y),
                "references": refs,
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def compare_to_reference(node_name: str, name: str, trace: str = "") -> str:
    """
    Compare a LinePlot/WaveformViewer's current live data with one of its reference overlays.

    The reference is interpolated onto the live x values where they overlap.

    Args:
        node_name: Plot node name (e.g., 'LinePlot.0')
        name: Reference name (see list_references)
        trace: Which live trace to compare, by legend name (see list_plot_traces). Required when the
               plot has more than one trace.

    Returns:
        JSON with overlap points, RMS and max-abs difference, mean offset, correlation,
        live vs reference peak position/value and peak shift, and a ~200-point summary
        of the residual (live - reference), or error
    """
    import numpy as np

    try:
        features = _qt_dispatch(lambda: _amicli.plot_features(node_name, trace))
        rx, ry = _qt_dispatch(lambda: _amicli.reference_xy(node_name, name))
        x, y = _amicli.fetch_xy(features)

        finite_ref = np.isfinite(rx) & np.isfinite(ry)
        rx, ry = rx[finite_ref], ry[finite_ref]
        if len(rx) < 2:
            raise ValueError(f"Reference '{name}' has fewer than 2 finite points")
        order = np.argsort(rx)
        rx, ry = rx[order], ry[order]
        overlap = (x >= rx[0]) & (x <= rx[-1]) & np.isfinite(y)
        if overlap.sum() < 2:
            raise ValueError(
                f"Live x range [{x.min():.4g}, {x.max():.4g}] does not overlap reference [{rx[0]:.4g}, {rx[-1]:.4g}]"
            )
        xo, yo = x[overlap], y[overlap]
        ref = np.interp(xo, rx, ry)
        diff = yo - ref
        live_peak, ref_peak = int(np.nanargmax(yo)), int(np.nanargmax(ref))
        corr = float(np.corrcoef(yo, ref)[0, 1]) if np.std(yo) > 0 and np.std(ref) > 0 else None
        _, rmin, rmax = _downsample_1d(diff, 200)
        return json.dumps(
            {
                "node": node_name,
                "reference": name,
                "overlap_points": int(overlap.sum()),
                "live_points": int(len(x)),
                "rms_diff": float(np.sqrt(np.mean(diff**2))),
                "max_abs_diff": float(np.max(np.abs(diff))),
                "mean_offset": float(np.mean(diff)),
                "correlation": corr,
                "live_peak": {"x": float(xo[live_peak]), "y": float(yo[live_peak])},
                "reference_peak": {"x": float(xo[ref_peak]), "y": float(ref[ref_peak])},
                "peak_shift": float(xo[live_peak] - xo[ref_peak]),
                "residual": {"min": rmin, "max": rmax},
            }
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_node_types() -> str:
    """
    List all available node types with their terminal specifications.

    Returns:
        JSON array of node types with inputs and outputs
        Example: [{"type": "ScatterPlot", "inputs": ["X", "Y"], "outputs": []}, ...]
    """
    try:
        types = _qt_dispatch(lambda: _amicli.list_node_types())
        return json.dumps(types, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def add_node_terminal(node_name: str, terminal_name: str, direction: str, type: str = "Any") -> str:
    """
    Add an input or output terminal to a node.

    Only works on nodes that support dynamic terminals (Calculator, Filter, PythonEditor).

    Args:
        node_name: Node name (e.g., 'Calculator.0', 'Filter.0')
        terminal_name: Name for the new terminal (e.g., 'In.1', 'Out.1')
        direction: 'in' or 'out'
        type: Terminal type. Options: 'Any', 'float', 'int', 'Array1d', 'Array2d', 'Array3d'

    Returns:
        JSON with confirmation or error
    """
    try:
        result = _qt_dispatch(lambda: _amicli.add_terminal(node_name, terminal_name, direction, type))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def remove_node_terminal(node_name: str, terminal_name: str) -> str:
    """
    Remove a terminal from a node. Only user-added terminals can be removed.

    Args:
        node_name: Node name (e.g., 'Calculator.0')
        terminal_name: Terminal to remove (e.g., 'In.1')

    Returns:
        JSON with confirmation or error
    """
    try:
        result = _qt_dispatch(lambda: _amicli.remove_terminal(node_name, terminal_name))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_node_inputs(node_name: str) -> str:
    """
    Get connected variable names and current configuration for a node.

    Use this to discover what variable names to use in Calculator expressions
    or Filter conditions, especially for graphs you didn't build.

    Args:
        node_name: Node name (e.g., 'Calculator.0', 'Filter.0')

    Returns:
        JSON with input_terminals, output_terminals, expression_vars, and current_config
    """
    try:
        result = _qt_dispatch(lambda: _amicli.get_node_inputs(node_name))
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_python_code(node_name: str) -> str:
    """
    Get the code of a PythonEditor node, plus its input/output terminals.

    Returns the default template if no code has been set yet.

    Args:
        node_name: PythonEditor node name (e.g., 'PythonEditor.0')

    Returns:
        JSON with code, inputs (on_event argument order), and outputs (return order), or error
    """
    try:
        result = _qt_dispatch(lambda: _amicli.get_python_code(node_name))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_python_code(node_name: str, code: str) -> str:
    """
    Set the code of a PythonEditor node.

    The code must define `class EventProcessor` with
    `on_event(self, <one arg per input terminal>, *args, **kwargs)` returning one value per
    output terminal (a tuple if there are several), plus begin_run(self), end_run(self),
    begin_step(self, step) and end_step(self, step) (use `pass` if unneeded).
    Add terminals and connect inputs first.
    If the node's editor window is already open, this overwrites its text too, discarding any
    unsaved edits made directly in that window.
    Show the code to the user before calling apply_graph(); then check get_graph_errors().

    Args:
        node_name: PythonEditor node name (e.g., 'PythonEditor.0')
        code: Python source

    Returns:
        JSON with node, inputs, and outputs, or error (e.g. syntax error with line number)
    """
    try:
        result = _qt_dispatch(lambda: _amicli.set_python_code(node_name, code))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_calculator_expression(node_name: str, expression: str) -> str:
    """
    Set the mathematical expression for a Calculator node.

    The expression uses connected wire names as variables (e.g., 'cspad.Out').
    Connect inputs FIRST, then call get_node_inputs() to see available variable names.
    Supports numpy/scipy functions and standard math operators.

    Args:
        node_name: Calculator node name (e.g., 'Calculator.0')
        expression: Math expression (e.g., 'cspad.Out * 2 + 5', 'np.sqrt(cspad.Out)')

    Returns:
        JSON with confirmation and available variables
    """
    try:
        result = _qt_dispatch(lambda: _amicli.set_calculator_expression(node_name, expression))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_filter_conditions(node_name: str, conditions: str) -> str:
    """
    Set filter conditions for a Filter node.

    Conditions is a JSON string with If/Elif/Else blocks. Each block has a
    "condition" (boolean expression using connected wire names) and output
    routing (maps output terminal name to input variable or "None").

    Connect inputs FIRST, then call get_node_inputs() to see available variables.

    Args:
        node_name: Filter node name (e.g., 'Filter.0')
        conditions: JSON string with condition blocks. Example:
            {"If": {"condition": "laser.Out == 1", "Filter.0.Out": "cspad.Out"},
             "Else": {"Filter.0.Out": "None"}}

    Returns:
        JSON with confirmation
    """
    try:
        parsed = json.loads(conditions) if isinstance(conditions, str) else conditions
        result = _qt_dispatch(lambda: _amicli.set_filter_conditions(node_name, parsed))
        return json.dumps(result)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in conditions: {e}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# RESOURCES
# ──────────────────────────────────────────────────────────────────────


@mcp.resource("ami://graph/state")
def resource_graph_state() -> str:
    """Current graph structure: all nodes, connections, sources."""
    try:
        state = _qt_dispatch(lambda: _amicli.get_graph_state())
        return json.dumps(state, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("ami://graph/sources")
def resource_sources() -> str:
    """Available data sources from connected workers."""
    try:
        sources = _qt_dispatch(lambda: _amicli.list_sources())
        return json.dumps(sources, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("ami://node-types")
def resource_node_types() -> str:
    """All available node types with terminal specifications."""
    try:
        types = _qt_dispatch(lambda: _amicli.list_node_types())
        return json.dumps(types, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_features() -> str:
    """
    List all features currently available in the global feature store.

    Features are node outputs that have computed data ready to fetch.
    Use this to discover what data is available before calling fetch_data.

    Returns:
        JSON dict mapping feature names to their types.
        For arrays, the type is a tuple like ("ndarray", 2) for 2D arrays.
    """
    try:
        features = _amicli.list_features()
        return json.dumps(features, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def fetch_data(feature_name: str, detail: str = "summary") -> str:
    """
    Fetch computed data from the graph's feature store.

    Use list_features() first to see available names. If the feature
    isn't in the store yet, a temporary view is registered automatically
    and data is fetched after waiting for one heartbeat.

    Arrays are summarized rather than returned raw, to keep responses compact.

    Args:
        feature_name: Feature name (e.g., 'ScalarPlot.0.Y', 'Roi2D.0.Out', 'cspad')
        detail: 'summary' - shape and min/max/mean/std (default; use to check data is flowing)
                'normal'  - also peak position/value, NaN/inf counts, and for 1D a ~200-point
                            min/max-per-bin curve; for 2D 16x16 block means plus row/column means
                'full'    - like 'normal' with ~1000 points / 64x64 blocks (much larger response)

    Returns:
        JSON with data type, shape, statistics, and the requested detail.
    """
    try:
        if detail not in ("summary", "normal", "full"):
            raise ValueError("detail must be 'summary', 'normal' or 'full'")
        data = _amicli.fetch_data(feature_name)
        return json.dumps(_summarize_data(data, detail))
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def render_plot(node_name: str, timeout: float = 30) -> Image:
    """
    Screenshot a node's display window as a PNG so you can look at it.

    Opens the window if it isn't already open (same as clicking the node in the GUI; the window
    is left open afterwards), waits for its next live update, and returns exactly what the user
    sees: the plot, colour scale/legend, and any ROI box drawn on top. Works for any node with a
    window — display nodes (LinePlot, ImageViewer, WaveformViewer, ...), ROI nodes (Roi2D, Roi1D,
    RoiArch, ScatterRoi), and source nodes. A bare output feature with no window of its own (e.g.
    'Roi2D.0.Out') needs a viewer node connected to it first — use fetch_data for numbers instead.

    Prefer fetch_data(detail='normal') for numbers; use this when the shape of the data matters
    (images, peak shapes, an ROI box's position, comparing to a reference).

    Args:
        node_name: Node name (e.g., 'ImageViewer.0', 'Roi2D.0')
        timeout: Max seconds to wait for the window to open and produce a screenshot (default 30;
                 a window that's busy rendering a large image, or waiting for the next heartbeat,
                 can take a while)

    Returns:
        PNG image, or an error raised as a tool error (e.g. "apply_graph() first" if upstream
        nodes have unapplied changes, or a timeout if no data is flowing)
    """
    future = _qt_dispatch(lambda: _amicli.request_screenshot(node_name))
    try:
        png = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        _qt_dispatch(lambda: _amicli.abandon_screenshot_request(future))
        raise TimeoutError(f"No screenshot from '{node_name}' within {timeout}s; is data flowing?")
    return Image(data=png, format="png")


@mcp.resource("ami://graph/validation")
def resource_validation() -> str:
    """Current graph issues and warnings."""
    try:
        issues = _qt_dispatch(lambda: _amicli.validate_graph())
        return json.dumps({"issues": issues}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("ami://subgraph-templates")
def resource_subgraph_templates() -> str:
    """List of available subgraph templates with descriptions."""
    try:
        templates = _qt_dispatch(lambda: _amicli.list_subgraph_templates())
        return json.dumps(templates, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ──────────────────────────────────────────────────────────────────────
# PROMPTS
# ──────────────────────────────────────────────────────────────────────


@mcp.prompt()
def use_subgraph(template_name: str, source: str = "") -> str:
    """
    Instantiate a subgraph template and connect it to a data source.

    Args:
        template_name: Name of the subgraph template
        source: Data source to connect (optional)
    """
    if not template_name or re.fullmatch(r"\$\w+", template_name.strip()):
        try:
            available = _qt_dispatch(lambda: _amicli.list_subgraph_templates())
            names = [t["name"] for t in available] if available else []
        except Exception:
            names = []
        return (
            "No subgraph template specified yet. "
            f"Available templates: {names}. "
            "Call this prompt again with a real template_name, "
            "or use list_subgraph_templates() to explore options."
        )

    try:
        template_info = _qt_dispatch(lambda: _amicli.subgraph_info(template_name))

        prompt = f"""Instantiate the '{template_name}' subgraph template.

Template description: {template_info.get('description', 'N/A')}
Boundary inputs: {template_info.get('inputs', [])}
Boundary outputs: {template_info.get('outputs', [])}

Steps:
1. Call import_subgraph("{template_name}") to create the subgraph instance
"""
        if source:
            prompt += f"""2. Ensure source '{source}' exists with ensure_source("{source}")
3. Connect source to the subgraph's boundary input(s)
"""
        prompt += """4. Optionally connect boundary outputs to display nodes
5. Call validate_graph() to check for issues"""

        return prompt
    except Exception as e:
        return f"Error loading template info: {e}"


# ──────────────────────────────────────────────────────────────────────
# SERVER THREAD
# ──────────────────────────────────────────────────────────────────────


class McpServerThread(threading.Thread):
    """Runs MCP HTTP server in a background daemon thread."""

    def __init__(self, amicli, qt_dispatch_fn, host="127.0.0.1"):
        """
        Args:
            amicli: AmiCli instance for graph manipulation
            qt_dispatch_fn: QtDispatcher.dispatch function
            host: Server host (default localhost)
        """
        super().__init__(daemon=True, name="ami-mcp-server")
        global _amicli, _qt_dispatch
        _amicli = amicli
        _qt_dispatch = qt_dispatch_fn
        self.host = host
        self.port = _find_free_port()

        # Create temp dir with opencode.jsonc
        self._tmpdir = tempfile.TemporaryDirectory(prefix="ami-mcp-")
        config = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {
                "ami": {
                    "type": "remote",
                    "url": f"http://localhost:{self.port}/mcp",
                    "enabled": True,
                }
            },
            "instructions": [
                ".opencode/skills/ami-graph-builder/SKILL.md",
                ".opencode/skills/ami-performance-monitor/SKILL.md",
            ],
        }
        config_path = os.path.join(self._tmpdir.name, "opencode.jsonc")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        # Copy skills into .opencode/skills/<name>/ so they are both always-loaded
        # (via instructions) and discoverable by name via the skill tool.
        # Skills live in ami/skills/ inside the package so they are accessible
        # in both development and installed environments.
        pkg_skills_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
        for skill_name in ("ami-graph-builder", "ami-performance-monitor"):
            src = os.path.join(pkg_skills_dir, skill_name, "SKILL.md")
            dst_dir = os.path.join(self._tmpdir.name, ".opencode", "skills", skill_name)
            if os.path.exists(src):
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src, os.path.join(dst_dir, "SKILL.md"))

    def run(self):
        """Run MCP server (blocks in this thread)."""
        logger.info(f"AMI MCP server on http://{self.host}:{self.port}/mcp, config dir: {self._tmpdir.name}")

        # Suppress noisy MCP library request logging
        logging.getLogger("mcp").setLevel(logging.WARNING)

        try:
            mcp.run(transport="streamable-http", host=self.host, port=self.port)
        except Exception as e:
            logger.exception(f"MCP server error: {e}")
