"""AMI MCP Server - exposes graph manipulation via Model Context Protocol."""

import atexit
import concurrent.futures
import hmac
import json
import logging
import os
import re
import secrets
import socket
import stat
import threading
from datetime import datetime, timezone

import numpy as np
import uvicorn
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from qtpy import QtCore, QtGui

logger = logging.getLogger(__name__)

# MCP server instance
mcp = MCPServer("ami", log_level="WARNING")

# Global references (set by McpServerThread)
_amicli = None
_qt_dispatch = None

# Where McpServerThread publishes the currently-running TCP server's connection info, so an
# independently-launched harness (e.g. via ami-mcp-connect) can find it without AMI launching
# anything itself. Each launch overwrites it; the most recently started AMI instance wins.
CONNECTION_FILE = os.path.expanduser("~/.config/ami/mcp-server.json")


def _write_connection_file(host, port, hutch="", token=""):
    """Publish the live MCP server's connection info for ami-mcp-connect to discover.

    Writes to a temp file in the same directory and renames it into place, so a concurrent
    reader never observes a partially-written file.
    """
    try:
        os.makedirs(os.path.dirname(CONNECTION_FILE), exist_ok=True)
        payload = {
            "host": host,
            "port": port,
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hutch": hutch,
            "token": token,
        }
        tmp_path = f"{CONNECTION_FILE}.tmp{os.getpid()}"
        with open(tmp_path, "w") as f:
            json.dump(payload, f)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, CONNECTION_FILE)
    except OSError:
        logger.exception(f"Failed to write MCP connection file at {CONNECTION_FILE}")


def _remove_connection_file_if_ours():
    """Remove the connection file, but only if it still names this process.

    Guards against a slow-exiting instance deleting a later instance's file after that later
    instance has already overwritten it.
    """
    try:
        with open(CONNECTION_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return
    if data.get("pid") == os.getpid():
        try:
            os.remove(CONNECTION_FILE)
        except OSError:
            pass


def _find_free_port(start=19100, max_tries=100):
    """Find first available port starting from `start`, probing the same address we bind to."""
    for offset in range(max_tries):
        port = start + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in range {start}-{start + max_tries}")


def _remove_stale_socket(path):
    """Remove a socket left by an earlier run; refuse if a server still answers on it."""
    try:
        if not stat.S_ISSOCK(os.lstat(path).st_mode):
            return  # never delete a non-socket; bind() then fails with "Address already in use"
    except FileNotFoundError:
        return
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        try:
            probe.connect(path)
        except ConnectionRefusedError:
            os.unlink(path)
            return
    raise RuntimeError(f"another server is listening on {path}")


def _round(arr):
    """Round floats to 4 significant figures and turn NaN/inf into None so they stay valid JSON."""
    arr = np.asarray(arr, dtype=float)
    out = [float(f"{v:.4g}") if np.isfinite(v) else None for v in arr.ravel()]
    return np.array(out, dtype=object).reshape(arr.shape).tolist()


def _downsample_1d(data, points):
    """Min/max-per-bin downsample so narrow peaks survive. Returns (x_bin_start, min, max)."""
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
def get_node_flags(node_name: str) -> str:
    """
    Get the latched/reset_on_run flags for a node.

    These are only meaningful on stateful/global nodes (e.g. MeanVsScan, Accumulator, PickN,
    SumN, ReduceByKey, RollingBuffer) -- the response's "stateful" field tells you whether this
    node is one of those. See set_node_flags for what each flag does.

    Args:
        node_name: Node name (e.g., 'MeanVsScan.0')

    Returns:
        JSON with "latched", "reset_on_run", and "stateful" (bool), or error
    """
    try:
        result = _qt_dispatch(lambda: _amicli.get_node_flags(node_name))
        return json.dumps({"node": node_name, **result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def set_node_flags(node_name: str, latched: bool = None, reset_on_run: bool = None) -> str:
    """
    Set latched/reset_on_run flags on a stateful (global_op) node.

    Only works on nodes whose to_operation() returns a GlobalTransformation (e.g. MeanVsScan,
    Accumulator, PickN, SumN, ReduceByKey, RollingBuffer) -- fails with a clear error on any
    other node type (e.g. Filter, PythonEditor, Map-based nodes).

    These two flags solve different problems -- don't confuse them:
    - reset_on_run=False: keep this node's accumulated state across a run/loop restart (e.g. a
      repeat=true offline source wrapping around) instead of losing it every pass. Use this for
      a long-running accumulation like a scan histogram you want to survive multiple loop passes.
    - latched=True: keep reporting this node's last output on heartbeats where its input is
      currently missing (e.g. a one-time calibration/reference measurement whose source has
      since stopped producing). Does NOT by itself help a value survive a loop restart.

    Requires apply_graph() afterward to take effect -- this only updates the flag and marks the
    node changed, matching the GUI's own "Reset on Run" / "Latch Outputs" context-menu toggles.

    Args:
        node_name: Node name (e.g., 'MeanVsScan.0')
        latched: If set, enable/disable output latching (see above)
        reset_on_run: If set, enable/disable resetting this node's state on a run restart
            (reset_on_run=False keeps accumulated state across repeat=true loop restarts)

    Returns:
        JSON with the resulting "latched"/"reset_on_run" values, or error
    """
    try:
        result = _qt_dispatch(lambda: _amicli.set_node_flags(node_name, latched, reset_on_run))
        return json.dumps({"node": node_name, **result})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_graph_errors() -> str:
    """
    Get runtime errors from all nodes in the graph.

    Also includes errors reported by workers/collectors since the last apply_graph that
    couldn't be attributed to a node (node is null, e.g. "worker000: <message>"). An entry
    with graph_purged=true means the worker/collector dropped the graph after the error: it
    produces no data until the problem is fixed and apply_graph is called again. The same
    problem from several workers is one entry with "sources", "count" (reports) and "events"
    (events affected; a warning report covers a whole heartbeat); "traceback" is the
    full worker-side traceback.

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
def get_messages(since_seq: int = 0, level: str = "", include_traceback: bool = False) -> str:
    """
    Get the history of error/warning messages from workers/collectors (the GUI status bar's
    ERROR/WARNING lines), most recently seen last, bounded to the 200 most recent distinct
    problems. Repeats (e.g. a warning re-reported every heartbeat by every worker) update one
    entry's sources/count/last_time and give it a new seq.

    Args:
        since_seq: Only return messages with seq > since_seq. Pass the previous last_seq to
                   poll for new or still-recurring messages.
        level: Optional filter: "error" or "warning" (default: both)
        include_traceback: Include worker-side tracebacks (long; get_graph_errors has them too)

    Returns:
        JSON with "messages" (seq, first_time, last_time, level, source, sources, count, events,
        graph_name, node, message, exception_type, graph_purged[, traceback]) and "last_seq"
    """
    try:
        result = _qt_dispatch(
            lambda: _amicli.get_messages(since_seq=since_seq, level=level or None, include_traceback=include_traceback)
        )
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def apply_graph() -> str:
    """
    Apply the current graph (submit to workers for execution).

    This is fire-and-forget. The apply runs asynchronously, and runtime errors from
    workers/collectors arrive later. Call get_graph_errors (or get_messages) after a few
    seconds to check for issues; an error with graph_purged=true means the graph stopped
    running and must be fixed and re-applied.

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
        JSON array of node types with type, description, inputs, outputs, parameters, viewable,
        buffered, global_op, exportable, and can_add_inputs/can_add_outputs.
        "viewable" or "buffered" being true means render_plot/open_view opens a window for it
        (buffered nodes like ScalarPlot/ScatterPlot show a window of recent events rather than
        the latest value -- check both, not just "viewable"). "global_op" being true means the
        node accepts get_node_flags/set_node_flags (latched/reset_on_run) -- check this before
        creating a node if you need those flags. "exportable" being true means the node
        participates in AMI's named-alias export system (e.g. ExportToWorker, PvExport).
        can_add_inputs/can_add_outputs is true for the few node types - e.g. SumN, PythonEditor -
        whose terminals aren't fixed; their "inputs"/"outputs" here are empty, not "takes no
        input".
        Example: [{"type": "ScatterPlot", "inputs": {"X": {"type": "float", "optional": false},
                  "Y": {"type": "float", "optional": false}}, "outputs": {}, "parameters": [],
                  "viewable": true, "buffered": false, "global_op": false, "exportable": false,
                  "can_add_inputs": false, "can_add_outputs": false}, ...]
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
def set_terminal_optional(node_name: str, terminal_name: str, optional: bool) -> str:
    """
    Mark an input terminal as optional (or required), the same as the GUI's per-terminal
    right-click "Optional" toggle.

    A required (non-optional) input missing on a given heartbeat short-circuits the node -- it
    doesn't run at all that heartbeat, and neither does anything downstream of it. An optional
    input missing on a given heartbeat is simply left out; the node still runs with whichever of
    its optional inputs are present.

    This matters for nodes that keep a rolling history across heartbeats -- ScatterPlot,
    ScalarPlot, TimePlot, Monitor. Marking their inputs optional lets you feed them several
    mutually-exclusive series (e.g. a laser on/off split from a Filter, where the inactive
    branch's output is None each heartbeat) without one series' absence blocking the others from
    ever being recorded. Required inputs are the right choice when a node should produce nothing
    at all unless every one of its inputs is actually present that heartbeat.

    Requires apply_graph() afterward to take effect.

    Args:
        node_name: Node name (e.g., 'ScatterPlot.0')
        terminal_name: Input terminal name (e.g., 'X', 'X.1')
        optional: True to mark the terminal optional, False to mark it required

    Returns:
        JSON with the resulting "optional" value for that terminal, or error
    """
    try:
        result = _qt_dispatch(lambda: _amicli.set_terminal_optional(node_name, terminal_name, optional))
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
        JSON with "input_vars" (terminal name -> connected wire name), "optional_terminals"
        (which of those terminal names are marked optional -- see set_terminal_optional for what
        that means), and "current_config" (node-specific values, e.g. a Filter's conditions or a
        Calculator's expression)
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
    """All available node types with terminal specifications. Same content as list_node_types()."""
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


# render_plot sends its screenshot as a single MCP message; mcp's StreamableHTTP client (via
# httpx2) caps a single SSE event at 1 MiB, and base64-encoding the image adds ~1/3 on top of its
# raw byte count. A busy or maximized window's screenshot can exceed that easily once encoded --
# the client then swallows the resulting SSEError and reports only a bare, unhelpful "SSE stream
# ended without a response" (see #226). RENDER_PLOT_MAX_BYTES leaves headroom under the 1 MiB
# limit for the JSON-RPC envelope and that base64 overhead.
RENDER_PLOT_MAX_BYTES = 700_000

# Long edge, in pixels, a screenshot is downscaled to before _to_jpeg even looks at the size
# budget above. This is close to the resolution some MCP clients (e.g. Claude) downscale images
# to before a model ever sees them, so capping here first loses no visible detail while keeping
# the retry loop below fast even for a huge (e.g. 16-megapixel, maximized-window) screenshot.
RENDER_PLOT_MAX_SIDE = 1568

# Shortest edge, in pixels, below which a screenshot stops being useful to look at; _to_jpeg
# gives up and raises rather than shrink past this.
RENDER_PLOT_MIN_SIDE = 200


def _to_jpeg(png, max_bytes):
    """Re-encode a screenshot PNG as JPEG, downscaled as needed to fit under `max_bytes`.

    Always converts to JPEG, even when the PNG already fits under `max_bytes` -- so render_plot's
    output is a single, predictable format rather than "PNG normally, except sometimes JPEG" (see
    #226 for why PNG alone doesn't reliably fit MCP's transport limit).

    Returns:
        (jpeg_bytes, note) -- `note` is None if no downscaling was needed beyond the initial
        RENDER_PLOT_MAX_SIDE cap, else a one-line description of the resize for the caller to
        relay to the agent (compression artifacts and/or a changed pixel scale may be present).

    Raises:
        ToolError: the image still doesn't fit under `max_bytes` even at RENDER_PLOT_MIN_SIDE.
    """
    image = QtGui.QImage.fromData(png, "PNG")
    orig_size = (image.width(), image.height())

    def scale_to(img, side_cap):
        if max(img.width(), img.height()) <= side_cap:
            return img
        return img.scaled(
            side_cap,
            side_cap,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )

    def encode(img):
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "JPEG", 85)
        return bytes(buf.data())

    image = scale_to(image, RENDER_PLOT_MAX_SIDE)
    data = encode(image)

    side_cap = max(image.width(), image.height())
    for _ in range(4):
        if len(data) <= max_bytes or side_cap <= RENDER_PLOT_MIN_SIDE:
            break
        # 0.9 guards against rounding leaving side_cap (and so the re-encoded size) unchanged.
        side_cap = max(RENDER_PLOT_MIN_SIDE, int(side_cap * (max_bytes / len(data)) ** 0.5 * 0.9))
        image = scale_to(image, side_cap)
        data = encode(image)

    if len(data) > max_bytes:
        raise ToolError(
            f"Screenshot is {len(data) / 1000:.0f} KB and can't be shrunk under the "
            f"{max_bytes / 1000:.0f} KB MCP transport limit; try fetch_data instead."
        )

    if (image.width(), image.height()) == orig_size:
        return data, None
    note = (
        f"resized {orig_size[0]}x{orig_size[1]} -> {image.width()}x{image.height()} to fit the "
        f"{max_bytes // 1000} KB MCP transport limit"
    )
    return data, note


def _dispatch_or_tool_error(fn):
    """Run fn() on the Qt thread (same as _qt_dispatch), turning a *synchronous* exception --
    e.g. AmiCli.open_view()'s KeyError (node not found), TypeError (node has no plot window),
    or RuntimeError (unapplied upstream changes) raised while opening/dispatching to a node's
    window, before any future is even created -- into a ToolError instead of letting it
    escape raw as an opaque "Error executing tool ..." with no message.

    Shared by render_plot and the get_plot_config/set_plot_config/set_trace_style family, all
    of which start with "_qt_dispatch(lambda: _amicli.<open the window and return a pending
    request's future>(node_name))".
    """
    try:
        return _qt_dispatch(fn)
    except Exception as e:
        raise ToolError(str(e))


@mcp.tool()
def render_plot(
    node_name: str, timeout: float = 30, max_size: int = RENDER_PLOT_MAX_BYTES
) -> Image | list[Image | str]:
    """
    Screenshot a node's display window as a JPEG so you can look at it.

    Opens the window if it isn't already open (same as clicking the node in the GUI; the window
    is left open afterwards), waits for its next live update, and returns exactly what the user
    sees: the plot, colour scale/legend, and any ROI box drawn on top. Works for any node with a
    window — display nodes (LinePlot, ImageViewer, WaveformViewer, ...), ROI nodes (Roi2D, Roi1D,
    RoiArch, ScatterRoi), and source nodes. A bare output feature with no window of its own (e.g.
    'Roi2D.0.Out') needs a viewer node connected to it first — use fetch_data for numbers instead.

    Prefer fetch_data(detail='normal') for numbers; use this when the shape of the data matters
    (images, peak shapes, an ROI box's position, comparing to a reference).

    Large or busy screenshots are downscaled and/or compressed to fit MCP's transport limit
    (see #226); when that happens, a second text item is returned alongside the image noting
    the resize, since axis-scale/pixel-detail judgements should account for it.

    Args:
        node_name: Node name (e.g., 'ImageViewer.0', 'Roi2D.0')
        timeout: Max seconds to wait for the window to open and produce a screenshot (default 30;
                 a window that's busy rendering a large image, or waiting for the next heartbeat,
                 can take a while)
        max_size: Max size in bytes of the returned image (default and hard cap ~700 KB, MCP's
                  own transport limit); a smaller value saves tokens

    Returns:
        JPEG image (plus a text note if it had to be resized to fit), or an error raised as a
        tool error (e.g. "apply_graph() first" if upstream nodes have unapplied changes, a
        timeout if no data is flowing, or the image still being too large even at a small size)
    """
    if max_size <= 0:
        raise ToolError("max_size must be positive")
    max_size = min(max_size, RENDER_PLOT_MAX_BYTES)

    future = _dispatch_or_tool_error(lambda: _amicli.request_screenshot(node_name))
    try:
        png = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        _qt_dispatch(lambda: _amicli.abandon_screenshot_request(future))
        # ToolError (not a bare TimeoutError): this is an anticipated failure -- a window
        # that hasn't produced a heartbeat yet, not a crash. The MCP framework logs ToolError
        # at INFO with no traceback, vs. ERROR + full traceback for anything else, so this
        # doesn't get mistaken for a real crash in AMI's log (see AGENTS.md note on this).
        raise ToolError(f"No screenshot from '{node_name}' within {timeout}s; is data flowing?")
    except Exception as e:
        # The window itself crashed rendering this node (NodeProcess.report_widget_error
        # resolves any pending screenshot request with the error instead of leaving it to time
        # out) -- also an anticipated failure, not a bug in this tool, so ToolError here too.
        # get_graph_errors()/get_messages() have the full traceback.
        raise ToolError(f"'{node_name}' failed to render: {e}")

    jpeg, note = _to_jpeg(png, max_size)
    if note:
        logger.info(f"render_plot('{node_name}'): {note}")
        return [Image(data=jpeg, format="jpeg"), note]
    return Image(data=jpeg, format="jpeg")


def _widget_request_result(node_name, future, timeout, verb):
    """Shared wait/error handling for get_plot_config/set_plot_config/set_trace_style, mirroring
    render_plot's handling of request_screenshot's future."""
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        _qt_dispatch(lambda: _amicli.abandon_widget_request(future))
        raise ToolError(f"No reply from '{node_name}' within {timeout}s; is its window open and receiving data?")
    except Exception as e:
        raise ToolError(f"Failed to {verb} '{node_name}': {e}")


@mcp.tool()
def get_plot_config(node_name: str, timeout: float = 30) -> str:
    """
    Get a plot node's configuration (title, axes, grid) and each trace's current label and
    style, from its live display window.

    Opens the window if it isn't already open (same as render_plot), and waits for its next
    live update so the reported trace list/styles reflect real state -- a brand-new plot with
    no traces yet returns an empty "traces" dict rather than erroring.

    Works on any PlotWidget-based display node: ScatterPlot, ScalarPlot, TimePlot, LinePlot,
    WaveformViewer, Histogram, ImageViewer, MultiWaveformViewer. Fails with a clear error on a
    node with no such window (e.g. ObjectViewer, a source node).

    Args:
        node_name: Node name (e.g., 'ScatterPlot.0')
        timeout: Max seconds to wait for the window to open and produce a reply (default 30)

    Returns:
        JSON with:
        "plot": current plot-level settings, e.g. {"Title": "", "Font Size": 9, "Show Grid":
            true, "X Axis": {"Label": "", "Log Scale": false, "Auto Range": true, "Min": 0.0,
            "Max": 100.0}, "Y Axis": {...}} -- exact keys depend on the node type (e.g. an
            ImageViewer has no "Auto Range"/"Min"/"Max")
        "traces": {<data name>: {"label": <current legend text>, "style": {...}}}, keyed by
            each trace's DATA NAME (e.g. "Filter.1.Out.1 vs Filter.1.Out" for a ScatterPlot, or
            just a wire name for WaveformViewer/ScalarPlot) -- NOT its current legend label,
            since that's just display text set_trace_style can change and isn't guaranteed
            unique. Use the data name with set_trace_style's `trace` argument.
        "annotations": {<id>: {"kind": "line"|"rect"|"circle", "label": <legend text>,
            "points": {...}, "style": {...}}}, keyed by each annotation's id (e.g.
            "LineEditor.0") -- see add_plot_annotation for what "points"/"style" contain for
            each kind. Use the id with update_plot_annotation/remove_plot_annotation.
    """
    future = _dispatch_or_tool_error(lambda: _amicli.get_plot_config(node_name))
    result = _widget_request_result(node_name, future, timeout, "get plot config from")
    return json.dumps(result, default=str)


@mcp.tool()
def set_plot_config(node_name: str, settings: dict, timeout: float = 30) -> str:
    """
    Set a plot node's configuration (title, axes, grid). Only the given keys are changed; call
    get_plot_config first to see the current values and the exact keys this node type accepts.

    Example: set_plot_config("ScatterPlot.0", {"Title": "Laser On/Off",
             "X Axis": {"Label": "delta_t"}, "Y Axis": {"Label": "sum(waveform2)"}})

    Opens the window if it isn't already open. Does not require apply_graph() -- this changes
    display settings, not the graph itself. CSV references and annotations on the plot are
    never touched by this call.

    Args:
        node_name: Node name (e.g., 'ScatterPlot.0')
        settings: Partial settings dict, same shape as get_plot_config's "plot" key
        timeout: Max seconds to wait for the window to open and produce a reply (default 30)

    Returns:
        JSON with the plot's full updated config (same shape as get_plot_config), or an error
        listing the valid setting names if an unknown key was given
    """
    future = _dispatch_or_tool_error(lambda: _amicli.set_plot_config(node_name, settings))
    result = _widget_request_result(node_name, future, timeout, "set plot config on")
    return json.dumps(result, default=str)


@mcp.tool()
def set_trace_style(node_name: str, trace: str, label: str = None, style: dict = None, timeout: float = 30) -> str:
    """
    Relabel and/or restyle one trace on a plot node, e.g. to tell apart a laser on/off split
    with distinct colors and legend labels.

    `trace` must be the trace's DATA NAME from get_plot_config's "traces" keys (e.g.
    "Filter.1.Out.1 vs Filter.1.Out"), not its current legend label -- the label is just
    display text this tool itself can change, and isn't guaranteed unique.

    `style` is merged into the trace's existing style (call get_plot_config first for the
    current style and valid keys for this node type -- e.g. a Histogram trace only has
    {"Brush": ...}), one level deep for grouped fields -- e.g. {"Point": {"Brush": [255, 0,
    0]}} changes only that group's Brush, leaving Size/symbol/Line alone. Colors accept an
    RGB/RGBA list or tuple, a "#rrggbb" hex string, or a pyqtgraph color name.

    Example: set_trace_style("ScatterPlot.0", "Filter.1.Out.1 vs Filter.1.Out",
             label="Laser Off", style={"Point": {"Brush": [255, 0, 0], "symbol": "o"}})

    Opens the window if it isn't already open. Does not require apply_graph().

    Args:
        node_name: Node name (e.g., 'ScatterPlot.0')
        trace: The trace's data name (see get_plot_config's "traces" keys)
        label: New legend label, or None to leave it unchanged
        style: Partial style dict to merge into the trace's current style, or None to leave it
            unchanged
        timeout: Max seconds to wait for the window to open and produce a reply (default 30)

    Returns:
        JSON with the plot's full updated config, or an error listing the plot's actual trace
        data names if `trace` didn't match one, or the valid style keys if an unknown one was
        given
    """
    future = _dispatch_or_tool_error(lambda: _amicli.set_trace_style(node_name, trace, label=label, style=style))
    result = _widget_request_result(node_name, future, timeout, "set trace style on")
    return json.dumps(result, default=str)


# Each annotation kind's two position groups, in plot coordinates -- for add_plot_annotation's
# `points` argument. "circle" has no true radius field: "Radius" is a point ON the circle's
# edge (its distance from "Center" becomes the radius), not a distance value itself.
ANNOTATION_POINT_GROUPS = {
    "line": ("From", "To"),
    "rect": ("Top Left", "Bottom Right"),
    "circle": ("Center", "Radius"),
}


@mcp.tool()
def add_plot_annotation(
    node_name: str, kind: str, points: dict = None, label: str = None, style: dict = None, timeout: float = 30
) -> str:
    """
    Add a line, rect, or circle annotation to a plot node -- e.g. a threshold line marking the
    boundary between two populations, or a box around a cluster of interest.

    `kind` is "line", "rect", or "circle". `points` gives its position, using that kind's two
    group names (each {"X": ..., "Y": ...}, in plot/data coordinates):
    - "line": {"From": {...}, "To": {...}} -- a line segment between the two points. For a
      threshold spanning the whole plot, use endpoints far outside the visible range (e.g.
      X +-1e9 for a horizontal threshold at a given Y) -- pyqtgraph clips it to the view.
    - "rect": {"Top Left": {...}, "Bottom Right": {...}}
    - "circle": {"Center": {...}, "Radius": {...}} -- "Radius" is a point ON the circle's
      edge, not a distance; its distance from "Center" becomes the radius.
    Any point omitted defaults to (0, 0) for a new annotation.

    `style` covers appearance, grouped the same way as set_trace_style: "Point" (symbol/
    Brush/Size, for the line/rect/circle's own vertices) and "Line" (color/width/style) always
    apply; "rect" and "circle" also have "Fill" ({"Fill Annotation": bool, "Brush": ...}).

    Example (laser on/off threshold + a box around the "on" cluster):
    add_plot_annotation("Histogram.0", "line", points={"From": {"X": 103400, "Y": -1e9},
                         "To": {"X": 103400, "Y": 1e9}}, label="Threshold",
                         style={"Line": {"color": [255, 255, 0], "style": "Dash"}})
    add_plot_annotation("ScatterPlot.0", "rect",
                         points={"Top Left": {"X": 0, "Y": 104200},
                                 "Bottom Right": {"X": 10, "Y": 104600}},
                         label="On cluster", style={"Fill": {"Brush": [255, 0, 0, 60]}})

    Opens the window if it isn't already open. Does not require apply_graph().

    Args:
        node_name: Node name (e.g., 'ScatterPlot.0')
        kind: "line", "rect", or "circle"
        points: Position dict using that kind's group names (see above); omitted points
            default to (0, 0)
        label: Legend text for the new annotation, or None for its id (e.g. "LineEditor.0")
        style: Partial style dict (see above); omitted fields use the editor's defaults
        timeout: Max seconds to wait for the window to open and produce a reply (default 30)

    Returns:
        JSON with the plot's full updated config (get_plot_config's shape) plus "id": the new
        annotation's id (use it with update_plot_annotation/remove_plot_annotation), or an
        error listing the valid kinds/point groups/style keys if an unknown one was given
    """
    args = {"kind": kind, "points": points, "label": label, "style": style}
    future = _dispatch_or_tool_error(lambda: _amicli.add_plot_annotation(node_name, **args))
    result = _widget_request_result(node_name, future, timeout, "add annotation to")
    return json.dumps(result, default=str)


@mcp.tool()
def update_plot_annotation(
    node_name: str,
    annotation_id: str,
    points: dict = None,
    label: str = None,
    style: dict = None,
    timeout: float = 30,
) -> str:
    """
    Change only the given points/label/style fields of an existing annotation on a plot node
    -- e.g. to move a threshold line, or recolor a box -- without needing to resend the rest.

    `annotation_id` must be one of get_plot_config's "annotations" keys (e.g. "LineEditor.0").
    See add_plot_annotation for the shape of `points`/`style` for that annotation's kind.

    Example: update_plot_annotation("Histogram.0", "LineEditor.0",
             points={"From": {"X": 103600}, "To": {"X": 103600}})

    Opens the window if it isn't already open. Does not require apply_graph().

    Args:
        node_name: Node name (e.g., 'ScatterPlot.0')
        annotation_id: The annotation's id (see get_plot_config's "annotations" keys)
        points: Partial position dict to apply; omitted fields keep their current value
        label: New legend text, or None to leave it unchanged
        style: Partial style dict to apply; omitted fields keep their current value
        timeout: Max seconds to wait for the window to open and produce a reply (default 30)

    Returns:
        JSON with the plot's full updated config, or an error listing the plot's actual
        annotation ids if annotation_id didn't match one, or the valid point/style keys for
        that kind if an unknown one was given
    """
    args = {"annotation_id": annotation_id, "points": points, "label": label, "style": style}
    future = _dispatch_or_tool_error(lambda: _amicli.update_plot_annotation(node_name, **args))
    result = _widget_request_result(node_name, future, timeout, "update annotation on")
    return json.dumps(result, default=str)


@mcp.tool()
def remove_plot_annotation(node_name: str, annotation_id: str, timeout: float = 30) -> str:
    """
    Remove an annotation from a plot node.

    `annotation_id` must be one of get_plot_config's "annotations" keys (e.g. "LineEditor.0").

    Opens the window if it isn't already open. Does not require apply_graph().

    Args:
        node_name: Node name (e.g., 'ScatterPlot.0')
        annotation_id: The annotation's id (see get_plot_config's "annotations" keys)
        timeout: Max seconds to wait for the window to open and produce a reply (default 30)

    Returns:
        JSON with the plot's full updated config, or an error listing the plot's actual
        annotation ids if annotation_id didn't match one
    """
    future = _dispatch_or_tool_error(lambda: _amicli.remove_plot_annotation(node_name, annotation_id))
    result = _widget_request_result(node_name, future, timeout, "remove annotation from")
    return json.dumps(result, default=str)


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


class _TcpBearerTokenVerifier(TokenVerifier):
    """Checks inbound bearer tokens against the token generated for one TCP server launch.

    Only used in TCP mode (see McpServerThread.__init__/_set_auth below); UDS mode has no auth
    at all, unchanged from before this token was introduced.
    """

    def __init__(self, token):
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self._token):
            return None
        return AccessToken(token=token, client_id="ami-mcp-connect", scopes=[])


def _set_auth(token):
    """Configure the module-level `mcp` singleton to require this bearer token (TCP mode only).

    AuthSettings/token_verifier are only read at request time -- MCPServer.streamable_http_app
    reads self.settings.auth and self._token_verifier fresh on every call, rather than freezing
    them at construction (confirmed by inspecting the installed mcp library's source) -- so this
    mutates those attributes directly on the existing singleton instead of recreating MCPServer
    and re-registering every @mcp.tool()-decorated function in this file.
    """
    mcp.settings.auth = AuthSettings(
        # issuer_url/resource_server_url are required by AuthSettings' own validation but never
        # actually traversed: ami-mcp-connect always sends the bearer token directly and never
        # performs OAuth discovery against these URLs, so they are unused placeholders.
        issuer_url="http://localhost/unused-oauth-issuer",
        resource_server_url="http://localhost/unused-oauth-resource",
    )
    mcp._token_verifier = _TcpBearerTokenVerifier(token)


# ──────────────────────────────────────────────────────────────────────
# SERVER THREAD
# ──────────────────────────────────────────────────────────────────────


class McpServerThread(threading.Thread):
    """Runs MCP HTTP server in a background daemon thread."""

    def __init__(self, amicli, qt_dispatch_fn, host="0.0.0.0", uds=None, hutch=""):
        """
        Args:
            amicli: AmiCli instance for graph manipulation
            qt_dispatch_fn: QtDispatcher.dispatch function
            host: Address to bind the TCP listener on (default all interfaces; see module docs
                  on why a bearer token is always required rather than restricting to loopback)
            uds: Unix socket path to serve on instead of a TCP port (port is then None)
            hutch: Active hutch name, published in the connection file so a harness can report
                   it (see ami.mcp_connect); empty string if none configured
        """
        super().__init__(daemon=True, name="ami-mcp-server")
        global _amicli, _qt_dispatch
        _amicli = amicli
        _qt_dispatch = qt_dispatch_fn
        self.host = host
        self.uds = uds
        self.hutch = hutch
        self.port = None if uds else _find_free_port()
        self.token = None

        # Publish the connection file so an independently-launched harness (via
        # ami-mcp-connect) can find this server. Not meaningful in UDS mode: there's no
        # TCP port to describe, and that mode is for a TLS front such as ghostunnel, not a
        # harness reaching the socket directly (see _run_uds).
        if not self.uds:
            # We bind self.host ("0.0.0.0" by default) but must advertise an address a remote
            # harness can actually dial back into, hence socket.getfqdn() here rather than
            # self.host. Every TCP launch requires a bearer token -- including local/loopback
            # connections -- since binding all interfaces means a loopback-only exemption would
            # no longer mean "only this machine", and any user on a shared login node could
            # otherwise reach another user's port.
            self.token = secrets.token_urlsafe(32)
            _set_auth(self.token)
            _write_connection_file(socket.getfqdn(), self.port, hutch=self.hutch, token=self.token)
            atexit.register(_remove_connection_file_if_ours)

    def run(self):
        """Run MCP server (blocks in this thread)."""
        # Suppress noisy MCP library request logging
        logging.getLogger("mcp").setLevel(logging.WARNING)

        try:
            if self.uds:
                self._run_uds()
            else:
                logger.info(f"AMI MCP server on http://{self.host}:{self.port}/mcp")
                mcp.run(transport="streamable-http", host=self.host, port=self.port)
        except Exception as e:
            logger.exception(f"MCP server error: {e}")

    def _run_uds(self):
        """Serve on a Unix socket only this account can open, for a TLS front such as ghostunnel."""
        # Requests forwarded by agentgateway carry its target's name as Host, which the DNS
        # rebinding check refuses with 421. That check protects loopback ports from web pages in
        # a local browser, and a browser cannot open a Unix socket.
        app = mcp.streamable_http_app(
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
        )

        _remove_stale_socket(self.uds)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.uds)
        # uvicorn's own uds option makes the socket writable by every account; restrict it
        # before uvicorn calls listen(), so no other account can ever connect.
        os.chmod(self.uds, 0o600)
        logger.info(f"AMI MCP server on unix:{self.uds} at /mcp")
        uvicorn.Server(uvicorn.Config(app, log_level=mcp.settings.log_level.lower())).run(sockets=[sock])
