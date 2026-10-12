#!/usr/bin/env python3
"""Analyze a tools/true-profile.sh capture: on-CPU and off-CPU (blocking) profiles of the game's main thread.

  analyze-profile.py <capture-dir> oncpu     perf-game.data  : self/inclusive time, kernel share, kernel hot paths with callers
  analyze-profile.py <capture-dir> offcpu    offcpu.data     : how long and where the main thread blocks (sleeping) or waits to run
Both write folded stacks (<capture-dir>/<mode>.folded, root;...;leaf, weighted) and, when `inferno-flamegraph` exists, an SVG.
Mach-O frames (the game, Darling libraries and frameworks) are resolved with the same Mach-O symbol-table reader as
tools/symbolize-macho-perf.py; kernel and ELF frames come from perf. No process memory is read.
"""
import bisect, collections, re, struct, subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parent
src = (root / 'symbolize-macho-perf.py').read_text()
ns = {}
exec('import argparse,bisect,collections,json,re,struct,subprocess\nfrom pathlib import Path\n' + src[src.index('class MachO'):src.index('p=argparse')], ns)
MachO = ns['MachO']

if len(sys.argv) < 3 or sys.argv[2] not in ('oncpu', 'offcpu'):
    sys.exit(__doc__)
cap = Path(sys.argv[1]); mode = sys.argv[2]
pids = dict(kv.split('=') for kv in (cap / 'pids.txt').read_text().split())
game = int(pids['game'])

maps = []
for line in (cap / 'game-maps.txt').read_text().splitlines():
    m = re.match(r'([0-9a-f]+)-([0-9a-f]+) \S+ ([0-9a-f]+) \S+ \S+\s+(.*)', line)
    if m:
        maps.append((int(m[1], 16), int(m[2], 16), int(m[3], 16), m[4]))
images = {}
raw_cache = {}

def macho_symbol(addr, path):
    key = (addr, path)
    if key in raw_cache:
        return raw_cache[key]
    if path not in images:
        try:
            images[path] = MachO(path)
        except (OSError, ValueError, struct.error):
            images[path] = None
    image = images[path]
    result = None
    if image:
        mapped = next((off + addr - lo for lo, hi, off, fp in maps if lo <= addr < hi and fp == path), None)
        if mapped is not None:
            r = image.resolve(mapped)
            if r:
                result = r[0]
    raw_cache[key] = result
    return result

demangled = {}
def demangle_all(names):
    todo = [n for n in names if n not in demangled]
    if not todo:
        return
    out = subprocess.run(['c++filt'], input='\n'.join(n[1:] if n.startswith('_') else n for n in todo) + '\n', capture_output=True, text=True).stdout.split('\n')
    for n, d in zip(todo, out):
        demangled[n] = d or n

FRAME = re.compile(r'^\s+([0-9a-f]+)\s+(.*)\s+\((.*)\)\s*$')
HEADER = re.compile(r'^(\S.*?)\s+(\d+)\s+(?:\[(\d+)\]\s+)?([\d.]+):\s+(?:\d+\s+)?(\S+):\s*(.*)$')

def short(path):
    return path.rsplit('/', 1)[-1]

def events():
    """yield (tid, time, event, rest, frames[(addr, sym, dso)]) in perf's time order"""
    cmd = ['perf', 'script', '-i', str(cap / ('perf-game.data' if mode == 'oncpu' else 'offcpu.data')), '--max-stack', '64',
           '--kallsyms', str(cap / 'kallsyms.txt')]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, errors='replace')
    cur = None
    for line in p.stdout:
        h = HEADER.match(line)
        if h:
            if cur:
                yield cur
            cur = [int(h[2]), float(h[4]), h[5], h[6], []]
            continue
        f = FRAME.match(line)
        if f and cur:
            cur[4].append((int(f[1], 16), f[2].strip(), f[3]))
    if cur:
        yield cur
    p.wait()

def is_kernel(dso):
    return dso.startswith('[kernel') or dso.startswith('[amdgpu') or (dso.startswith('[') and not dso.startswith('[unknown'))

def label_frames(frames):
    """leaf-first frames -> list of readable names (leaf-first)"""
    names = []
    for addr, sym, dso in frames:
        if dso.startswith('/') and '.darling' in dso or sym.startswith('[unknown]') and dso.endswith(('.dylib',)) or 'LeagueofLegends' in dso:
            s = macho_symbol(addr, dso)
            names.append((s or ('unsymbolized@%x' % addr), short(dso)))
        else:
            names.append((re.sub(r'\+0x[0-9a-f]+$', '', sym) if sym != '[unknown]' else 'unknown@%x' % addr, short(dso)))
    demangle_all([n for n, _ in names])
    return [(demangled.get(n, n), d) for n, d in names]

SCHED = re.compile(r'^(__traceiter_sched|__schedule|schedule|preempt_schedule|__cond_resched|io_schedule|schedule_timeout|schedule_hrtimeout|do_nanosleep|hrtimer_nanosleep|do_sys_)')

def fold_line(names, weight):
    return ';'.join((n.replace(';', ':') + ('' if d in ('kernel.kallsyms]', '') else '')) for n, d in reversed(names)) + ' %d' % weight

if mode == 'oncpu':
    self_ = collections.Counter(); incl = collections.Counter(); folded = collections.Counter(); kernel_leaf = collections.Counter()
    kcallers = collections.defaultdict(collections.Counter); total = 0; kernel_samples = 0
    for tid, t, ev, rest, frames in events():
        if tid != game or not frames:
            continue
        total += 1
        names = label_frames(frames)
        kern = is_kernel(frames[0][2])
        self_[names[0]] += 1
        for n in set(names):
            incl[n] += 1
        folded[tuple(names)] += 1
        if kern:
            kernel_samples += 1
            kernel_leaf[names[0][0]] += 1
            user = next((n for n, d in names if d.endswith('.dylib') or d == 'LeagueofLegends' or d.startswith('CoreFoundation') or d.startswith('AppKit')), '?')
            # first user frame that is not the syscall emulation itself
            u = next((f'{n} [{d}]' for (n, d), (a, s, dso) in zip(names, frames) if not is_kernel(dso) and d != 'libsystem_kernel.dylib'), '?')
            kcallers[names[0][0]][u] += 1
    out = (cap / 'oncpu.folded'); out.write_text('\n'.join(fold_line(list(k), v) for k, v in folded.items()) + '\n')
    print('main-thread on-CPU samples: %d (%.1f s at 999 Hz); kernel-mode samples: %d (%.1f%%)' % (total, total / 999, kernel_samples, 100 * kernel_samples / total))
    by_image = collections.Counter()
    for (name, image), count in self_.items():
        by_image[image] += count
    print('\n== self samples by image')
    for image, count in by_image.most_common(20):
        print('%5.1f%%  %s' % (100 * count / total, image))
    print('\n== top self (leaf) functions'); [print('%5.1f%%  %s [%s]' % (100 * c / total, n, d)) for (n, d), c in self_.most_common(22)]
    print('\n== top inclusive functions'); [print('%5.1f%%  %s [%s]' % (100 * c / total, n, d)) for (n, d), c in incl.most_common(36)]
    print('\n== kernel leaf functions and who calls them (first non-emulation user frame)')
    for k, c in kernel_leaf.most_common(10):
        print('%5.1f%%  %s' % (100 * c / total, k))
        for u, cc in kcallers[k].most_common(3):
            print('          %4.1f%%  <- %s' % (100 * cc / total, u[:130]))
else:
    # off-CPU: pair each switch-out of the main thread with its next switch-in
    pending = None; blocked = collections.Counter(); count = collections.Counter(); folded = collections.Counter()
    waits = collections.defaultdict(list); first = last = None
    state_time = collections.Counter()
    reasons = {}
    for tid, t, ev, rest, frames in events():
        if ev != 'sched:sched_switch':
            continue
        m = re.search(r'prev_pid=(\d+).*?prev_state=(\S+).*?next_pid=(\d+)', rest)
        if not m:
            continue
        prev, state, nxt = int(m[1]), m[2], int(m[3])
        if first is None:
            first = t
        last = t
        if prev == game:
            pending = (t, state, frames)
        if nxt == game and pending:
            t0, state0, frames0 = pending; pending = None
            dur = t - t0
            names = label_frames(frames0)
            kern = [n for (n, d), (a, s, dso) in zip(names, frames0) if is_kernel(dso)]
            reason = next((n for n in kern if not SCHED.match(n)), '?')
            # kernel path below the scheduler (leaf-first), up to the syscall entry
            path = []
            for n in kern:
                if SCHED.match(n):
                    continue
                if n in ('do_syscall_64', 'entry_SYSCALL_64_after_hwframe'):
                    break
                path.append(n)
            user = next((f'{n} [{d}]' for (n, d), (a, s, dso) in zip(names, frames0) if not is_kernel(dso) and d != 'libsystem_kernel.dylib'), '?')
            sysc = next((n for n in path if n.startswith(('__x64_sys_', '__ia32_sys_'))), '')
            rpc = next((n for (n, d) in (x for x in names) if n.startswith(('dserver_rpc_', 'mach_msg_overwrite', 'semaphore_', 'psynch_')) and 'hooks' not in n and 'explicit' not in n), '')
            chain = ' < '.join(f'{n}' for (n, d), (a_, s_, dso) in zip(names, frames0) if not is_kernel(dso) and d != 'libsystem_kernel.dylib')
            key = ('%s:%s' % ('run-queue' if state0.startswith('R') else 'sleep', (rpc or ' < '.join(path[:3]) or reason)), chain.split(' < ')[0] + ' <- ' + ' < '.join(chain.split(' < ')[1:5]))
            blocked[key] += dur; count[key] += 1
            state_time['runnable (preempted, waiting for a CPU)' if state0.startswith('R') else 'sleeping (blocked)'] += dur
            folded[tuple(names)] += int(dur * 1e6)
    window = (last - first) if first else 0
    print('window %.1f s; main thread off-CPU %.2f s: ' % (window, sum(state_time.values())) + ', '.join('%s %.2f s (%.1f%%)' % (k, v, 100 * v / window) for k, v in state_time.items()))
    (cap / 'offcpu.folded').write_text('\n'.join(fold_line(list(k), v) for k, v in folded.items()) + '\n')
    print('\n%7s %7s %8s %7s  %s' % ('total ms', 'calls', 'avg us', '%wall', 'blocking reason  <-  who asked (first non-emulation frame)'))
    for key, v in blocked.most_common(28):
        c = count[key]
        print('%8.0f %7d %8.0f %6.2f%%  %s\n%35s <- %s' % (v * 1e3, c, v / c * 1e6, 100 * v / window, key[0][:110], '', key[1][:150]))

svg = cap / (mode + '.svg')
folded_file = cap / (mode + '.folded')
if subprocess.run(['which', 'inferno-flamegraph'], capture_output=True).returncode == 0:
    with folded_file.open() as fin, svg.open('w') as fout:
        subprocess.run(['inferno-flamegraph', '--title', 'League main thread: ' + mode, '--countname', 'us' if mode == 'offcpu' else 'samples'], stdin=fin, stdout=fout)
    print('\nflame graph: %s' % svg)
