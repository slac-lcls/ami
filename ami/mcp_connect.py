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
import sys

import anyio
from mcp.client.streamable_http import streamable_http_client
from mcp.server.stdio import stdio_server

logger = logging.getLogger(__name__)

CONNECTION_FILE = os.path.expanduser("~/.config/ami/mcp-server.json")

SKILL_NAMES = ("ami-graph-builder", "ami-performance-monitor")

# Directories common harnesses already search for skills. ~/.claude/skills is Claude Code's own
# personal location and one of opencode V2's documented compatibility paths; ~/.config/opencode
# /skills is opencode V2's own global path; ~/.opencode/skills covers opencode V1, which (per
# manual testing during planning) reads skills from there instead -- not from any path in V2's
# documented discovery list.
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


def _package_skills_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")


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
    for target_dir in SKILL_TARGET_DIRS:
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
    """Read the connection file ami-local writes, with a liveness pre-check.

    This is a fast pre-check, not the authoritative test -- a pid can be reused by an unrelated
    process after a crash, which this can't detect. The actual HTTP connection attempt in
    bridge() is what really decides whether AMI is reachable.

    Returns:
        The parsed connection dict ({"host", "port", "pid", "started_at"}), or None if the file
        is missing, malformed, or names a pid that is no longer running.
    """
    try:
        with open(CONNECTION_FILE) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    pid = data.get("pid")
    if pid is not None:
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


async def _pump_to_harness(read_stream, write_stream, pending_initialize_ids, pending_request_ids, skills_changed):
    """Forward AMI -> harness, appending a restart note to the matching `initialize` reply.

    Only ever touches the one reply whose id matches a request _pump_to_ami saw go by, and only
    when install_skill_links() actually changed something this run -- every other message
    passes through completely unmodified. Closes write_stream (the harness's side) when
    read_stream ends, same reasoning as _pump_to_ami.
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
            if skills_changed and message_id in pending_initialize_ids and hasattr(item.message, "result"):
                pending_initialize_ids.discard(message_id)
                existing = item.message.result.get("instructions") or ""
                note = f"{existing}\n\n{SKILLS_UPDATED_NOTE}" if existing else SKILLS_UPDATED_NOTE
                item.message.result["instructions"] = note
            await write_stream.send(item)


# How long to keep relaying AMI's replies after the harness closes stdin, before giving up on
# any still-unanswered requests and ending the bridge unconditionally.
SHUTDOWN_GRACE_SECONDS = 5


async def bridge(url, skills_changed):
    """Relay MCP messages between the harness's stdio transport and AMI's Streamable-HTTP one."""
    async with stdio_server() as (harness_read, harness_write):
        async with streamable_http_client(url) as (ami_read, ami_write):
            pending_initialize_ids = set()
            pending_request_ids = set()

            async with anyio.create_task_group() as tg:

                async def _run_to_ami():
                    try:
                        await _pump_to_ami(harness_read, ami_write, pending_initialize_ids, pending_request_ids)
                    finally:
                        # The harness has nothing more to send. Give any requests it already
                        # sent a bounded window to be answered -- _run_to_harness is still
                        # running and will deliver them -- before closing ami_write. Closing it
                        # any earlier would end the HTTP client's post_writer task, which also
                        # closes the reply channel any still-in-flight request's answer needs,
                        # dropping that reply outright rather than just failing to wait for it.
                        with anyio.move_on_after(SHUTDOWN_GRACE_SECONDS):
                            while pending_request_ids:
                                await anyio.sleep(0.05)
                        await ami_write.aclose()
                        tg.cancel_scope.cancel()

                async def _run_to_harness():
                    try:
                        await _pump_to_harness(
                            ami_read, harness_write, pending_initialize_ids, pending_request_ids, skills_changed
                        )
                    finally:
                        # AMI's side ended (or was cancelled by _run_to_ami above); either way
                        # there is nothing left to relay, so end the bridge immediately.
                        tg.cancel_scope.cancel()

                tg.start_soon(_run_to_ami)
                tg.start_soon(_run_to_harness)


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
    try:
        anyio.run(bridge, url, skills_changed)
    except Exception as e:
        print(f"ami-mcp-connect: lost connection to AMI's MCP server at {url}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
