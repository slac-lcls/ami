"""The MCP server on a Unix socket (AMI_MCP_UDS), as a TLS front such as ghostunnel reaches it.

Each server runs in its own subprocess, because the server thread cannot be stopped and conftest
keeps it out of the test process.
"""

import os
import socket
import stat
import subprocess
import sys
import tempfile
import time

import pytest

pytest.importorskip("mcp.server.mcpserver")
httpx = pytest.importorskip("httpx")

SERVE = """
import sys
from ami.mcp_server import McpServerThread
t = McpServerThread(amicli=None, qt_dispatch_fn=None, uds=sys.argv[1])
t.start()
t.join()
"""

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def sock_dir():
    # A short path: a Unix socket path must fit in 108 bytes, and pytest's tmp_path may not.
    with tempfile.TemporaryDirectory(prefix="ami-mcp-") as d:
        yield d


def start_server(path):
    env = dict(os.environ)
    env.pop("AMI_DISABLE_MCP", None)
    return subprocess.Popen([sys.executable, "-c", SERVE, path], env=env, stderr=subprocess.PIPE)


def wait_listening(proc, path, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"server exited: {proc.stderr.read().decode()}")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(path)
            return
        except OSError:
            time.sleep(0.1)
    pytest.fail(f"no server on {path} after {timeout} s")


@pytest.fixture
def server(sock_dir):
    path = os.path.join(sock_dir, "mcp.sock")
    proc = start_server(path)
    wait_listening(proc, path)
    yield path
    proc.kill()
    proc.wait()


def post_initialize(path, host):
    transport = httpx.HTTPTransport(uds=path)
    with httpx.Client(transport=transport, base_url=f"http://{host}") as client:
        return client.post("/mcp", json=INITIALIZE, headers=HEADERS)


def test_accepts_gateway_host_header(server):
    # agentgateway sends its target's name as Host; on a loopback port the DNS rebinding check
    # would answer 421 Invalid Host header.
    response = post_initialize(server, "rmcp-ami-mfx.lcls.svc.cluster.local")
    assert response.status_code == 200, response.text
    assert '"serverInfo"' in response.text


def test_socket_is_private_to_its_account(server):
    assert stat.S_IMODE(os.stat(server).st_mode) == 0o600


def test_replaces_stale_socket(sock_dir):
    path = os.path.join(sock_dir, "mcp.sock")
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(path)
    stale.close()  # leaves the socket file with nothing listening, as after a crash
    proc = start_server(path)
    try:
        wait_listening(proc, path)
        assert post_initialize(path, "localhost").status_code == 200
    finally:
        proc.kill()
        proc.wait()


def test_refuses_socket_another_server_holds(server):
    proc = start_server(server)
    try:
        proc.wait(timeout=30)  # the server thread ends, so the process exits
        assert "another server is listening" in proc.stderr.read().decode()
    finally:
        proc.kill()
    assert post_initialize(server, "localhost").status_code == 200


def test_never_deletes_a_regular_file(sock_dir):
    path = os.path.join(sock_dir, "mcp.sock")
    with open(path, "w") as f:
        f.write("keep")
    proc = start_server(path)
    proc.wait(timeout=30)
    assert "Address already in use" in proc.stderr.read().decode()
    with open(path) as f:
        assert f.read() == "keep"
