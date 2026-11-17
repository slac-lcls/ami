"""ami-mcp-connect: bridges a harness's MCP stdio transport to AMI's live MCP server.

Spawned by the harness itself -- e.g. opencode's ``type: "local"`` MCP servers, or Claude
Code's ``mcpServers`` entries with a bare ``command`` -- never by AMI. AMI only ever runs its
own MCP server and publishes where to find it (see ``ami.mcp_server.CONNECTION_FILE``); this
is the piece an independently-launched harness spawns to reach it. See
``.opencode/plans/decoupled-agent-harness/`` for the full design and rationale.

On every invocation it also makes sure the two bundled AMI skills are symlinked into the
directories common harnesses search for skills, so they stay in sync with whichever ``ami``
this script is installed alongside.
"""

import json
import logging
import os
import socket
import sys

import anyio
import httpx
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

CONNECTION_FILE = os.path.expanduser("~/.config/ami/mcp-server.json")

SKILL_NAMES = ("ami-graph-builder", "ami-performance-monitor")

# Directories common harnesses already search for skills. ~/.claude/skills is Claude Code's own
# personal location and one of opencode V2's documented compatibility paths; ~/.config/opencode
# /skills is opencode V2's own global path; ~/.opencode/skills covers opencode V1, which (per
# manual testing during planning) reads skills from there instead -- not from any path in V2's
# documented discovery list. ~/.claude/skills is kept even when CLAUDE_CONFIG_DIR (below) is set,
# since opencode still reads it as a compatibility path regardless of that variable.
SKILL_TARGET_DIRS = (
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.config/opencode/skills"),
    os.path.expanduser("~/.opencode/skills"),
)

SKILLS_UPDATED_NOTE = (
    "The AMI skills (ami-graph-builder, ami-performance-monitor) were just installed or "
    "updated by ami-mcp-connect. If they are not in your available skills, tell the user to "
    "restart this harness session so they load. AMI's MCP tools work either way."
)


def _hutch_note(hutch):
    """Build the "AMI hutch: ..." line appended to the initialize reply's instructions.

    Lets the ami-performance-monitor skill's Step 0 use this value directly instead of
    querying Grafana to discover it (see that skill's SKILL.md).
    """
    if hutch:
        return f"AMI hutch: {hutch}"
    return "AMI hutch: none configured — no active-hutch Grafana metrics to check"


def _package_skills_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")


def _skill_target_dirs():
    """SKILL_TARGET_DIRS, plus $CLAUDE_CONFIG_DIR/skills when CLAUDE_CONFIG_DIR is set.

    When CLAUDE_CONFIG_DIR is set, Claude Code reads personal skills from
    $CLAUDE_CONFIG_DIR/skills instead of ~/.claude/skills -- e.g. SLAC's claude-lcls launcher
    sets CLAUDE_CONFIG_DIR=~/.claude-lcls, so without this, claude-lcls users never see AMI's
    skills no matter how many times they restart (see issue #228). Read at call time rather
    than module import time, so tests can monkeypatch the environment.

    Returns:
        SKILL_TARGET_DIRS with $CLAUDE_CONFIG_DIR/skills appended when applicable, duplicates
        (by normalized path) removed while preserving order.
    """
    dirs = list(SKILL_TARGET_DIRS)
    claude_config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if claude_config_dir:
        dirs.append(os.path.join(os.path.expanduser(claude_config_dir), "skills"))
    seen = set()
    unique = []
    for d in dirs:
        key = os.path.normpath(d)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def install_skill_links():
    """Symlink this package's bundled skills into the directories common harnesses search.

    For each (target directory, skill) pair: creates the link if missing, replaces it if it
    points somewhere else (or nowhere), and leaves it alone -- with a warning -- if something
    that is not a symlink already occupies that path. A missing or unwritable target directory
    is also just a warning; one failing target never stops the others from being attempted.

    Returns:
        True if any link was created or replaced, else False.
    """
    pkg_skills_dir = _package_skills_dir()
    changed = False
    for target_dir in _skill_target_dirs():
        for skill_name in SKILL_NAMES:
            expected_target = os.path.join(pkg_skills_dir, skill_name)
            if not os.path.isdir(expected_target):
                continue  # this ami install doesn't ship this skill; nothing to link
            link_path = os.path.join(target_dir, skill_name)
            try:
                if os.path.islink(link_path):
                    if os.readlink(link_path) == expected_target:
                        continue  # already correct, nothing to do
                elif os.path.exists(link_path):
                    logger.warning(
                        f"{link_path} exists and is not a symlink; leaving it alone "
                        f"(expected a link to {expected_target})"
                    )
                    continue
                os.makedirs(target_dir, exist_ok=True)
                tmp_link = f"{link_path}.tmp{os.getpid()}"
                if os.path.lexists(tmp_link):
                    os.remove(tmp_link)
                os.symlink(expected_target, tmp_link)
                os.replace(tmp_link, link_path)  # atomic: no window with a missing/broken link
                changed = True
            except OSError:
                logger.warning(f"Could not install skill link {link_path}", exc_info=True)
    return changed


def find_ami_server():
    """Read the connection file ami-local writes, with a liveness pre-check where that's possible.

    This is a fast pre-check, not the authoritative test -- a pid can be reused by an unrelated
    process after a crash, which this can't detect. The actual HTTP connection attempt in
    bridge() is what really decides whether AMI is reachable.

    The pid-liveness check only means anything when the file names a process on this machine:
    os.kill(pid, 0) can't tell us anything about a pid on a different host. So it's skipped
    (not treated as failure) whenever the file's host isn't this machine -- e.g. AMI running on
    a SLURM batch node, reached by hostname from a login node. "This machine" also accepts
    127.0.0.1/localhost for connection files written before this check existed.

    Returns:
        The parsed connection dict ({"host", "port", "pid", "started_at", "hutch", "token"}),
        or None if the file is missing, malformed, or (same-machine only) names a pid that is
        no longer running.
    """
    try:
        with open(CONNECTION_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    host = data.get("host")
    same_machine = host in (None, "127.0.0.1", "localhost", socket.getfqdn())
    pid = data.get("pid")
    if same_machine and pid is not None:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return None  # stale file from a process that's no longer running
    return data


async def _pump_to_ami(read_stream, write_stream, pending_initialize_ids, pending_request_ids):
    """Forward harness -> AMI, tracking in-flight request ids, until the harness closes stdin.

    Deliberately does NOT close write_stream itself. The HTTP client's own post_writer task
    closes its reply channel (read_stream_writer) as part of its normal exit once write_stream
    (its request queue) closes -- so closing it the moment the harness disconnects would sever
    the channel any still-in-flight request's reply needs, dropping it instead of delivering it
    late. The caller (bridge()'s _run_to_ami) closes write_stream only after giving pending
    requests a chance to be answered.
    """
    async for item in read_stream:
        if isinstance(item, Exception):
            logger.warning(f"Malformed message from harness: {item}")
            continue
        message_id = getattr(item.message, "id", None)
        if getattr(item.message, "method", None) is not None and message_id is not None:
            # Has both `method` and `id`: a request, not a notification (which has no id
            # and gets no reply), so it's something _pump_to_harness should wait for.
            pending_request_ids.add(message_id)
            if item.message.method == "initialize":
                pending_initialize_ids.add(message_id)
        await write_stream.send(item)


async def _pump_to_harness(read_stream, write_stream, pending_initialize_ids, pending_request_ids, notes):
    """Forward AMI -> harness, appending `notes` to the matching `initialize` reply.

    Only ever touches the one reply whose id matches a request _pump_to_ami saw go by, and only
    when `notes` is non-empty -- every other message passes through completely unmodified.
    Closes write_stream (the harness's side) when read_stream ends, same reasoning as
    _pump_to_ami.
    """
    async with write_stream:
        async for item in read_stream:
            if isinstance(item, Exception):
                logger.warning(f"Malformed message from AMI: {item}")
                continue
            message_id = getattr(item.message, "id", None)
            is_reply = hasattr(item.message, "result") or hasattr(item.message, "error")
            if is_reply:
                pending_request_ids.discard(message_id)
            if notes and message_id in pending_initialize_ids and hasattr(item.message, "result"):
                pending_initialize_ids.discard(message_id)
                existing = item.message.result.get("instructions") or ""
                note_text = "\n\n".join(notes)
                instructions = f"{existing}\n\n{note_text}" if existing else note_text
                item.message.result["instructions"] = instructions
            await write_stream.send(item)


# How long to keep relaying AMI's replies after the harness closes stdin, before giving up on
# any still-unanswered requests and ending the bridge unconditionally.
SHUTDOWN_GRACE_SECONDS = 5


async def bridge(url, skills_changed, hutch_note, token):
    """Relay MCP messages between the harness's stdio transport and AMI's Streamable-HTTP one."""
    # create_mcp_http_client is the same factory streamable_http_client would use by default
    # (SSE-friendly long read timeout, follow_redirects) -- used explicitly here only so a
    # bearer token can be added, when AMI's connection file has one (TCP mode always does; a
    # missing token means either UDS mode or an older AMI that predates this feature).
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with create_mcp_http_client(headers=headers) as http_client:
        async with stdio_server() as (harness_read, harness_write):
            async with streamable_http_client(url, http_client=http_client) as (ami_read, ami_write):
                pending_initialize_ids = set()
                pending_request_ids = set()
                notes = [hutch_note] if hutch_note else []
                if skills_changed:
                    notes.append(SKILLS_UPDATED_NOTE)

                async with anyio.create_task_group() as tg:

                    async def _run_to_ami():
                        try:
                            await _pump_to_ami(harness_read, ami_write, pending_initialize_ids, pending_request_ids)
                        finally:
                            # The harness has nothing more to send. Give any requests it already
                            # sent a bounded window to be answered -- _run_to_harness is still
                            # running and will deliver them -- before closing ami_write. Closing
                            # it any earlier would end the HTTP client's post_writer task, which
                            # also closes the reply channel any still-in-flight request's answer
                            # needs, dropping that reply outright rather than just failing to
                            # wait for it.
                            with anyio.move_on_after(SHUTDOWN_GRACE_SECONDS):
                                while pending_request_ids:
                                    await anyio.sleep(0.05)
                            await ami_write.aclose()
                            tg.cancel_scope.cancel()

                    async def _run_to_harness():
                        try:
                            await _pump_to_harness(
                                ami_read, harness_write, pending_initialize_ids, pending_request_ids, notes
                            )
                        finally:
                            # AMI's side ended (or was cancelled by _run_to_ami above); either
                            # way there is nothing left to relay, so end the bridge immediately.
                            tg.cancel_scope.cancel()

                    tg.start_soon(_run_to_ami)
                    tg.start_soon(_run_to_harness)


def _token_rejected(url, token):
    """True if `token` is rejected (401) by the MCP server at `url`, False if accepted.

    A dedicated preflight request, not exception handling inside bridge(): the mcp client
    library (mcp.client.streamable_http.StreamableHTTPTransport._handle_post_request) turns a
    401 into a normal JSON-RPC error reply delivered through the message stream rather than
    raising, so there is nothing for the `except Exception` around anyio.run(bridge, ...) below
    to catch -- confirmed by driving a real server+client through this exact path, not just
    reading the source. This is the only way to tell the user specifically that their token was
    rejected, rather than have the harness receive a generic, unexplained tool error.

    Returns:
        True if the server answered 401, False for any other response or if it could not be
        reached at all (connection errors are left for bridge()'s own attempt to report).
    """
    try:
        response = httpx.post(url, json={}, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    except httpx.HTTPError:
        return False
    return response.status_code == 401


def main():
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    skills_changed = install_skill_links()
    if skills_changed:
        print("ami-mcp-connect: installed/updated AMI skill links", file=sys.stderr)

    server_info = find_ami_server()
    if server_info is None:
        print(
            f"ami-mcp-connect: no running AMI instance found ({CONNECTION_FILE} missing or "
            'stale). Start ami-local, then restart this harness (or reconnect the "ami" MCP '
            "server from /mcps).",
            file=sys.stderr,
        )
        sys.exit(1)

    url = f"http://{server_info['host']}:{server_info['port']}/mcp"
    token = server_info.get("token")
    if token and _token_rejected(url, token):
        print(
            "ami-mcp-connect: AMI rejected our token (401) -- if AMI was restarted, reconnect "
            'this MCP server to pick up the new token (e.g. reconnect the "ami" MCP server '
            "from /mcps).",
            file=sys.stderr,
        )
        sys.exit(1)

    hutch_note = _hutch_note(server_info.get("hutch"))
    try:
        anyio.run(bridge, url, skills_changed, hutch_note, token)
    except Exception as e:
        print(f"ami-mcp-connect: lost connection to AMI's MCP server at {url}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
