#!/usr/bin/env python3
"""Watch the practice game clock; preserve thread waits if progress stops.

Does not attach a debugger or record credentials, arguments, or environments.
"""
import argparse
import json
from pathlib import Path
import ssl
import subprocess
import time
import urllib.request


def roles():
    result = {}
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            name = (proc / 'cmdline').read_bytes().split(b'\0', 1)[0].rsplit(b'/', 1)[-1].decode()
            if name in ('LeagueofLegends', 'LeagueClient', 'darlingserver'):
                result[name] = int(proc.name)
        except (OSError, UnicodeError):
            pass
    return result


def snapshot(out, processes):
    (out / 'roles.json').write_text(json.dumps(processes, indent=2))
    rows = []
    for role, pid in processes.items():
        for task in Path(f'/proc/{pid}/task').glob('*'):
            row = {'role': role, 'tid': int(task.name)}
            for field in ('comm', 'stat', 'wchan', 'syscall', 'stack'):
                try:
                    row[field] = (task / field).read_text().strip()
                except OSError as error:
                    row[field] = str(error)
            rows.append(row)
        try:
            (out / f'{role}-maps.txt').write_text(Path(f'/proc/{pid}/maps').read_text())
        except OSError:
            pass
    (out / 'thread-waits.json').write_text(json.dumps(rows, indent=2))
    # Sample only after a stall has been detected, so capture cannot trigger it.
    with (out / 'perf-errors.txt').open('w') as errors:
        subprocess.run(['perf', 'record', '-q', '-e', 'cpu-clock', '-F', '99',
                        '-g', '--call-graph', 'dwarf,8192', '-p',
                        ','.join(map(str, processes.values())), '-o', str(out / 'stall.perf'),
                        '--', 'sleep', '8'], stderr=errors, timeout=20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    context = ssl._create_unverified_context()
    last_clock = None
    last_progress = time.monotonic()
    deadline = last_progress + args.seconds
    seen_game = False
    with (args.out / 'progress.jsonl').open('w') as log:
        while time.monotonic() < deadline:
            state = {'monotonic': time.monotonic(), 'processes': roles()}
            seen_game |= 'LeagueofLegends' in state['processes']
            try:
                with urllib.request.urlopen('https://127.0.0.1:2999/liveclientdata/gamestats',
                                            context=context, timeout=2) as response:
                    state['clock'] = json.load(response)['gameTime']
                if last_clock is None or state['clock'] > last_clock:
                    last_progress = time.monotonic()
                last_clock = state['clock']
            except Exception as error:
                state['error'] = type(error).__name__
            log.write(json.dumps(state) + '\n')
            log.flush()
            if seen_game and last_clock is not None and time.monotonic() - last_progress > 20:
                if 'LeagueofLegends' not in state['processes']:
                    state['result'] = 'game exited'
                elif 'error' in state:
                    state['result'] = 'game API stopped responding'
                else:
                    state['result'] = 'clock unchanged (check whether the game is paused)'
                (args.out / 'result.json').write_text(json.dumps(state, indent=2))
                snapshot(args.out, state['processes'])
                print(state['result'], flush=True)
                return 1
            time.sleep(3)
    result = {'result': 'completed', 'last_clock': last_clock, 'seen_game': seen_game}
    (args.out / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    return 0 if seen_game and last_clock is not None else 2


if __name__ == '__main__':
    raise SystemExit(main())
