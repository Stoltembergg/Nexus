#!/usr/bin/env python3
"""Supervise one guest session so a launcher exit does not orphan it.

The launcher runs this script instead of exec'ing the guest client directly. It
forwards SIGINT/SIGTERM/SIGHUP to the child, and after the child exits it asks
darlingserver to shut down and stops any process still inside the guest PID
namespace. That covers the two ways a session leaks: the Riot Client stays
resident after its window closes, and a killed loader leaves launchd/mldr and
the client tree behind.

The guest namespace is captured while the session runs, from a process that
carries this prefix's `__mldr_sockpath`; without that evidence cleanup never
touches a process. If the namespace cannot be read, only processes that carry
the socket are stopped. Cleanup only runs when this launcher started the
runtime: a second launch that attaches to an existing server leaves it alone
when its own loader exits.

Optional idle stop: with RCLOL_STOP_AFTER_CLIENT_SECONDS=N, the supervisor
stops the session once a managed League/Riot window has been absent for N
seconds and no game process is running. It is off by default and never stops
when the window state cannot be read.

Match protection: when the loader exits while this prefix's game is still
running (the Riot Client was closed mid-match), cleanup waits for the game to
end instead of tearing the match down. A termination signal still stops the
session at once.

Match priority: while the game runs, the other processes in the guest
namespace (Riot Client, LeagueClientUx and their CEF helpers) run at nice 15
with SCHED_BATCH, and go back to normal when the match ends. Set
RCLOL_MATCH_PRIORITY=0 to turn this off.

Set RCLOL_CLEAN_ON_EXIT=0 to keep the previous behaviour: the runtime is left
alone when the launcher exits.

Usage (from run-riot-client.sh):

    python3 session-supervisor.py --prefix ~/.darling --darling /path/darling \
        -- python3 exec-guest.py env ... darling ...
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

SOCK_VARIABLE = b'__mldr_sockpath'
SOCK_NAME = '.darlingserver.sock'
GAME_NAME = 'LeagueofLegends'
CLIENT_CLASSES = ('leagueclientux', 'riot client')
POLL_SECONDS = 2.0
BACKGROUND_NICE = 15
TERM_GRACE = 5.0
KILL_GRACE = 5.0


def log(message, out=sys.stdout):
    """Best-effort output; a closed terminal must not abort cleanup."""
    try:
        print('session-supervisor: %s' % message, file=out, flush=True)
    except (OSError, ValueError):
        pass


def process_info(proc):
    """Return (state, ppid, start_ticks), or None when stat is unreadable."""
    try:
        fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        if len(fields) < 20:
            return None
        return fields[0], int(fields[1]), int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


def command_names(proc):
    try:
        raw = (proc / 'cmdline').read_bytes()
    except OSError:
        return []
    return [os.path.basename(part.decode(errors='replace'))
            for part in raw.split(b'\0') if part]


def command_line(proc):
    """Raw argv as text, without basenaming, for interpreter/path checks."""
    try:
        raw = (proc / 'cmdline').read_bytes()
    except OSError:
        return []
    return [os.fsdecode(part) for part in raw.split(b'\0') if part]


def environment(proc):
    try:
        return dict(
            item.split(b'=', 1)
            for item in (proc / 'environ').read_bytes().split(b'\0')
            if b'=' in item
        )
    except OSError:
        return {}


def socket_prefix(proc):
    """The prefix named by a process's loader socket, or None."""
    raw = environment(proc).get(SOCK_VARIABLE)
    if raw is None:
        return None
    try:
        path = Path(os.fsdecode(raw))
        return path.parent.resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def owned_by_prefix(proc, prefix):
    if process_info(proc) is None:
        return False
    try:
        if proc.stat().st_uid != os.getuid():
            return False
    except OSError:
        return False
    return socket_prefix(proc) == prefix


def prefix_namespace(prefix, proc_root=Path('/proc')):
    """The guest PID namespace, proved by a process carrying this socket."""
    for proc in proc_root.iterdir() if proc_root.exists() else ():
        if not proc.name.isdigit():
            continue
        if owned_by_prefix(proc, prefix):
            try:
                return os.readlink(proc / 'ns/pid')
            except OSError:
                return None
    return None


def namespace_members(namespace, proc_root=Path('/proc'), own_namespace=None):
    """Processes inside namespace, excluding this host process.

    A namespace equal to the supervisor's own is refused: a mistaken capture
    must never turn session cleanup into a host-wide kill.
    """
    if not namespace or namespace == own_namespace:
        return []
    found = []
    for proc in proc_root.iterdir() if proc_root.exists() else ():
        if not proc.name.isdigit():
            continue
        try:
            if os.readlink(proc / 'ns/pid') != namespace:
                continue
            if proc.stat().st_uid != os.getuid():
                continue
        except OSError:
            continue
        found.append((int(proc.name), proc))
    return found


def prefix_only(prefix, proc_root=Path('/proc')):
    """Fallback: processes that positively carry this prefix's socket."""
    found = []
    for proc in proc_root.iterdir() if proc_root.exists() else ():
        if proc.name.isdigit() and owned_by_prefix(proc, prefix):
            found.append((int(proc.name), proc))
    return found


def deepest_first(members, proc_root=Path('/proc')):
    """Children before parents, so live parents can reap their own tree."""
    parents = {}
    for pid, proc in members:
        info = process_info(proc)
        parents[pid] = info[1] if info else None
    known = {pid for pid, _proc in members}

    def depth(pid, seen):
        parent = parents.get(pid)
        if parent not in known or parent == pid or parent in seen:
            return 0
        return depth(parent, seen | {pid}) + 1

    return sorted((pid for pid, _proc in members),
                  key=lambda pid: (-depth(pid, set()), pid))


def wrapper(proc, name):
    """Return (state, comm, ppid) for a /proc entry, or None."""
    try:
        state = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0]
        comm = (proc / 'comm').read_text().strip()
        parent = int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[1])
        return state, comm, parent
    except (OSError, ValueError, IndexError):
        return None


def stop_processes(members, kill=os.kill, sleep=time.sleep, proc_root=Path('/proc'),
                   out=sys.stdout, term_grace=TERM_GRACE, kill_grace=KILL_GRACE,
                   clock=time.monotonic):
    """SIGTERM then SIGKILL a set of processes; return what is still present."""
    def alive(pid, proc):
        info = process_info(proc)
        return info is not None and info[0] != 'Z'

    remaining = [(pid, proc) for pid, proc in members if alive(pid, proc)]
    for pid in deepest_first(remaining, proc_root):
        try:
            kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = clock() + term_grace
    while remaining and clock() < deadline:
        sleep(POLL_SECONDS)
        remaining = [(pid, proc) for pid, proc in remaining if alive(pid, proc)]
    # Re-read once before escalating: a zero grace period must not SIGKILL a
    # process that already exited on SIGTERM.
    remaining = [(pid, proc) for pid, proc in remaining if alive(pid, proc)]
    for pid in deepest_first(remaining, proc_root):
        try:
            kill(pid, signal.SIGKILL)
        except OSError:
            pass
    deadline = clock() + kill_grace
    while remaining and clock() < deadline:
        sleep(POLL_SECONDS)
        remaining = [(pid, proc) for pid, proc in remaining
                     if process_info(proc) is not None]
    # Re-read once even when a grace period is zero, so the caller never gets a
    # stale "still running" answer for a process that SIGKILL already removed.
    return [(pid, proc) for pid, proc in remaining
            if process_info(proc) is not None]


def cleanup(prefix, darling, namespace, proc_root=Path('/proc'), run=subprocess.run,
            kill=os.kill, sleep=time.sleep, out=sys.stdout, own_namespace=None,
            term_grace=TERM_GRACE, kill_grace=KILL_GRACE, clock=time.monotonic):
    """Shut down the runtime, then stop anything left in the guest namespace."""
    if namespace is None:
        namespace = prefix_namespace(prefix, proc_root)
    own_namespace = own_namespace or os.readlink('/proc/self/ns/pid')
    members = namespace_members(namespace, proc_root, own_namespace)
    if members and darling:
        try:
            run([darling, 'shutdown'], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=25)
        except (OSError, subprocess.SubprocessError):
            pass
        deadline = clock() + term_grace
        while members and clock() < deadline:
            sleep(POLL_SECONDS)
            members = [(pid, proc) for pid, proc in members
                       if process_info(proc) is not None]
    if not members:
        members = prefix_only(prefix, proc_root)
    if not members:
        log('runtime and guest processes are gone', out)
        return []
    log('stopping %d leftover guest process(es)' % len(members), out)
    remaining = stop_processes(members, kill=kill, sleep=sleep,
                               proc_root=proc_root, out=out, term_grace=term_grace,
                               kill_grace=kill_grace, clock=clock)
    if remaining:
        details = []
        for pid, proc in remaining:
            info = wrapper(proc, proc_root)
            details.append('%d (%s, %s)' % (pid, info[1] if info else '?',
                                            info[0] if info else '?'))
        log('still present: %s' % '; '.join(details), out)
    else:
        log('guest session stopped', out)
    return remaining


def runtime_alive(prefix, proc_root=Path('/proc')):
    """True when this prefix's darlingserver marker names a live server.

    Used to tell "we started the runtime" from "we attached to one that another
    launcher already owns". Cleanup must never end the second kind.
    """
    try:
        pid = int((prefix / '.init.pid').read_text().strip())
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    proc = proc_root / str(pid)
    info = process_info(proc)
    if info is None or info[0] == 'Z':
        return False
    argv = command_line(proc)
    if not argv or os.path.basename(argv[0]) != 'darlingserver':
        return False
    try:
        return (proc.stat().st_uid == os.getuid() and len(argv) > 1
                and Path(argv[1]).resolve() == prefix)
    except OSError:
        return False


def managed_client_window(run=subprocess.run):
    """True/False for a managed client window; None when it cannot be read."""
    try:
        listing = run(['xprop', '-root', '_NET_CLIENT_LIST'], text=True,
                      capture_output=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    lowered = listing.lower()
    if '_net_client_list' not in lowered or 'not found' in lowered:
        return None
    for raw in set(re.findall(r'0x[0-9a-fA-F]+', listing)):
        try:
            classes = run(['xprop', '-id', raw, 'WM_CLASS'], text=True,
                          capture_output=True, timeout=5).stdout.lower()
        except (OSError, subprocess.SubprocessError):
            return None
        if 'not found' in classes or '=' not in classes:
            return None
        if any(name in classes for name in CLIENT_CLASSES):
            return True
    return False


def game_running(prefix, proc_root=Path('/proc')):
    """True/False for a game of this prefix; None when /proc cannot prove it."""
    if not proc_root.exists():
        return None
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        if GAME_NAME not in command_names(proc):
            continue
        if socket_prefix(proc) == prefix:
            return True
    return False


def idle_decision(seen_client, idle_since, now, windows, game, seconds):
    """Return (seen_client, idle_since, stop_now) for one poll."""
    if seconds <= 0 or windows is None or game is None:
        return seen_client, None, False
    if game or windows:
        return seen_client or game or windows, None, False
    if not seen_client:
        return False, None, False
    if idle_since is None:
        return True, now, False
    return True, idle_since, now - idle_since >= seconds


def set_priority(pid, nice_value, batch):
    """Apply nice/scheduler to every thread of pid; ignore vanished threads."""
    policy = os.SCHED_BATCH if batch else os.SCHED_OTHER
    tasks = Path('/proc/%d/task' % pid)
    try:
        tids = [int(t.name) for t in tasks.iterdir() if t.name.isdigit()]
    except OSError:
        tids = [pid]
    for tid in tids:
        try:
            os.setpriority(os.PRIO_PROCESS, tid, nice_value)
            os.sched_setscheduler(tid, policy, os.sched_param(0))
        except OSError:
            pass


class MatchPriority:
    """Lower the launcher and CEF processes of the guest while a match runs."""

    def __init__(self, enabled=True, apply=set_priority, out=sys.stdout):
        self.enabled = enabled
        self.apply = apply
        self.out = out
        self.lowered = set()

    def update(self, namespace, game, proc_root=Path('/proc'), own_namespace=None):
        if not self.enabled:
            return
        if not game:
            self.restore()
            return
        background = set()
        for pid, proc in namespace_members(namespace, proc_root, own_namespace):
            if GAME_NAME not in command_names(proc):
                background.add(pid)
        new = background - self.lowered
        if new and not self.lowered:
            log('match running; lowering launcher and client priority', self.out)
        for pid in sorted(new):
            self.apply(pid, BACKGROUND_NICE, True)
        self.lowered |= new

    def restore(self):
        if not self.lowered:
            return
        log('match over; restoring launcher and client priority', self.out)
        for pid in sorted(self.lowered):
            self.apply(pid, 0, False)
        self.lowered = set()


def run_supervised(command, prefix, darling, stop_after=0, clean=True,
                   proc_root=Path('/proc'), run=subprocess.run, kill=os.kill,
                   sleep=time.sleep, out=sys.stdout, poll=POLL_SECONDS,
                   own_namespace=None, priority=None):
    """Run command, forward termination signals, then clean the session.

    Cleanup only runs when this launcher started the runtime. A second launch
    while a session is alive attaches to that server, and must not shut it down
    when its own loader exits.
    """
    if not clean:
        os.execvp(command[0], command)
    owns_runtime = not runtime_alive(prefix, proc_root)
    namespace = None
    child = subprocess.Popen(command, start_new_session=True)
    stop = []
    previous = {}

    def forward(signum, _frame):
        stop.append(signum)
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except OSError:
            pass

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous[signum] = signal.signal(signum, forward)
    seen_client = False
    idle_since = None
    priority = priority or MatchPriority(enabled=False)
    try:
        while child.poll() is None and not stop:
            # Learn the guest namespace while the session runs: after a crash
            # the processes that still carry the socket may be the only proof.
            if namespace is None:
                namespace = prefix_namespace(prefix, proc_root)
            priority.update(namespace, game_running(prefix, proc_root), proc_root,
                            own_namespace)
            if stop_after > 0:
                now = time.monotonic()
                seen_client, idle_since, stop_now = idle_decision(
                    seen_client, idle_since, now, managed_client_window(run),
                    game_running(prefix, proc_root), stop_after)
                if stop_now:
                    log('client window has been gone for %ds; stopping the session'
                        % stop_after, out)
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except OSError:
                        pass
                    break
            sleep(poll)
        deadline = time.monotonic() + TERM_GRACE
        while child.poll() is None and time.monotonic() < deadline:
            sleep(poll)
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except OSError:
                pass
        code = child.wait()
        # The loader can exit while the match keeps running, for example when
        # the Riot Client is closed in game. Wait for the match, not the loader.
        if not stop and owns_runtime and game_running(prefix, proc_root):
            log('loader exited during a match; waiting for the game to end', out)
            namespace = namespace or prefix_namespace(prefix, proc_root)
            while not stop and game_running(prefix, proc_root):
                priority.update(namespace, True, proc_root, own_namespace)
                sleep(poll)
        priority.restore()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    if not owns_runtime:
        log('another session owns this runtime; leaving it running', out)
        remaining = []
    else:
        namespace = namespace or prefix_namespace(prefix, proc_root)
        remaining = cleanup(prefix, darling, namespace, proc_root=proc_root, run=run,
                            kill=kill, sleep=sleep, out=out,
                            own_namespace=own_namespace)
    if stop:
        log('interrupted by signal %d' % stop[0], out)
    status = code if code >= 0 else 128 - code
    # A surviving guest process is a failed cleanup, not a clean exit.
    return (status or 1) if remaining else status


def env_seconds(name, out=sys.stderr):
    """Seconds from an optional environment variable; 0 when unset or invalid."""
    raw = os.environ.get(name, '').strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        log('ignoring invalid %s=%r' % (name, raw), out)
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--darling', help='loader used for a graceful shutdown')
    parser.add_argument('--stop-after', type=int,
                        default=env_seconds('RCLOL_STOP_AFTER_CLIENT_SECONDS'),
                        help='stop after the client window has been gone this many seconds')
    parser.add_argument('--no-clean', action='store_true',
                        help='leave the runtime alone after the child exits')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('a command is required after --')
    clean = not args.no_clean and os.environ.get('RCLOL_CLEAN_ON_EXIT', '1') != '0'
    prefix = args.prefix.expanduser().resolve()
    priority = MatchPriority(enabled=os.environ.get('RCLOL_MATCH_PRIORITY', '1') != '0')
    return run_supervised(command, prefix, args.darling, stop_after=max(0, args.stop_after),
                          clean=clean, priority=priority)


if __name__ == '__main__':
    sys.exit(main())
