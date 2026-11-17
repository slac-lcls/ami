import ctypes
import functools
import multiprocessing as _mp
import os
import signal
import subprocess
import sys
import time
import warnings
from multiprocessing import *  # noqa

try:
    if "SPT_NOENV" not in os.environ:
        os.environ["SPT_NOENV"] = "1"
    import setproctitle
except ImportError:
    setproctitle = None

PR_SET_PDEATHSIG = 1


def check_mp_start_method():
    if sys.platform == "darwin":
        method = _mp.get_start_method(allow_none=True)
        if method is None:
            _mp.set_start_method("spawn")
        elif method != "spawn":
            warnings.warn("AMI may not work properly on macOS with the %s start method" % _mp.get_start_method())


def set_pdeathsig(sig, parent_pid=None):
    """Linux only: ask the kernel to send us `sig` if our direct parent process dies.

    A backstop against orphaned ami child processes (editor, plot/node windows, the dmypy
    daemon the editor starts, ...) that would otherwise keep running -- and keep holding
    their port/socket -- if their parent dies without running its own cleanup (crash,
    SIGKILL, a signal with no handler, e.g. the editor dying to the SIGTERM ami.local's
    cleanup() sends the "client" process). See #227. No-op on platforms without prctl
    (e.g. macOS).

    Args:
        sig: signal to request, e.g. signal.SIGKILL (can't be caught or ignored, so this is
            guaranteed to actually terminate the child, unlike SIGTERM).
        parent_pid: if given, also guards the fork()/prctl() race: if our parent has
            already exited by the time this runs (getppid() no longer matches), no
            PDEATHSIG will ever arrive, so we exit immediately ourselves instead of
            lingering (reparented to init, or adopted by a subreaper such as tmux or
            systemd --user). Must be captured by the caller *before* forking -- by the
            time this runs in the child, os.getpid() would give the child's own pid, not
            the parent's.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, sig)
    except OSError:
        return
    if parent_pid is not None and os.getppid() != parent_pid:
        os._exit(1)


def start_dmypy_daemon(status_file, timeout=10):
    """Start dmypy's server as our own direct child, so PR_SET_PDEATHSIG can reach it.

    `dmypy start` double-forks and setsid()s its server (mypy/dmypy_server.py), so it ends
    up reparented to init -- no PDEATHSIG set on anything we spawn can reach it, and it's
    orphaned whenever our process dies by signal instead of running its own `dmypy stop`
    (see #227). `dmypy --status-file F daemon` runs the same server in the foreground,
    without forking, so launching it as a plain subprocess with PR_SET_PDEATHSIG keeps it
    tied to our lifetime. `start_new_session=True` keeps it out of ami-local's process
    group, so it isn't also sent Ctrl-C's SIGINT directly.

    Returns:
        The Popen object once the status file shows the server is listening (or `timeout`
        seconds have passed, or it has already exited) -- the caller can send it `dmypy
        stop`/`check`/etc. via that status file, or kill the process directly as a backstop.
    """
    proc = subprocess.Popen(
        ["dmypy", "--status-file", status_file, "daemon"],
        start_new_session=True,
        preexec_fn=functools.partial(set_pdeathsig, signal.SIGKILL, os.getpid()),
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            if os.path.getsize(status_file) > 0:
                break
        except OSError:
            pass
        time.sleep(0.05)
    return proc


class Process(_mp.Process):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={}, *, daemon=None):
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon)
        self.procname = name

    def run(self):
        set_pdeathsig(signal.SIGKILL, self._parent_pid)
        if self._target:
            if self.procname is not None:
                setproctitle.setproctitle("ami " + self.procname)
            self._target(*self._args, **self._kwargs)
