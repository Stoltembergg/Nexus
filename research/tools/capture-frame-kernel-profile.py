#!/usr/bin/env python3
"""Bounded, read-only kernel profiling for the currently running League match.
Run with sudo; never reads application arguments, environment or memory.
"""
from pathlib import Path
import os, subprocess, json, time, sys, urllib.request, ssl, argparse
root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cpu-only', action='store_true')
parser.add_argument('--out', type=Path, help='New output directory; existing evidence is never overwritten')
args = parser.parse_args()
cpu_only = args.cpu_only
out = root / (args.out if args.out is not None else Path('logs/profile-20261009-frame-cost/cpu-only' if cpu_only else 'logs/profile-20261009-frame-cost/kernel'))
if os.geteuid() != 0:
    raise SystemExit('Run with sudo: kernel and scheduling events require root')
roles = {}
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        argv0 = (p / 'cmdline').read_bytes().split(b'\0', 1)[0].decode(errors='replace')
        name = argv0.rsplit('/', 1)[-1]
        if name in ('LeagueofLegends', 'LeagueClient', 'darlingserver'):
            roles[name] = int(p.name)
    except OSError:
        pass
if 'LeagueofLegends' not in roles or 'darlingserver' not in roles:
    raise SystemExit('No live game/server; nothing captured')
if out.exists():
    raise SystemExit('Output already exists; refusing to overwrite evidence')
out.mkdir(mode=0o700)
game = roles['LeagueofLegends']
(out / 'roles.json').write_text(json.dumps(roles, indent=2))
(out / 'kallsyms.txt').write_text(Path('/proc/kallsyms').read_text())
for role, pid in roles.items():
    (out / (role + '-maps.txt')).write_text(Path(f'/proc/{pid}/maps').read_text())
# Main-thread trace filters capture syscall duration and why the thread stops
# running. Kernel/user CPU samples cover all threads of these processes.
trace = ['perf', 'record', '-q', '-a', '--clockid', 'mono', '-o', str(out / 'waits.data'),
         '-e', 'sched:sched_switch', '--filter', f'prev_pid == {game} || next_pid == {game}',
         '-e', 'sched:sched_wakeup', '--filter', f'pid == {game}',
         '-e', 'raw_syscalls:sys_enter', '--filter', f'common_pid == {game}',
         '-e', 'raw_syscalls:sys_exit', '--filter', f'common_pid == {game}',
         '--', 'sleep', '20']
samples = ['perf', 'record', '-q', '--clockid', 'mono', '-e', 'cpu-clock', '-F', '199', '-g',
           '-p', ','.join(str(x) for x in roles.values()), '-o', str(out / 'cpu.data'),
           '--', 'sleep', '20']
def state():
    result = {'wall_time': time.time(), 'monotonic': time.monotonic()}
    try:
        with urllib.request.urlopen('https://127.0.0.1:2999/liveclientdata/gamestats', context=ssl._create_unverified_context(), timeout=3) as response:
            result['game_clock'] = json.load(response).get('gameTime')
    except Exception:
        result['game_clock'] = None
    result['cpu_frequencies_khz'] = {p.parent.name: p.read_text().strip() for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_cur_freq')}
    return result
before = state()
try:
    with (out / 'errors.txt').open('w') as errors:
        children = [subprocess.Popen(cmd, stderr=errors) for cmd in ((samples,) if cpu_only else (trace, samples))]
        codes = [child.wait(timeout=35) for child in children]
    (out / 'exit-codes.json').write_text(json.dumps(codes))
    (out / 'state.json').write_text(json.dumps({'before': before, 'after': state()}, indent=2))
    print('Kernel capture complete:', out, 'exit codes:', codes)
finally:
    uid, gid = int(os.environ.get('SUDO_UID', '0')), int(os.environ.get('SUDO_GID', '0'))
    for p in out.iterdir():
        os.chmod(p, 0o600)
        os.chown(p, uid, gid)
    os.chown(out, uid, gid)
