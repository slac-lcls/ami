"""McpServerThread's connection file: written in TCP mode, skipped in UDS mode, and removed on
clean exit only by the process that owns it.

Only _write_connection_file/_remove_connection_file_if_ours are unit tested directly here; a
real McpServerThread's TCP-mode startup is covered end-to-end in
test_mcp_connect.py::test_connection_file_matches_running_server, and its UDS-mode startup
(which must NOT write this file) in test_mcp_uds.py.
"""

import json
import os
import stat

import pytest

pytest.importorskip("mcp.server.mcpserver")

from ami import mcp_server  # noqa: E402


@pytest.fixture
def connection_file(tmp_path, monkeypatch):
    path = str(tmp_path / "config" / "ami" / "mcp-server.json")
    monkeypatch.setattr(mcp_server, "CONNECTION_FILE", path)
    return path


def test_write_creates_expected_shape(connection_file):
    mcp_server._write_connection_file("127.0.0.1", 9142)
    with open(connection_file) as f:
        data = json.load(f)
    assert data["host"] == "127.0.0.1"
    assert data["port"] == 9142
    assert data["pid"] == os.getpid()
    assert "started_at" in data


def test_write_is_0600(connection_file):
    mcp_server._write_connection_file("127.0.0.1", 9142)
    mode = stat.S_IMODE(os.stat(connection_file).st_mode)
    assert mode == 0o600


def test_write_creates_parent_directory(connection_file):
    assert not os.path.exists(os.path.dirname(connection_file))
    mcp_server._write_connection_file("127.0.0.1", 9142)
    assert os.path.isdir(os.path.dirname(connection_file))


def test_second_write_overwrites_first(connection_file):
    mcp_server._write_connection_file("127.0.0.1", 9142)
    mcp_server._write_connection_file("127.0.0.1", 9999)
    with open(connection_file) as f:
        data = json.load(f)
    assert data["port"] == 9999


def test_remove_if_ours_deletes_matching_pid(connection_file):
    mcp_server._write_connection_file("127.0.0.1", 9142)
    mcp_server._remove_connection_file_if_ours()
    assert not os.path.exists(connection_file)


def test_remove_if_ours_leaves_a_later_instance_alone(connection_file):
    # Simulate: this process wrote the file, a second (later) instance overwrote it with a
    # different pid, then this process's shutdown handler runs -- it must not delete the
    # second instance's entry.
    mcp_server._write_connection_file("127.0.0.1", 9142)
    with open(connection_file) as f:
        data = json.load(f)
    data["pid"] = os.getpid() + 1  # pretend a different process wrote this
    with open(connection_file, "w") as f:
        json.dump(data, f)

    mcp_server._remove_connection_file_if_ours()

    assert os.path.exists(connection_file)
    with open(connection_file) as f:
        assert json.load(f)["pid"] == os.getpid() + 1


def test_remove_if_ours_on_missing_file_does_not_raise(connection_file):
    mcp_server._remove_connection_file_if_ours()  # file was never written; must be a no-op
