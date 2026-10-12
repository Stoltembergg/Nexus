#!/usr/bin/env python3
"""Measure what each League graphics setting costs in the Baron fight (one change at a time).

  settings-ab.py [label ...]       default: all. Restarts the game per configuration (tools/baron-up.sh), runs the
                                   Baron workload twice, prints fps/mean/p99. game.cfg is backed up and restored.
Output also goes to /tmp/settings-ab.out. Not a quality recommendation: it only measures cost."""
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path
root = Path(__file__).resolve().parent.parent
os.chdir(root)
cfg = Path.home() / '.darling/Applications/League of Legends.app/Contents/LoL/Config/game.cfg'
backup = Path('/tmp/game.cfg.settings-ab.orig')
shutil.copy2(cfg, backup)
CONFIGS = {
    'medium (current)': {},
    'FXAA off': {'EnableFXAA': '0'},
    'god rays off': {'ShowGodray': '0'},
    'hide eye candy': {'HideEyeCandy': '1'},
    'shadows low': {'ShadowQuality': '1'},
    'shadows off': {'ShadowQuality': '0'},
    'effects low': {'EffectsQuality': '1'},
    'character low': {'CharacterQuality': '1'},
    'environment low': {'EnvironmentQuality': '1'},
}
want = sys.argv[1:] or list(CONFIGS)
env = os.environ.copy(); env.pop('ELECTRON_RUN_AS_NODE', None)
out = open('/tmp/settings-ab.out', 'a')
def say(msg):
    print(msg, flush=True); out.write(msg + '\n'); out.flush()
def apply(changes):
    text = backup.read_text()
    for k, v in changes.items():
        text, n = re.subn(r'(?m)^%s=.*$' % re.escape(k), '%s=%s' % (k, v), text)
        if n == 0:
            text = text.replace('[General]\n', '[General]\n%s=%s\n' % (k, v), 1)
    cfg.write_text(text)
def run_workload():
    p = subprocess.run([sys.executable, '-I', 'tools/baron-workload.py', '--seconds', '20'], capture_output=True, text=True)
    try:
        return json.loads(p.stdout[p.stdout.index('{'):p.stdout.rindex('}') + 1])
    except ValueError:
        return None
try:
    for label in want:
        apply(CONFIGS[label])
        up = subprocess.run(['sh', 'tools/baron-up.sh'], capture_output=True, text=True, env=env)
        time.sleep(5)
        res = []
        for _ in range(2):
            newest = max((f.stat().st_mtime for f in (Path.home() / '.darling/tmp').glob('metal-present-intervals*.csv')), default=0)
            if time.time() - newest > 45:
                subprocess.run(['darling', 'shell', 'sh', '-c', 'touch /tmp/metal-frame-interval-repeat'], env=env, stdout=subprocess.DEVNULL, timeout=90)
                time.sleep(20)
            r = run_workload()
            if r: res.append(r)
        if res:
            say('%-18s fps %s   mean %s ms   p99 %s ms' % (label, [r['fps'] for r in res], [r['mean_ms'] for r in res], [r['p99_ms'] for r in res]))
        else:
            say('%-18s no result (%s)' % (label, up.stdout[-120:].strip()))
finally:
    shutil.copy2(backup, cfg)
    say('game.cfg restored')
