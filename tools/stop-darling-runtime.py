#!/usr/bin/env python3
"""Wait for Darling's old server to exit before rebuilding its namespace."""
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
prefix = Path(os.environ.get('DPREFIX', str(Path.home() / '.darling'))).expanduser()
sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_window_state import client_windows_present

GAME_NAME = 'LeagueofLegends'
SOCK_VARIABLE = b'__mldr_sockpath'

try:
    old_pid = int((prefix / '.init.pid').read_text().strip())
except (OSError, ValueError):
    old_pid = 0

def live(pid):
    if pid <= 0:
        return False
    try:
        state = next(line.split()[1] for line in (Path('/proc') / str(pid) / 'status').read_text().splitlines() if line.startswith('State:'))
        return state != 'Z'
    except (FileNotFoundError, ProcessLookupError, StopIteration):
        # A process can exit after status is opened but before it is read.
        return False

def process_identity(pid):
    try:
        return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None

def game_process_inventory():
    """Return True/False for this prefix, or None if /proc is inconclusive.

    Game identity alone is not enough: only the loader socket positively ties
    a game to this prefix. A candidate with unreadable/missing ownership data
    makes the inventory unknown rather than authorizing a shutdown.
    """
    proc_root = Path('/proc')
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    owner = prefix.resolve()
    for proc in entries:
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / 'comm').read_text().strip()
        except FileNotFoundError:
            if not proc.exists():
                continue
            comm = None
        except OSError:
            comm = None

        try:
            raw_command = (proc / 'cmdline').read_bytes()
        except FileNotFoundError:
            if not proc.exists():
                continue
            raw_command = None
        except OSError:
            raw_command = None

        names = [] if raw_command is None else [
            os.path.basename(os.fsdecode(part))
            for part in raw_command.split(b'\0') if part
        ]
        is_candidate = comm == GAME_NAME or (names and names[0] == GAME_NAME)
        if not is_candidate:
            # If both identity sources are inaccessible for a still-present
            # process, it is impossible to rule out a game process.
            if comm is None and raw_command is None and proc.exists():
                return None
            continue

        try:
            state = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            if state == 'Z':
                continue
            environment = (proc / 'environ').read_bytes().split(b'\0')
        except FileNotFoundError:
            if not proc.exists():
                continue
            return None
        except (OSError, IndexError):
            return None

        sockets = [item.split(b'=', 1)[1] for item in environment
                   if item.startswith(SOCK_VARIABLE + b'=')]
        if len(sockets) != 1:
            return None
        try:
            socket_path = Path(os.fsdecode(sockets[0]))
            if not socket_path.is_absolute():
                return None
            socket_owner = socket_path.parent.resolve()
        except (OSError, RuntimeError, ValueError):
            return None
        if socket_owner == owner:
            return True
        # A candidate positively attributed to another prefix is unrelated.
    return False

def require_safe_session_state():
    """Stop before mutation unless both process and window probes are clear."""
    if game_process_inventory() is not False:
        raise SystemExit('League game process present or process inventory unknown; runtime remains untouched')
    if client_windows_present(check_output=subprocess.check_output) is not False:
        raise SystemExit('Riot/League client window present or window state unknown; runtime remains untouched')

def riot_descendants(server_pid):
    # The host server and its guest init have different PID namespaces. Follow
    # ancestry while the server is alive, rather than comparing namespace IDs.
    pending = [server_pid]
    seen = set()
    result = {}
    while pending:
        pid = pending.pop()
        if pid in seen or pid <= 0:
            continue
        seen.add(pid)
        try:
            for children in (Path('/proc') / str(pid) / 'task').glob('*/children'):
                pending.extend(int(child) for child in children.read_text().split())
            mappings = (Path('/proc') / str(pid) / 'maps').read_text()
            if ('Electron Framework.framework/Versions/A/Electron Framework' in mappings or
                    '/Applications/Riot Client.app/' in mappings):
                result[pid] = process_identity(pid)
        except (OSError, ValueError):
            continue
    return result

def orphaned_riot():
    # A dead server marker cannot enumerate its former descendants. Recover
    # only same-user Riot mappings in this prefix with no live server ancestor.
    result = {}
    riot_path = str(prefix / 'Applications/Riot Client.app') + '/'
    league_path = str(prefix / 'Applications/League of Legends.app') + '/'
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            mappings = (entry / 'maps').read_text()
            if riot_path not in mappings and league_path not in mappings:
                continue
            pid = int(entry.name)
            ancestor = pid
            seen = set()
            has_server = False
            while ancestor > 1 and ancestor not in seen:
                seen.add(ancestor)
                proc = Path('/proc') / str(ancestor)
                if proc.joinpath('comm').read_text().strip() == 'darlingserver' and live(ancestor):
                    has_server = True
                    break
                fields = proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()
                ancestor = int(fields[1])
            if not has_server:
                result[pid] = process_identity(pid)
        except (OSError, ValueError, IndexError):
            continue
    return result

# These observations are inherently non-atomic: a game or window can appear
# immediately after a probe. Recheck before each later signal/escalation and
# before installing the runtime to narrow that race.
require_safe_session_state()
owned_riot = riot_descendants(old_pid)
owned_riot.update(orphaned_riot())
require_safe_session_state()
subprocess.run(['darling', 'shutdown'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
deadline = time.monotonic() + 5
while live(old_pid) and time.monotonic() < deadline:
    time.sleep(.1)
if live(old_pid):
    raise SystemExit(f'Darling server {old_pid} has not exited; runtime remains untouched')
# Shutdown can leave Electron helpers or League's startup window reparented
# and consuming CPU/GPU time.
# Stop the observed descendants and verified serverless Riot processes in this
# prefix, guarding against PID reuse. Leave other live Darling sessions alone.
for pid, identity in owned_riot.items():
    if identity is not None and process_identity(pid) == identity and live(pid):
        require_safe_session_state()
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
deadline = time.monotonic() + 3
while any(process_identity(pid) == identity and live(pid)
          for pid, identity in owned_riot.items()) and time.monotonic() < deadline:
    time.sleep(.1)
remaining = {pid: identity for pid, identity in owned_riot.items()
             if process_identity(pid) == identity and live(pid)}
# These helpers have no live server and ignored graceful termination. They
# cannot complete guest RPCs after shutdown. Kill only the previously observed
# Riot descendants, with the same PID/start-time guard used above.
for pid, identity in remaining.items():
    if process_identity(pid) == identity and live(pid):
        require_safe_session_state()
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
deadline = time.monotonic() + 5
while any(process_identity(pid) == identity and live(pid)
          for pid, identity in remaining.items()) and time.monotonic() < deadline:
    time.sleep(.1)
if any(process_identity(pid) == identity and live(pid) for pid, identity in remaining.items()):
    raise SystemExit('Old Riot helpers remain alive; runtime remains untouched')
require_safe_session_state()
subprocess.run([sys.executable, str(Path(__file__).with_name('ensure-darling-runtime.py'))], check=True)
