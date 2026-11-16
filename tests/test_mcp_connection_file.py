"""McpServerThread's connection file: written in TCP mode, skipped in UDS mode, and removed on
clean exit only by the process that owns it.

Only _write_connection_file/_remove_connection_file_if_ours are unit tested directly here; a
real McpServerThread's TCP-mode startup is covered end-to-end in
test_mcp_connect.py::test_connection_file_matches_running_server, and its UDS-mode startup
(which must NOT write this file) in test_mcp_uds.py.
"""

import json
import os
import socket
import stat

import pytest

pytest.importorskip("mcp.server.mcpserver")
anyio = pytest.importorskip("anyio")

from ami import mcp_server  # noqa: E402


@pytest.fixture
def connection_file(tmp_path, monkeypatch):
    path = str(tmp_path / "config" / "ami" / "mcp-server.json")
    monkeypatch.setattr(mcp_server, "CONNECTION_FILE", path)
    return path


def test_write_creates_expected_shape(connection_file):
    mcp_server._write_connection_file("some.host.example.com", 9142, hutch="rix", token="abc123")
    with open(connection_file) as f:
        data = json.load(f)
    assert data["host"] == "some.host.example.com"
    assert data["port"] == 9142
    assert data["pid"] == os.getpid()
    assert "started_at" in data
    assert data["hutch"] == "rix"
    assert data["token"] == "abc123"


def test_write_defaults_hutch_and_token_to_empty_string(connection_file):
    mcp_server._write_connection_file("127.0.0.1", 9142)
    with open(connection_file) as f:
        data = json.load(f)
    assert data["hutch"] == ""
    assert data["token"] == ""


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


# ──────────────────────────────────────────────────────────────────────
# _find_free_port: probes the same address McpServerThread actually binds to
# ──────────────────────────────────────────────────────────────────────


def test_find_free_port_returns_a_port_bindable_on_all_interfaces():
    port = mcp_server._find_free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", port))  # must not raise -- this is the address McpServerThread binds


# ──────────────────────────────────────────────────────────────────────
# _set_auth / _TcpBearerTokenVerifier: the TCP-mode bearer token check
# ──────────────────────────────────────────────────────────────────────


def test_token_verifier_accepts_matching_token():
    verifier = mcp_server._TcpBearerTokenVerifier("correct-token")
    result = anyio.run(verifier.verify_token, "correct-token")
    assert result is not None
    assert result.token == "correct-token"


def test_token_verifier_rejects_wrong_token():
    verifier = mcp_server._TcpBearerTokenVerifier("correct-token")
    assert anyio.run(verifier.verify_token, "wrong-token") is None


def test_token_verifier_rejects_empty_token():
    verifier = mcp_server._TcpBearerTokenVerifier("correct-token")
    assert anyio.run(verifier.verify_token, "") is None


def test_set_auth_wires_token_verifier_onto_module_singleton():
    mcp_server._set_auth("fresh-token")
    assert mcp_server.mcp.settings.auth is not None
    assert isinstance(mcp_server.mcp._token_verifier, mcp_server._TcpBearerTokenVerifier)
    assert mcp_server.mcp._token_verifier._token == "fresh-token"
