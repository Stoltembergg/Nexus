#!/usr/bin/env python3
"""Stationary-scene fight A/B: every case starts from a fresh Baron (tools/baron-reset.py), runs the same 20 s stationary
workload and is rejected if the player died / Baron vanished. Cases are guest flag files toggled between runs.
  fight-ab.py NAME [--rounds 2] A_cmd B_cmd     e.g. 'rm -f /tmp/metal-no-binding-reuse' 'touch /tmp/metal-no-binding-reuse'
Order is A B B A ... (ABBA) per round. Writes logs/fight-ab/<NAME>.json and prints a summary."""
import json, subprocess, sys, time, os, statistics, requests, urllib3
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); os.chdir(root)
urllib3.disable_warnings()
name, a_cmd, b_cmd = sys.argv[1], sys.argv[-2], sys.argv[-1]
rounds = int(sys.argv[sys.argv.index('--rounds') + 1]) if '--rounds' in sys.argv else 2
env = os.environ.copy(); env.pop('ELECTRON_RUN_AS_NODE', None)
def guest(c): subprocess.run(['timeout', '-k', '2', '20', 'darling', 'shell', 'sh', '-c', c], env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
def clock(): return requests.get('https://127.0.0.1:2999/liveclientdata/gamestats', verify=False, timeout=4).json()['gameTime']
def alive():
    r = requests.get('https://127.0.0.1:2999/liveclientdata/playerlist', verify=False, timeout=4).json()
    return not r[0].get('isDead', False)
os.makedirs('logs/fight-ab', exist_ok=True); rows = []
order = ['A', 'B', 'B', 'A'] * ((rounds + 1) // 2)
order = order[:rounds * 2]
for i, c in enumerate(order):
    guest(a_cmd if c == 'A' else b_cmd)
    for attempt in range(4):
        try: clock()
        except Exception: sys.exit('game is gone: aborting')
        r = subprocess.run(['python3', '-I', 'tools/baron-reset.py']); time.sleep(16)
        guest('touch /tmp/metal-frame-interval-repeat'); t0 = clock()
        p = subprocess.run(['python3', '-I', 'tools/baron-workload.py', '--stationary', '--require-baron', '--seconds', '18'],
                           capture_output=True, text=True)
        ok = p.returncode == 0 and clock() > t0 and alive()
        if ok: break
        print(f'case {i} {c}: invalid (attempt {attempt}): {p.stderr.strip()[-120:]}', flush=True)
    else:
        print('giving up'); break
    d = json.loads(p.stdout[p.stdout.find('{'):]); d['case'] = c; d['idx'] = i; rows.append(d)
    print(i, c, d['fps'], 'p50', d['p50_ms'], 'p99', d['p99_ms'], flush=True)
json.dump(rows, open(f'logs/fight-ab/{name}.json', 'w'), indent=1)
for c in 'AB':
    v = [r for r in rows if r['case'] == c]
    if v: print(c, 'fps', statistics.mean(r['fps'] for r in v), 'p99', statistics.mean(r['p99_ms'] for r in v), 'n', len(v))
guest(a_cmd)
