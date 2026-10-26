#!/usr/bin/env python3
"""Supervise one guest session so a launcher exit does not orphan it.

The launcher runs this script instead of exec'ing the guest client directly. It
handles SIGINT/SIGTERM/SIGHUP in ordinary control flow, and after the child
exits it may ask darlingserver to shut down and stop any process still inside
the guest PID namespace. Every destructive action requires a positive idle
game and shared client-window inventory; active or unknown state preserves the
session.

The guest namespace is captured while the session runs, from a process that
carries this prefix's `__mldr_sockpath`; without that evidence cleanup never
touches a process. If the namespace cannot be read, only processes that carry
the socket are stopped. Cleanup only runs when this launcher started the
runtime: a second launch that attaches to an existing server leaves it alone
when its own loader exits.

Optional idle stop: with RCLOL_STOP_AFTER_CLIENT_SECONDS=N, the supervisor
stops an owned session once a managed League/Riot window has been absent for N
seconds and no game process is running. It is off by default and never stops
when either state cannot be read.

Match protection: when the loader exits while this prefix's game is still
running (the Riot Client was closed mid-match), cleanup waits for the game to
end instead of tearing the match down. A termination signal still stops the
session at once.

Set RCLOL_CLEAN_ON_EXIT=0 to keep the previous behaviour: the runtime is left
alone when the launcher exits.

Usage (from run-riot-client.sh):

    python3 session-supervisor.py --prefix ~/.darling --darling /path/darling \
        -- python3 exec-guest.py env ... darling ...
"""
import argparse
import errno
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SOCK_VARIABLE = b'__mldr_sockpath'
SOCK_NAME = '.darlingserver.sock'
GAME_NAME = 'LeagueofLegends'
POLL_SECONDS = 2.0
TERM_GRACE = 5.0
KILL_GRACE = 5.0

# Keep the shared inventory as the single source of truth for X11/Niri/Wayland.
# The script is also loaded directly by the test suite, where tools/ is not
# necessarily on sys.path.
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from client_window_state import client_windows_present


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


def socket_prefix(proc):
    """The prefix named by a process's loader socket, or None."""
    try:
        raw = (proc / 'environ').read_bytes()
    except OSError:
        return None
    values = [item.split(b'=', 1)[1] for item in raw.split(b'\0')
              if item.startswith(SOCK_VARIABLE + b'=')]
    if len(values) != 1:
        return None
    return _resolve_socket_prefix(values[0])


def _owned_prefix_start_ticks(proc, prefix):
    """Return the observed identity if prefix ownership stayed consistent."""
    before = process_info(proc)
    if before is None:
        return None
    try:
        if proc.stat().st_uid != os.getuid():
            return None
    except OSError:
        return None
    if socket_prefix(proc) != prefix:
        return None
    after = process_info(proc)
    if after is None or after[2] != before[2]:
        return None
    return before[2]


def owned_by_prefix(proc, prefix):
    return _owned_prefix_start_ticks(proc, prefix) is not None


def prefix_namespace(prefix, proc_root=Path('/proc')):
    """The guest PID namespace, proved by a process carrying this socket."""
    for proc in proc_root.iterdir() if proc_root.exists() else ():
        if not proc.name.isdigit():
            continue
        start_ticks = _owned_prefix_start_ticks(proc, prefix)
        if start_ticks is None:
            continue
        try:
            namespace = os.readlink(proc / 'ns/pid')
        except OSError:
            continue
        after = process_info(proc)
        if after is not None and after[2] == start_ticks:
            return namespace
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
        before = process_info(proc)
        if before is None:
            continue
        try:
            if os.readlink(proc / 'ns/pid') != namespace:
                continue
            if proc.stat().st_uid != os.getuid():
                continue
        except OSError:
            continue
        after = process_info(proc)
        if after is not None and after[2] == before[2]:
            found.append((int(proc.name), proc, before[2]))
    return found


def prefix_only(prefix, proc_root=Path('/proc')):
    """Fallback: processes that positively carry this prefix's socket."""
    found = []
    for proc in proc_root.iterdir() if proc_root.exists() else ():
        if not proc.name.isdigit():
            continue
        start_ticks = _owned_prefix_start_ticks(proc, prefix)
        if start_ticks is not None:
            found.append((int(proc.name), proc, start_ticks))
    return found


def deepest_first(members, proc_root=Path('/proc')):
    """Children before parents, so live parents can reap their own tree."""
    parents = {}
    for pid, proc, start_ticks in members:
        info = process_info(proc)
        parents[pid] = (info[1] if info is not None and info[2] == start_ticks
                        else None)
    known = {pid for pid, _proc, _start_ticks in members}

    def depth(pid, seen):
        parent = parents.get(pid)
        if parent not in known or parent == pid or parent in seen:
            return 0
        return depth(parent, seen | {pid}) + 1

    return sorted(members, key=lambda candidate: (
        -depth(candidate[0], set()), candidate[0]))


def candidate_info(candidate):
    """Return current proc info only while the captured PID identity matches."""
    _pid, proc, start_ticks = candidate
    info = process_info(proc)
    return info if info is not None and info[2] == start_ticks else None


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
                   clock=time.monotonic, safety_check=None):
    """Signal members; None means a safety veto aborted the cleanup pass."""
    # This low-level helper has no prefix/window context of its own. Callers
    # must explicitly supply the live safety gate; absence fails closed.
    safe = safety_check or (lambda: False)

    def alive(candidate):
        info = candidate_info(candidate)
        return info is not None and info[0] != 'Z'

    def present(candidate):
        return candidate_info(candidate) is not None

    remaining = [candidate for candidate in members if alive(candidate)]
    for candidate in deepest_first(remaining, proc_root):
        pid = candidate[0]
        if not safe():
            log('cleanup protected: game/window state is active or unknown', out)
            return None
        if not alive(candidate):
            continue
        # The final /proc identity check and kill(2) cannot be atomic: a PID
        # can still be reused in the small interval between this check and the
        # syscall. The check prevents signaling identities already observed as
        # replacements, but does not claim to close that kernel-level race.
        try:
            kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = clock() + term_grace
    while remaining and clock() < deadline:
        sleep(POLL_SECONDS)
        remaining = [candidate for candidate in remaining if alive(candidate)]
    if not safe():
        log('cleanup protected: game/window state is active or unknown', out)
        return None
    # Re-read once before escalating: a zero grace period must not SIGKILL a
    # process that already exited on SIGTERM. Identity checks also discard a
    # PID that was reused during the grace period.
    remaining = [candidate for candidate in remaining if alive(candidate)]
    for candidate in deepest_first(remaining, proc_root):
        pid = candidate[0]
        if not safe():
            log('cleanup protected: game/window state is active or unknown', out)
            return None
        if not alive(candidate):
            continue
        # The same non-atomic /proc-check-to-kill(2) gap applies to escalation.
        try:
            kill(pid, signal.SIGKILL)
        except OSError:
            pass
    deadline = clock() + kill_grace
    while remaining and clock() < deadline:
        sleep(POLL_SECONDS)
        remaining = [candidate for candidate in remaining if present(candidate)]
    # Re-read once even when a grace period is zero, so the caller never gets a
    # stale "still running" answer for a process that SIGKILL already removed.
    return [candidate for candidate in remaining if present(candidate)]


def cleanup(prefix, darling, namespace, proc_root=Path('/proc'), run=subprocess.run,
            kill=os.kill, sleep=time.sleep, out=sys.stdout, own_namespace=None,
            term_grace=TERM_GRACE, kill_grace=KILL_GRACE, clock=time.monotonic,
            safety_check=None, window_probe=None):
    """Shut down only under positive idle evidence; None means protected."""
    safe = safety_check or (lambda: safe_to_stop(prefix, proc_root, window_probe))
    if not safe():
        log('cleanup protected: game/window state is active or unknown', out)
        return None
    if namespace is None:
        namespace = prefix_namespace(prefix, proc_root)
    own_namespace = own_namespace or os.readlink('/proc/self/ns/pid')
    members = namespace_members(namespace, proc_root, own_namespace)
    if members and darling:
        if not safe():
            log('cleanup protected: game/window state is active or unknown', out)
            return None
        try:
            run([darling, 'shutdown'], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=25)
        except (OSError, subprocess.SubprocessError):
            pass
        if not safe():
            log('cleanup protected: game/window state is active or unknown', out)
            return None
        deadline = clock() + term_grace
        while members and clock() < deadline:
            sleep(POLL_SECONDS)
            members = [candidate for candidate in members
                       if candidate_info(candidate) is not None]
        if not safe():
            log('cleanup protected: game/window state is active or unknown', out)
            return None
    if not members:
        members = prefix_only(prefix, proc_root)
    if not members:
        log('runtime and guest processes are gone', out)
        return []
    log('stopping %d leftover guest process(es)' % len(members), out)
    remaining = stop_processes(members, kill=kill, sleep=sleep,
                               proc_root=proc_root, out=out, term_grace=term_grace,
                               kill_grace=kill_grace, clock=clock,
                               safety_check=safe)
    if remaining is None:
        return None
    if remaining:
        details = []
        for pid, proc, _start_ticks in remaining:
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
    """Compatibility wrapper routed through the shared window inventory."""
    if run is subprocess.run:
        return client_windows_present()

    def check_output(command, text=True, stderr=None, timeout=5):
        result = run(command, text=text, stdout=subprocess.PIPE, stderr=stderr,
                     timeout=timeout)
        if getattr(result, 'returncode', 0):
            raise subprocess.CalledProcessError(result.returncode, command)
        return result.stdout

    return client_windows_present(check_output=check_output)


def _proc_snapshot(proc):
    """Read state, parent, start ticks and comm from one stat snapshot."""
    try:
        raw = (proc / 'stat').read_text()
        comm = raw.split('(', 1)[1].rsplit(')', 1)[0]
        fields = raw.rsplit(')', 1)[1].split()
        if len(fields) < 20:
            return None
        return fields[0], int(fields[1]), int(fields[19]), comm
    except (OSError, ValueError, IndexError):
        return None


def _proc_still_present(proc):
    try:
        proc.stat()
        return True
    except OSError as exc:
        return exc.errno != errno.ENOENT


def _identity_gone_or_unknown(proc, identity):
    """True means this inspection may safely ignore a vanished/zombie PID."""
    after = _proc_snapshot(proc)
    if after is not None:
        if after[0] == 'Z':
            return True
        if after[2] != identity[2]:
            return False
        return False
    return not _proc_still_present(proc)


def _unrelated_identity_stable(proc, before, command):
    """Recheck an apparent non-game entry before excluding it from the scan."""
    command_again = _read_command(proc)
    after = _proc_snapshot(proc)
    if after is None:
        return True if not _proc_still_present(proc) else None
    if after[0] == 'Z':
        return True
    if (after[2] != before[2] or after[3] != before[3]
            or command_again is None or command_again != command):
        return None
    return False


def _read_command(proc):
    try:
        return (proc / 'cmdline').read_bytes()
    except OSError:
        return None


def _read_environ(proc):
    try:
        return (proc / 'environ').read_bytes()
    except OSError:
        return None


def _command_is_game(raw):
    return any(GAME_NAME in os.path.basename(os.fsdecode(part))
               for part in raw.split(b'\0') if part)


def _socket_value(raw):
    """Return the exact loader-socket value, or None when it is absent/ambiguous."""
    values = [item.split(b'=', 1)[1] for item in raw.split(b'\0')
              if item.startswith(SOCK_VARIABLE + b'=')]
    return values[0] if len(values) == 1 else None


def _resolve_socket_prefix(raw):
    if not raw:
        return None
    try:
        socket_path = Path(os.fsdecode(raw))
        if not socket_path.is_absolute() or socket_path.name != SOCK_NAME:
            return None
        return socket_path.parent.resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def game_running(prefix, proc_root=Path('/proc')):
    """Tri-state game probe; unknown evidence never authorizes a stop."""
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    prefix = Path(prefix).resolve()
    for proc in entries:
        if not proc.name.isdigit():
            continue
        before = _proc_snapshot(proc)
        if before is None:
            if _proc_still_present(proc):
                return None
            continue
        if before[0] == 'Z':
            continue

        command = _read_command(proc)
        comm_is_game = GAME_NAME in before[3]
        if command is None:
            if _identity_gone_or_unknown(proc, before):
                continue
            # Without argv, even a non-game comm cannot rule out a relevant
            # executable that changed its process title.
            return None
        if not command.strip(b'\0'):
            if GAME_NAME in before[3] or before[3].lower() == 'mldr':
                if _identity_gone_or_unknown(proc, before):
                    continue
                return None
            # An empty argv is not proof of irrelevance. Confirm that the
            # process identity/comm and the empty cmdline stayed stable.
            stable = _unrelated_identity_stable(proc, before, command)
            if stable is None:
                return None
            continue
        if not _command_is_game(command) and not comm_is_game:
            stable = _unrelated_identity_stable(proc, before, command)
            if stable is None:
                return None
            # Environment is intentionally not inspected for unrelated entries.
            continue
        try:
            uid = proc.stat().st_uid
        except OSError:
            if _identity_gone_or_unknown(proc, before):
                continue
            return None
        if uid != os.getuid():
            after = _proc_snapshot(proc)
            if after is None:
                if not _proc_still_present(proc):
                    continue
                return None
            if after[0] == 'Z':
                continue
            if after[2] != before[2] or after[3] != before[3]:
                return None
            command_again = _read_command(proc)
            if command_again is None:
                if _identity_gone_or_unknown(proc, before):
                    continue
                return None
            if command_again != command:
                return None
            try:
                uid_again = proc.stat().st_uid
            except OSError:
                if _identity_gone_or_unknown(proc, before):
                    continue
                return None
            if uid_again != uid:
                return None
            continue
        environ = _read_environ(proc)
        if environ is None:
            if _identity_gone_or_unknown(proc, before):
                continue
            return None
        command_again = _read_command(proc)
        environ_again = _read_environ(proc)
        try:
            uid_again = proc.stat().st_uid
        except OSError:
            if _identity_gone_or_unknown(proc, before):
                continue
            return None
        after = _proc_snapshot(proc)
        if after is None:
            if not _proc_still_present(proc):
                continue
            return None
        if after[0] == 'Z':
            continue
        if (after[2] != before[2] or after[3] != before[3]
                or uid_again != uid
                or command_again is None or environ_again is None
                or command_again != command
                or _socket_value(environ_again) != _socket_value(environ)):
            return None

        socket_value = _socket_value(environ)
        if socket_value is None:
            return None
        owner_prefix = _resolve_socket_prefix(socket_value)
        if owner_prefix is None:
            return None
        if owner_prefix == prefix:
            return True
        # A stable, readable socket path proves this game belongs to a
        # different prefix; it is not evidence that this prefix is active.
    return False


def safe_to_stop(prefix, proc_root=Path('/proc'), window_probe=None):
    """True only when both independent safety probes positively report idle.

    The procfs and window observations are not an atomic lease: state can
    change between this check and a later signal.
    """
    probe = client_windows_present if window_probe is None else window_probe
    try:
        game = game_running(prefix, proc_root)
    except Exception:
        game = None
    try:
        windows = probe()
    except Exception:
        windows = None
    return game is False and windows is False


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


def run_supervised(command, prefix, darling, stop_after=0, clean=True,
                   proc_root=Path('/proc'), run=subprocess.run, kill=os.kill,
                   sleep=time.sleep, out=sys.stdout, poll=POLL_SECONDS,
                   own_namespace=None, popen=None, killpg=None,
                   register_signal=None, window_probe=None, clock=None):
    """Run command and handle stop requests in ordinary, safety-checked flow.

    Cleanup only runs when this launcher started the runtime. A second launch
    while a session is alive attaches to that server, and must not shut it down
    when its own loader exits.
    """
    if not clean:
        os.execvp(command[0], command)
    owns_runtime = not runtime_alive(prefix, proc_root)
    namespace = None
    child = (subprocess.Popen if popen is None else popen)(
        command, start_new_session=True)
    send_group = os.killpg if killpg is None else killpg
    register = signal.signal if register_signal is None else register_signal
    now = time.monotonic if clock is None else clock
    window_state = client_windows_present if window_probe is None else window_probe
    stop = []
    previous = {}

    def record_signal(signum, _frame):
        if not stop:
            stop.append(signum)

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous[signum] = register(signum, record_signal)
    seen_client = False
    idle_since = None
    cleanup_suppressed = False
    try:
        while child.poll() is None and not stop:
            # Learn the guest namespace while the session runs: after a crash
            # the processes that still carry the socket may be the only proof.
            if namespace is None:
                namespace = prefix_namespace(prefix, proc_root)
            if stop_after > 0:
                if not owns_runtime:
                    idle_since = None
                    sleep(poll)
                    continue
                current_time = now()
                try:
                    windows = window_state()
                except Exception:
                    windows = None
                try:
                    game = game_running(prefix, proc_root)
                except Exception:
                    game = None
                seen_client, idle_since, stop_now = idle_decision(
                    seen_client, idle_since, current_time, windows, game, stop_after)
                if stop:
                    break
                if stop_now:
                    # Idle stopping is opt-in and only applies to a runtime
                    # this supervisor observed itself starting.
                    if not safe_to_stop(prefix, proc_root, window_state):
                        idle_since = None
                        sleep(poll)
                        continue
                    if stop:
                        break
                    log('client window has been gone for %ds; stopping the session'
                        % stop_after, out)
                    if child.poll() is None:
                        try:
                            send_group(child.pid, signal.SIGTERM)
                        except OSError:
                            pass
                        deadline = now() + TERM_GRACE
                        while (child.poll() is None and now() < deadline
                               and not stop):
                            sleep(poll)
                        if stop:
                            break
                        still_safe = safe_to_stop(prefix, proc_root, window_state)
                        if stop:
                            break
                        if not still_safe:
                            # A veto after TERM ends this automatic stop
                            # attempt; neither KILL nor guest cleanup follows.
                            cleanup_suppressed = True
                            idle_since = None
                            if child.poll() is None:
                                sleep(poll)
                                continue
                        elif child.poll() is None:
                            # Recheck the leader immediately before killpg.
                            if child.poll() is None:
                                try:
                                    send_group(child.pid, signal.SIGKILL)
                                except OSError:
                                    pass
                            break
                        else:
                            break
            sleep(poll)
        if not stop:
            code = child.wait()
            # The loader can exit while the match keeps running, for example
            # when the Riot Client is closed in game. Wait for the match, not
            # the loader. Unknown game state skips waiting, but the cleanup
            # gate below will preserve the session unless both probes are clear.
            if not stop and owns_runtime and game_running(prefix, proc_root) is True:
                log('loader exited during a match; waiting for the game to end', out)
                namespace = namespace or prefix_namespace(prefix, proc_root)
                while not stop and game_running(prefix, proc_root) is True:
                    sleep(poll)

        if stop:
            signum = stop[0]
            if not owns_runtime or not safe_to_stop(prefix, proc_root, window_state):
                log('interrupted by signal %d; detaching to preserve the session'
                    % signum, out)
                return 128 + signum

            # The handler only records the request. Signal the child group here,
            # after checking both safety probes and the leader's liveness.
            if child.poll() is None:
                try:
                    send_group(child.pid, signal.SIGTERM)
                except OSError:
                    pass
                deadline = now() + TERM_GRACE
                while child.poll() is None and now() < deadline:
                    sleep(poll)

                # Recheck after TERM even if the leader exited: a veto means
                # detach, with no blocking wait or guest cleanup.
                if not safe_to_stop(prefix, proc_root, window_state):
                    log('interrupted by signal %d; safety changed, detaching'
                        % signum, out)
                    return 128 + signum
                if child.poll() is None:
                    # The group leader must still be live immediately before
                    # escalating. The procfs-to-killpg gap is not atomic.
                    if child.poll() is None:
                        try:
                            send_group(child.pid, signal.SIGKILL)
                        except OSError:
                            pass
            code = child.wait()
    finally:
        for signum, handler in previous.items():
            register(signum, handler)
    if not owns_runtime:
        log('another session owns this runtime; leaving it running', out)
        remaining = []
    elif cleanup_suppressed:
        log('cleanup skipped after a safety veto', out)
        remaining = None
    else:
        namespace = namespace or prefix_namespace(prefix, proc_root)
        remaining = cleanup(prefix, darling, namespace, proc_root=proc_root, run=run,
                            kill=kill, sleep=sleep, out=out,
                            own_namespace=own_namespace,
                            window_probe=window_state)
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
    return run_supervised(command, prefix, args.darling, stop_after=max(0, args.stop_after),
                          clean=clean)


if __name__ == '__main__':
    sys.exit(main())
