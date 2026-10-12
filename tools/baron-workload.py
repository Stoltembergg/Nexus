#!/usr/bin/env python3
"""Baron-pit fight workload with real input, and the frame statistics of exactly that window.

  baron-workload.py [--seconds 40]
Needs: practice match, champion near Baron, practice refresh toggles on (see tools/uinput_click.py and the panel notes in
memory), match launched with CYCLE_FRAME_INTERVALS=1. Bindings of this setup: ZQSD move, left click targets/attacks, abilities are MB2 (right
click), LShift, E, R. Attacks Baron in place and taps Q/D to jiggle inside the pit, then reads ~/.darling/tmp/metal-present-intervals*.csv for the window. Stops if focus leaves the game.
"""
import argparse, csv, glob, json, math, os, statistics, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uinput_click import Mouse, hover, BTN_LEFT, BTN_RIGHT

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=40)
parser.add_argument('--window-out', help='save workload monotonic timestamps for profile/overlap validation')
parser.add_argument('--autoattack', action='store_true', help='only left-click Baron (auto attacks), no abilities or movement')
parser.add_argument('--idle', action='store_true', help='no input: measure the scene as it stands')
parser.add_argument('--hover', action='store_true', help='keep the cursor on Baron (outline on), no clicks or keys')
parser.add_argument('--warmup', action='store_true', help='run the workload without collecting or reporting frame statistics')
parser.add_argument('--require-baron', action='store_true', help='reject an empty or misplaced fight scene instead of using a fallback aim point')
parser.add_argument('--stationary', action='store_true', help='spam abilities without movement-key taps for repeatable A/B')
parser.add_argument('--abilities-only', action='store_true', help='cast abilities without target clicks (stability stress outside the Baron pit)')
args = parser.parse_args()


def baron_hp_percent():
    """Fill of the target frame's health bar (top-left, appears once Baron is targeted); None when not visible."""
    try:
        import io
        from PIL import Image
        png = subprocess.run(['grim', '-g', '0,0 260x90', '-'], capture_output=True, check=True).stdout
        img = Image.open(io.BytesIO(png)).convert('RGB')
        px = img.load()
        best = None
        for y in range(24, 40):
            red = [x for x in range(130, 240) if px[x, y][0] > 140 and px[x, y][1] < 80 and px[x, y][2] < 80]
            if red and (best is None or len(red) > best):
                best = len(red)
        return best
    except Exception:
        return None


def locate_baron():
    """Screen position of Baron's body: from the overhead health bar (red segments, ~175 px wide). None if not found."""
    try:
        import io
        from PIL import Image
        png = subprocess.run(['grim', '-g', '0,0 1920x1080', '-'], capture_output=True, check=True).stdout
        px = Image.open(io.BytesIO(png)).convert('RGB').load()
        best = None
        for y in range(20, 760, 1):
            xs = [x for x in range(260, 1650) if px[x, y][0] > 120 and px[x, y][1] < 80 and px[x, y][2] < 80 and px[x, y][0] > 2 * px[x, y][1]]
            # Red scenery/effects elsewhere on the same scanline must not
            # expand the health bar into a screen-wide false candidate.
            groups = []
            for x in xs:
                if not groups or x - groups[-1][-1] > 4:
                    groups.append([x])
                else:
                    groups[-1].append(x)
            for group in groups:
                width = group[-1] - group[0]
                if 120 <= width <= 260 and len(group) >= 60 and (best is None or len(group) > best[0]):
                    best = (len(group), y, group[0], group[-1])
        if best is None:
            return None
        _, y, x0, x1 = best
        if not 120 <= x1 - x0 <= 260:
            return None
        return ((x0 + x1) // 2, y + 190)
    except Exception:
        return None

def focused():
    return json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j'])).get('class') == 'LeagueofLegends'

if not focused():
    sys.exit('game is not focused')
subprocess.run(['xdotool', 'keyup', 'Alt_L', 'Alt_R', 'Control_L', 'Control_R', 'Shift_L', 'Shift_R'])
hp_start = baron_hp_percent()
BARON = locate_baron()
if args.require_baron and BARON is None:
    sys.exit('Baron health bar not found: refusing to measure an empty fight scene')
BARON = BARON or (620, 400)
mouse = Mouse()
print('baron aim point', BARON, file=sys.stderr)   # Baron body on screen with the camera as left by baron-setup.py (champion stands on it)
start = time.monotonic_ns()
cycle = 0
try:
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        if args.idle:
            time.sleep(0.5); continue
        if args.hover:
            hover(BARON[0] + (cycle % 3 - 1) * 12, BARON[1] + (cycle % 2) * 10, settle=0.04); time.sleep(0.25); cycle += 1; continue
        if not focused():
            print('focus changed: stopping'); break
        x, y = BARON[0] + (cycle % 3 - 1) * 40, BARON[1] + (cycle % 2) * 30
        hover(x, y, settle=0.04)
        if not args.abilities_only:
            mouse.click(2, hold=0.04, gap=0.06, button=BTN_LEFT)    # target / attack Baron
        if args.autoattack:
            time.sleep(0.4); cycle += 1; continue
        if not args.stationary and not args.abilities_only:
            mouse.click(1, hold=0.04, gap=0.05, button=BTN_RIGHT)   # MB2 is Kindred's dash; omit it in stationary runs
        for key in ('Shift_L', 'e', 'r'):
            subprocess.run(['xdotool', 'key', '--delay', '60', key], check=True)
            time.sleep(0.04)
        # Optional movement; stationary runs keep the target and camera stable across A/B cases.
        if not args.stationary and not args.abilities_only:
            subprocess.run(['xdotool', 'keydown', 'q' if cycle % 2 else 'd']); time.sleep(0.12)
            subprocess.run(['xdotool', 'keyup', 'q' if cycle % 2 else 'd'])
        else:
            time.sleep(0.12)
        cycle += 1
finally:
    mouse.close()
hp_end = baron_hp_percent()
if args.require_baron and locate_baron() is None:
    sys.exit('Baron health bar disappeared: refusing to report a fight FPS result')
end = time.monotonic_ns()
if args.window_out:
    from pathlib import Path
    Path(args.window_out).write_text(json.dumps({'start_ns':start,'end_ns':end,'cycles':cycle})+'\n')
if args.warmup:
    sys.exit(0)
# the recorder only writes complete 2048-frame blocks: keep the game rendering until one past `end` is on disk
deadline = time.monotonic() + 75
while time.monotonic() < deadline:
    newest = 0
    for path in glob.glob(os.path.expanduser('~/.darling/tmp/metal-present-intervals*.csv')):
        try:
            with open(path) as handle:
                rows = handle.read().splitlines()
            if len(rows) > 1:
                newest = max(newest, int(rows[-1].split(',')[0]))
        except (OSError, ValueError):
            pass
    if newest >= end:
        break
    time.sleep(2)
if newest < end:
    sys.exit('recorder did not cover the end of the workload: refusing a partial result')
times = set()
for path in glob.glob(os.path.expanduser('~/.darling/tmp/metal-present-intervals*.csv')):
    for row in csv.DictReader(open(path)):
        t = int(row['queued_ns'])
        if start <= t <= end:
            times.add(t)
t = sorted(times)
if len(t) < 100:
    sys.exit('only %d frame timestamps in the window (recorder armed? CYCLE_FRAME_INTERVALS=1)' % len(t))
iv = sorted((b - a) / 1e6 for a, b in zip(t, t[1:]))
mean = statistics.mean(iv)
print(json.dumps(dict(frames=len(t), seconds=round((t[-1] - t[0]) / 1e9, 1), fps=round(1000 / mean, 1), mean_ms=round(mean, 2),
                      p50_ms=round(iv[len(iv) // 2], 2), p95_ms=round(iv[math.ceil(len(iv) * .95) - 1], 2),
                      p99_ms=round(iv[math.ceil(len(iv) * .99) - 1], 2), worst_ms=round(iv[-1], 2),
                      fps_1pct_low=round(1000 / iv[math.ceil(len(iv) * .99) - 1], 1),
                      baron_hp_bar_px_start=hp_start, baron_hp_bar_px_end=hp_end), indent=1))
