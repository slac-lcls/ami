"""The Agent button's handlers exist whenever MCP is available, with or without qtconsole."""

import subprocess
import sys

import pytest

pytest.importorskip("mcp.server.mcpserver")

# Run in a fresh interpreter, since blocking qtconsole only works before Flowchart is first imported.
CHECK = """
import sys
sys.modules["qtconsole"] = None  # makes "import qtconsole..." raise ImportError
import ami.client.flowchart  # noqa: F401  (importing Flowchart first is circular)
import ami.flowchart.Flowchart as fc
assert not fc.HAS_QTCONSOLE and fc.HAS_MCP, (fc.HAS_QTCONSOLE, fc.HAS_MCP)
missing = [m for m in ("agentClicked", "_cleanup_agent_proc") if not hasattr(fc.FlowchartCtrlWidget, m)]
assert not missing, missing
"""


def test_agent_handlers_without_qtconsole():
    result = subprocess.run([sys.executable, "-c", CHECK], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
