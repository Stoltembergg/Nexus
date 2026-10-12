#!/usr/bin/env python3
"""One-shot performance capture for a running League game (run it while a match is live).

Records, over --seconds (default 30): the in-game clock before/after (Live Client Data API on
127.0.0.1:2999, to prove the match was not paused), per-thread CPU of the game, a user-space
`perf record` of the game's main thread and of darlingserver, and prints the top symbols by
dso/symbol for each. Output goes to --out (default /tmp/game-perf-<time>). Read-only: it only
samples; it never attaches a debugger/ptrace (perf uses the sampling PMU/software clock, and
perf_event_paranoid=2 restricts it to user space of our own processes).
"""
import argparse, json, os, re, subprocess, sys, time, urllib3
from pathlib import Path
import requests

urllib3.disable_warnings()
GAME_MARK = 'LeagueOfLegends.app/Contents/MacOS/LeagueofLegends'


def find_pids(match, exclude=()):
    out = []
    for p in Path('/proc').iterdir():
        if p.name.isdigit():
            try:
                cmd = (p / 'cmdline').read_bytes().split(b'\0', 1)[0].decode(errors='replace')
            except OSError:
                continue
            if match.casefold() in cmd.casefold() and not any(e in cmd for e in exclude):
                out.append(int(p.name))
    return out


def game_clock():
    try:
        r = requests.get('https://127.0.0.1:2999/liveclientdata/gamestats', verify=False, timeout=3)
        return r.json().get('gameTime')
    except Exception:
        return None


def thread_cpu(pid):
    ticks = {}
    for t in Path(f'/proc/{pid}/task').iterdir():
        try:
            f = (t / 'stat').read_text()
            name = f[f.index('(') + 1:f.rindex(')')]
            rest = f[f.rindex(')') + 2:].split()
            ticks[int(t.name)] = (name, int(rest[11]) + int(rest[12]), int(rest[11]), int(rest[12]))
        except (OSError, ValueError):
            pass
    return ticks


def gpu_time(pid):
    """DRM engine time for this process, counting duplicate device FDs once."""
    engines, clients = {}, set()
    for fd in Path(f'/proc/{pid}/fdinfo').glob('*'):
        try:
            contents = fd.read_text()
        except OSError:
            continue
        client = re.search(r'^drm-client-id:\s*(\d+)', contents, re.M)
        device = re.search(r'^drm-pdev:\s*(\S+)', contents, re.M)
        if not client:
            continue
        key = (device[1] if device else '', client[1])
        if key in clients:
            continue
        clients.add(key)
        for engine, nanoseconds in re.findall(r'^drm-engine-(\S+):\s*(\d+) ns', contents, re.M):
            engines[engine] = engines.get(engine, 0) + int(nanoseconds)
    return engines


def power_state():
    state = {'cpu_policies': {}, 'power_supplies': {}}
    for policy in Path('/sys/devices/system/cpu/cpufreq').glob('policy*'):
        values = {}
        for name in ('scaling_max_freq', 'scaling_governor', 'scaling_cur_freq', 'energy_performance_preference'):
            try:
                values[name] = (policy / name).read_text().strip()
            except OSError:
                pass
        state['cpu_policies'][policy.name] = values
    for supply in Path('/sys/class/power_supply').glob('*'):
        try:
            state['power_supplies'][supply.name] = (supply / 'online').read_text().strip()
        except OSError:
            pass
    return state


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seconds', type=int, default=30)
    ap.add_argument('--out', type=Path, default=Path(f'/tmp/game-perf-{time.strftime("%H%M%S")}'))
    ap.add_argument('--top', type=int, default=25)
    args = ap.parse_args()

    games = find_pids(GAME_MARK, exclude=('CrashHandler',))
    servers = [p for p in find_pids('darlingserver') if Path(f'/proc/{p}/exe').exists()
               and os.readlink(f'/proc/{p}/exe').endswith('darlingserver')]
    if not games:
        sys.exit('no running game process (LeagueofLegends); start a match first')
    game = games[0]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f'game pid {game}, darlingserver pids {servers}, out {args.out}')

    clock0 = game_clock()
    cpu0, gpu0, power0, t0 = thread_cpu(game), gpu_time(game), power_state(), time.monotonic()
    perfs = [('game-main', subprocess.Popen(
        ['perf', 'record', '-q', '-F', '499', '-g', '-t', str(game), '-o', str(args.out / 'game-main.data'),
         '--', 'sleep', str(args.seconds)], stderr=subprocess.DEVNULL))]
    for s in servers[:1]:
        perfs.append(('darlingserver', subprocess.Popen(
            ['perf', 'record', '-q', '-F', '499', '-g', '-p', str(s), '-o', str(args.out / 'darlingserver.data'),
             '--', 'sleep', str(args.seconds)], stderr=subprocess.DEVNULL)))
    for _, p in perfs:
        p.wait()
    wall = time.monotonic() - t0
    if not Path(f'/proc/{game}').exists():
        sys.exit('game exited during capture; no valid performance comparison')
    cpu1, gpu1, clock1 = thread_cpu(game), gpu_time(game), game_clock()
    hz = os.sysconf('SC_CLK_TCK')

    summary = {'game_clock_before': clock0, 'game_clock_after': clock1, 'wall_s': round(wall, 1)}
    summary['game_gpu_engine_pct'] = {engine: round((value - gpu0[engine]) / (wall * 1e9) * 100, 1)
                                      for engine, value in gpu1.items() if engine in gpu0}
    summary['power_before'] = power0
    summary['power_after'] = power_state()
    if clock0 is None or clock1 is None:
        summary['clock_note'] = 'Live Client Data API unreachable: cannot confirm the match was running'
    elif clock1 - clock0 < wall * 0.8:
        summary['clock_note'] = 'GAME CLOCK DID NOT ADVANCE IN REAL TIME: measurement invalid (paused?)'
    threads = sorted(((cpu1[t][1] - cpu0.get(t, (0, 0))[1]) / hz / wall * 100, t, cpu1[t][0])
                     for t in cpu1)[::-1][:8]
    summary['threads_cpu_pct'] = [(round(c), tid, name) for c, tid, name in threads]
    summary['main_cpu_pct'] = {
        'user': round((cpu1[game][2] - cpu0[game][2]) / hz / wall * 100, 1),
        'kernel': round((cpu1[game][3] - cpu0[game][3]) / hz / wall * 100, 1),
    }
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))

    for name, _ in perfs:
        data = args.out / f'{name}.data'
        for sort in ('dso,sym',):
            r = subprocess.run(['perf', 'report', '-i', str(data), '--no-children', '--stdio', '-g', 'none',
                                '--sort', sort, '--percent-limit', '1'],
                               capture_output=True, text=True)
            lines = [l for l in r.stdout.splitlines() if l.strip() and not l.startswith('#')][:args.top]
            print(f'\n== {name} top ({sort}) ==')
            print('\n'.join(lines))


if __name__ == '__main__':
    main()
