#!/usr/bin/env python3
"""Limit client UI CPU contention while the focused match is running.

Chromium browser/GPU/renderer processes keep running but share a CPU quota (a cgroup v2 cpu.max in the user's delegated
subtree, default 25% of one CPU for all of them together) while the game is focused: they are launched with the frame
limit off and otherwise burn ~200% CPU behind the game, which costs the game FPS (the APU is power-bound) and loads
darlingserver. The quota is lifted on focus loss, game exit or watcher shutdown. If no cgroup can be used, the threads are
pinned to one CPU instead. Never suspend communicating UI processes: SIGSTOP can leave black windows and timed-out IPC
when they resume.
"""
import atexit
import os
import signal
import sys
import time
from pathlib import Path

GAME = b'/Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends'
UI_COMMS = {'CrRendererMain', 'CrGpuMain', 'CrBrowserMain', 'Chrome_ChildIOT', 'Chrome_IOThread', 'CrUtilityMain'}
UI_MARKS = (b'LeagueClientUx', b'/Riot Client.app/Contents/Frameworks/Riot Client.app/')
GRACE_SECONDS = max(0, int(os.environ.get('RCLOL_UI_GRACE_SECONDS', '60')))
BACKGROUND_COMMS = ('vicinae-file-in',)
QUOTA_PERCENT = max(1, int(os.environ.get('RCLOL_UI_QUOTA_PERCENT', '25')))
CGROUP = Path(f'/sys/fs/cgroup/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/rclol-ui')
cgroup_state = {'usable': None, 'limited': False}
limited = {}  # (thread ID, start time) -> original CPU affinity
group_defaults = {}  # original leader mask, for newly inherited thread masks


def log(message):
    print(time.strftime('%H:%M:%S'), message, flush=True)


def scan():
    game, ui = None, []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / 'cmdline').read_bytes()
            comm = (entry / 'comm').read_text().strip()
        except OSError:
            continue
        argv0 = cmdline.split(b'\0', 1)[0]
        if GAME.lower() in argv0.lower() and b'CrashHandler' not in argv0:
            game = int(entry.name)
        elif comm in UI_COMMS and any(mark in argv0 for mark in UI_MARKS):
            ui.append(int(entry.name))
        elif comm.startswith(BACKGROUND_COMMS):
            # desktop background workers (file indexers) that spike to several cores every ~10 s: each burst costs the
            # game its share of the APU power budget (clock 2.9 -> 2.3 GHz) and showed up as periodic FPS dips
            ui.append(int(entry.name))
    return game, ui


def playable():
    """Throttle only while the player is actually using the game. Visibility
    alone is insufficient: a window can remain visible behind a focused client."""
    import json, ssl, subprocess, urllib.request
    try:
        active = json.loads(subprocess.run(['hyprctl', 'activewindow', '-j'], capture_output=True, text=True, timeout=3).stdout)
        if active.get('class') != 'LeagueofLegends':
            return False
        clients = json.loads(subprocess.run(['hyprctl', 'clients', '-j'], capture_output=True, text=True, timeout=3).stdout)
        if not any(c.get('class') == 'LeagueofLegends' and c.get('visible') and not c.get('hidden') for c in clients):
            return False
        context = ssl._create_unverified_context()
        def clock():
            with urllib.request.urlopen('https://127.0.0.1:2999/liveclientdata/gamestats', context=context, timeout=2) as r:
                return json.load(r)['gameTime']
        first = clock(); time.sleep(1.5); return clock() - first > 0.5
    except Exception:
        return False


def thread_identity(tid):
    # The start time prevents restoring a recycled thread ID.
    fields = Path(f'/proc/{tid}/stat').read_text().rsplit(')', 1)[1].split()
    return tid, fields[19]


def cgroup_set(limit):
    """Apply (True) or lift (False) the quota. Returns False when no cgroup can be used."""
    try:
        if cgroup_state['usable'] is False:
            return False
        CGROUP.mkdir(exist_ok=True)
        (CGROUP / 'cpu.max').write_text(f'{QUOTA_PERCENT * 1000} 100000' if limit else 'max 100000')
        cgroup_state['usable'] = True
        return True
    except OSError as error:
        if cgroup_state['usable'] is None:
            log(f'cpu quota cgroup not usable ({error}); pinning threads instead')
        cgroup_state['usable'] = False
        return False


def limit_ui_cgroup(pids):
    if not cgroup_set(True):
        return None
    moved = 0
    try:
        members = set((CGROUP / 'cgroup.procs').read_text().split())
    except OSError:
        members = set()
    for pid in pids:
        if str(pid) in members:
            continue
        try:
            (CGROUP / 'cgroup.procs').write_text(str(pid))
            moved += 1
        except OSError:
            continue
    first = not cgroup_state['limited']
    cgroup_state['limited'] = True
    return moved + (1 if first else 0)


def limit_ui(pids):
    added = limit_ui_cgroup(pids)
    if added is not None:
        return added
    added = 0
    for pid in pids:
        try:
            group = thread_identity(pid)
            inherited = group in group_defaults
            default = group_defaults.setdefault(group, os.sched_getaffinity(pid))
            tasks = list(Path(f'/proc/{pid}/task').iterdir())
        except OSError:
            continue
        for task in tasks:
            tid = int(task.name)
            try:
                key = thread_identity(tid)
                if key in limited:
                    continue
                original = os.sched_getaffinity(tid)
                # Match the existing worker mask, keeping clear of the game's
                # reserved main CPU. All client UI threads share its last CPU.
                restore = default if inherited and original == {max(default)} else original
                os.sched_setaffinity(tid, {max(original)})
                limited[key] = restore
                added += 1
            except (OSError, ValueError, IndexError):
                continue
    return added


def resume_all():
    if cgroup_state['limited']:
        cgroup_set(False)
        cgroup_state['limited'] = False
        log('lifted the client UI cpu quota')
    restored = 0
    for (tid, started), original in list(limited.items()):
        try:
            if thread_identity(tid) == (tid, started):
                os.sched_setaffinity(tid, original)
                restored += 1
        except (OSError, ValueError, IndexError):
            pass
    if limited:
        log(f'restored affinity of {restored} client/background threads')
    limited.clear()
    group_defaults.clear()


def main():
    atexit.register(resume_all)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))
    log('watching for a match')
    seen = {}  # game pid -> first time seen
    while True:
        game, ui = scan()
        if game:
            # Give the client UI time to finish loading before limiting it: limiting it right at game start (a
            # reconnect starts the game seconds after the client) left it stuck on a half-loaded error page.
            if time.monotonic() - seen.setdefault(game, time.monotonic()) < GRACE_SECONDS:
                time.sleep(2)
                continue
            if not playable():
                if limited or cgroup_state['limited']:
                    log('game not focused/visible/advancing: resuming client UI')
                    resume_all()
                time.sleep(2)
                continue
            added = limit_ui(ui)
            if added:
                log(f'game pid {game} focused: limited {added} client/background {"processes" if cgroup_state["limited"] else "threads"}')
        elif limited or cgroup_state['limited']:
            log('game exited')
            resume_all()
        time.sleep(2)


if __name__ == '__main__':
    main()
