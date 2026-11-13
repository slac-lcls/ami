"""ami-mcp-connect: skill-link install, connection-file discovery, the instructions-note
relay logic, and an end-to-end bridge against a real McpServerThread.

The end-to-end test runs AMI's MCP server in its own subprocess, like test_mcp_uds.py, because
the server thread cannot be stopped and conftest keeps it out of the test process.
"""

import json
import os
import selectors
import subprocess
import sys
import time

import pytest

pytest.importorskip("mcp.server.mcpserver")
anyio = pytest.importorskip("anyio")

from ami import mcp_connect  # noqa: E402

# ──────────────────────────────────────────────────────────────────────
# install_skill_links
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def skill_dirs(tmp_path, monkeypatch):
    """Point SKILL_TARGET_DIRS at three fresh tmp_path subdirectories."""
    dirs = [str(tmp_path / f"target{i}") for i in range(3)]
    monkeypatch.setattr(mcp_connect, "SKILL_TARGET_DIRS", tuple(dirs))
    return dirs


def _link_path(target_dir, skill_name="ami-graph-builder"):
    return os.path.join(target_dir, skill_name)


def _expected_target(skill_name="ami-graph-builder"):
    return os.path.join(mcp_connect._package_skills_dir(), skill_name)


def test_creates_missing_links(skill_dirs):
    changed = mcp_connect.install_skill_links()
    assert changed is True
    for d in skill_dirs:
        for name in mcp_connect.SKILL_NAMES:
            link = _link_path(d, name)
            assert os.path.islink(link)
            assert os.readlink(link) == _expected_target(name)


def test_already_correct_is_a_noop(skill_dirs):
    mcp_connect.install_skill_links()
    link = _link_path(skill_dirs[0])
    before = os.lstat(link)
    changed = mcp_connect.install_skill_links()
    assert changed is False
    after = os.lstat(link)
    assert before.st_ino == after.st_ino  # same link, not replaced


def test_replaces_stale_link(skill_dirs):
    d = skill_dirs[0]
    os.makedirs(d, exist_ok=True)
    link = _link_path(d)
    os.symlink("/nonexistent/somewhere/else", link)
    changed = mcp_connect.install_skill_links()
    assert changed is True
    assert os.readlink(link) == _expected_target()


def test_replaces_dangling_link(skill_dirs):
    d = skill_dirs[0]
    os.makedirs(d, exist_ok=True)
    link = _link_path(d)
    os.symlink("/nonexistent/also/gone", link)
    assert not os.path.exists(link)  # dangling: lexists True, exists False
    changed = mcp_connect.install_skill_links()
    assert changed is True
    assert os.readlink(link) == _expected_target()


def test_real_directory_is_left_alone(skill_dirs, caplog):
    d = skill_dirs[0]
    link = _link_path(d)
    os.makedirs(link)  # a real directory, not a symlink, occupying the expected path
    changed = mcp_connect.install_skill_links()
    assert not os.path.islink(link)
    assert os.path.isdir(link)
    assert "not a symlink" in caplog.text
    # the other two targets are unaffected by the first one being blocked
    assert changed is True
    assert os.path.islink(_link_path(skill_dirs[1]))


def test_unwritable_target_warns_but_others_still_installed(skill_dirs, caplog):
    blocked_dir = skill_dirs[0]
    os.makedirs(blocked_dir, mode=0o500)  # read+execute only: can list it, can't create inside it
    try:
        changed = mcp_connect.install_skill_links()
    finally:
        os.chmod(blocked_dir, 0o700)  # restore so tmp_path cleanup can remove it
    assert changed is True
    assert "Could not install skill link" in caplog.text
    assert not os.path.islink(_link_path(blocked_dir))
    assert os.path.islink(_link_path(skill_dirs[1]))


# ──────────────────────────────────────────────────────────────────────
# find_ami_server
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def connection_file(tmp_path, monkeypatch):
    path = str(tmp_path / "mcp-server.json")
    monkeypatch.setattr(mcp_connect, "CONNECTION_FILE", path)
    return path


def test_find_ami_server_missing_file(connection_file):
    assert mcp_connect.find_ami_server() is None


def test_find_ami_server_malformed_json(connection_file):
    with open(connection_file, "w") as f:
        f.write("{not json")
    assert mcp_connect.find_ami_server() is None


def test_find_ami_server_dead_pid(connection_file):
    # pid 0 is never a real process id to kill(2) target-wise on Linux for this purpose; use an
    # arbitrarily large pid instead, which is reliably not a running process.
    with open(connection_file, "w") as f:
        json.dump({"host": "127.0.0.1", "port": 9999, "pid": 2**30}, f)
    assert mcp_connect.find_ami_server() is None


def test_find_ami_server_live_pid(connection_file):
    payload = {"host": "127.0.0.1", "port": 9142, "pid": os.getpid(), "started_at": "x"}
    with open(connection_file, "w") as f:
        json.dump(payload, f)
    assert mcp_connect.find_ami_server() == payload


# ──────────────────────────────────────────────────────────────────────
# Instructions-note relay logic
# ──────────────────────────────────────────────────────────────────────


class _FakeMessage:
    def __init__(self, id=None, method=None, result=None):
        self.id = id
        if method is not None:
            self.method = method
        if result is not None:
            self.result = result


class _FakeItem:
    def __init__(self, message):
        self.message = message


async def _run_pumps_and_collect(harness_items, ami_items, skills_changed):
    to_ami_send, to_ami_recv = anyio.create_memory_object_stream(max_buffer_size=10)
    to_harness_send, to_harness_recv = anyio.create_memory_object_stream(max_buffer_size=10)
    harness_read_send, harness_read_recv = anyio.create_memory_object_stream(max_buffer_size=10)
    ami_read_send, ami_read_recv = anyio.create_memory_object_stream(max_buffer_size=10)

    for item in harness_items:
        await harness_read_send.send(item)
    harness_read_send.close()
    for item in ami_items:
        await ami_read_send.send(item)
    ami_read_send.close()

    pending_initialize_ids = set()
    pending_request_ids = set()

    # Run in order, not concurrently: _pump_to_ami no longer closes its own output stream
    # (bridge() closes it only after a grace period -- see SHUTDOWN_GRACE_SECONDS), and running
    # both at once would make these tests depend on scheduling order to see pending_request_ids
    # populated before _pump_to_harness checks it.
    await mcp_connect._pump_to_ami(harness_read_recv, to_ami_send, pending_initialize_ids, pending_request_ids)
    to_ami_send.close()
    await mcp_connect._pump_to_harness(
        ami_read_recv, to_harness_send, pending_initialize_ids, pending_request_ids, skills_changed
    )  # closes to_harness_send itself, same as the real bridge

    collected_to_ami = [item async for item in to_ami_recv]
    collected_to_harness = [item async for item in to_harness_recv]
    return collected_to_harness, collected_to_ami


def test_instructions_note_added_when_skills_changed():
    init_request = _FakeItem(_FakeMessage(id=1, method="initialize"))
    init_reply = _FakeItem(_FakeMessage(id=1, result={"serverInfo": {}}))

    to_harness, _ = anyio.run(_run_pumps_and_collect, [init_request], [init_reply], True)

    assert len(to_harness) == 1
    assert mcp_connect.SKILLS_UPDATED_NOTE in to_harness[0].message.result["instructions"]


def test_instructions_note_appended_not_overwritten():
    init_request = _FakeItem(_FakeMessage(id=1, method="initialize"))
    init_reply = _FakeItem(_FakeMessage(id=1, result={"instructions": "existing text"}))

    to_harness, _ = anyio.run(_run_pumps_and_collect, [init_request], [init_reply], True)

    result = to_harness[0].message.result["instructions"]
    assert "existing text" in result
    assert mcp_connect.SKILLS_UPDATED_NOTE in result


def test_no_note_when_skills_unchanged():
    init_request = _FakeItem(_FakeMessage(id=1, method="initialize"))
    init_reply = _FakeItem(_FakeMessage(id=1, result={"serverInfo": {}}))

    to_harness, _ = anyio.run(_run_pumps_and_collect, [init_request], [init_reply], False)

    assert "instructions" not in to_harness[0].message.result


def test_unrelated_replies_pass_through_unchanged():
    other_request = _FakeItem(_FakeMessage(id=2, method="tools/list"))
    other_reply = _FakeItem(_FakeMessage(id=2, result={"tools": ["create_node"]}))

    to_harness, _ = anyio.run(_run_pumps_and_collect, [other_request], [other_reply], True)

    assert to_harness[0].message.result == {"tools": ["create_node"]}


async def _pump_one_item_each_way(harness_item, ami_item):
    """Run both pumps once each, in order, and return the shared pending_request_ids set as it
    stands after both -- used to check what bridge()'s grace-period wait would actually see.
    """
    to_ami_send, to_ami_recv = anyio.create_memory_object_stream(max_buffer_size=1)
    to_harness_send, to_harness_recv = anyio.create_memory_object_stream(max_buffer_size=1)
    harness_read_send, harness_read_recv = anyio.create_memory_object_stream(max_buffer_size=1)
    ami_read_send, ami_read_recv = anyio.create_memory_object_stream(max_buffer_size=1)

    await harness_read_send.send(harness_item)
    harness_read_send.close()
    pending_initialize_ids = set()
    pending_request_ids = set()
    await mcp_connect._pump_to_ami(harness_read_recv, to_ami_send, pending_initialize_ids, pending_request_ids)
    to_ami_send.close()

    if ami_item is not None:
        await ami_read_send.send(ami_item)
    ami_read_send.close()
    await mcp_connect._pump_to_harness(
        ami_read_recv, to_harness_send, pending_initialize_ids, pending_request_ids, False
    )
    return pending_request_ids


def test_pending_request_ids_tracks_requests_not_notifications():
    request = _FakeItem(_FakeMessage(id=5, method="tools/list"))
    pending = anyio.run(_pump_one_item_each_way, request, None)
    assert pending == {5}  # no reply seen yet -- still pending


def test_pending_request_ids_cleared_by_matching_reply():
    request = _FakeItem(_FakeMessage(id=5, method="tools/list"))
    reply = _FakeItem(_FakeMessage(id=5, result={"tools": []}))
    pending = anyio.run(_pump_one_item_each_way, request, reply)
    assert pending == set()


def test_pending_request_ids_ignores_notifications():
    # A notification has no id at all, per JSON-RPC -- must never be waited on.
    notification = _FakeItem(_FakeMessage(method="notifications/initialized"))
    pending = anyio.run(_pump_one_item_each_way, notification, None)
    assert pending == set()


# ──────────────────────────────────────────────────────────────────────
# End-to-end: a real McpServerThread, bridged to by a real ami-mcp-connect subprocess
# ──────────────────────────────────────────────────────────────────────

SERVE = """
import sys
from ami.mcp_server import McpServerThread
t = McpServerThread(amicli=None, qt_dispatch_fn=None)
sys.stdout.write(str(t.port) + "\\n")
sys.stdout.flush()
t.start()
t.join()
"""

INITIALIZE = (
    json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    )
    + "\n"
)
INITIALIZED_NOTIFICATION = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
TOOLS_LIST = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"


def _readline_with_timeout(stream, timeout):
    """readline(), but fail the test instead of hanging the suite if nothing arrives in time."""
    sel = selectors.DefaultSelector()
    sel.register(stream, selectors.EVENT_READ)
    try:
        if not sel.select(timeout):
            pytest.fail(f"no line from the bridge within {timeout}s")
    finally:
        sel.close()
    line = stream.readline()
    if not line:
        pytest.fail("bridge closed its stdout before sending a reply")
    return line


@pytest.fixture
def ami_home(tmp_path):
    """A private HOME so this test never touches the real connection file or skill links."""
    home = tmp_path / "home"
    home.mkdir()
    return str(home)


@pytest.fixture
def running_ami_server(ami_home):
    env = dict(os.environ)
    env.pop("AMI_DISABLE_MCP", None)
    env["HOME"] = ami_home
    env["COLUMNS"] = "1000"
    proc = subprocess.Popen(
        [sys.executable, "-c", SERVE],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    port_line = proc.stdout.readline()
    if not port_line:
        proc.kill()
        pytest.fail(f"server never printed its port: {proc.stderr.read()}")
    port = int(port_line.strip())

    conn_file = os.path.join(ami_home, ".config", "ami", "mcp-server.json")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if os.path.exists(conn_file):
            break
        if proc.poll() is not None:
            pytest.fail(f"server exited before writing its connection file: {proc.stderr.read()}")
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("connection file never appeared")

    yield port, conn_file
    proc.kill()
    proc.wait()


def test_connection_file_matches_running_server(running_ami_server):
    port, conn_file = running_ami_server
    with open(conn_file) as f:
        data = json.load(f)
    assert data["port"] == port
    assert data["host"] == "127.0.0.1"


def _spawn_bridge(ami_home):
    env = dict(os.environ)
    env["HOME"] = ami_home
    return subprocess.Popen(
        [sys.executable, "-m", "ami.mcp_connect"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,  # line-buffered: each write()+flush() below must reach the child promptly
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


def test_bridge_relays_real_tool_list(running_ami_server, ami_home):
    proc = _spawn_bridge(ami_home)
    try:
        proc.stdin.write(INITIALIZE)
        proc.stdin.flush()
        init_reply = json.loads(_readline_with_timeout(proc.stdout, 15))
        assert init_reply["id"] == 1
        # this run installed the skill links (fresh ami_home), so the note must be present
        assert mcp_connect.SKILLS_UPDATED_NOTE in init_reply["result"].get("instructions", "")

        proc.stdin.write(INITIALIZED_NOTIFICATION)
        proc.stdin.write(TOOLS_LIST)
        proc.stdin.flush()
        tools_reply = json.loads(_readline_with_timeout(proc.stdout, 15))
        assert tools_reply["id"] == 2
        tool_names = {t["name"] for t in tools_reply["result"]["tools"]}
        assert "create_node" in tool_names

        proc.stdin.close()
        try:
            proc.wait(timeout=mcp_connect.SHUTDOWN_GRACE_SECONDS + 10)
        except subprocess.TimeoutExpired:
            pytest.fail("ami-mcp-connect did not exit after the harness closed stdin")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    # the skill links should have been installed under the private HOME, not the real one
    assert os.path.islink(os.path.join(ami_home, ".claude", "skills", "ami-graph-builder"))


def test_pending_reply_delivered_during_grace_period(running_ami_server, ami_home):
    """Closing stdin before a request's reply has arrived must not drop that reply.

    _run_to_ami's shutdown handler should keep _run_to_harness alive for up to
    SHUTDOWN_GRACE_SECONDS specifically so this can still be delivered.
    """
    proc = _spawn_bridge(ami_home)
    try:
        proc.stdin.write(INITIALIZE)
        proc.stdin.flush()
        _readline_with_timeout(proc.stdout, 15)  # initialize reply; not under test here

        proc.stdin.write(INITIALIZED_NOTIFICATION)
        proc.stdin.write(TOOLS_LIST)
        proc.stdin.flush()
        proc.stdin.close()  # close immediately -- before tools/list's reply can have arrived

        tools_reply = json.loads(_readline_with_timeout(proc.stdout, mcp_connect.SHUTDOWN_GRACE_SECONDS + 10))
        assert tools_reply["id"] == 2
        assert "create_node" in {t["name"] for t in tools_reply["result"]["tools"]}

        try:
            proc.wait(timeout=mcp_connect.SHUTDOWN_GRACE_SECONDS + 10)
        except subprocess.TimeoutExpired:
            pytest.fail("ami-mcp-connect did not exit after delivering the pending reply")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_bridge_reports_no_server_running(tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(home)
    proc = subprocess.run(
        [sys.executable, "-m", "ami.mcp_connect"],
        input="",
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert proc.returncode != 0
    assert "no running AMI instance found" in proc.stderr
    assert proc.stdout == ""
