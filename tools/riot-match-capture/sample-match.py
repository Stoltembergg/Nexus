#!/usr/bin/env python3
"""Passive per-thread sampler for one League match.

Reads only /proc and /sys counters: scheduler statistics per thread and the
number (plus descriptor or futex operation) of the system call a thread is
blocked in. Nothing is attached to, written to, or injected into any process.

Waits for the game process to appear, samples until it exits, then stops.
"""
import argparse
import collections
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROC = Path("/proc")
GAME_SUFFIX = "/contents/macos/leagueoflegends"
FD_SYSCALLS = {0, 1, 7, 17, 18, 19, 20, 44, 45, 46, 47, 232, 281, 299, 307}
FUTEX = 202
MAIN_HZ = 50
OTHER_EVERY = 5


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def siblings():
    pair = {}
    for d in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/topology/thread_siblings_list"):
        cpu = int(d.parent.parent.name[3:])
        ids = []
        for part in read(d).split(","):
            lo, _, hi = part.partition("-")
            ids += range(int(lo), int(hi or lo) + 1)
        pair[cpu] = [i for i in ids if i != cpu]
    return pair


def stat_state(base):
    """Return (state, cpu) from a thread's stat file, or None."""
    text = read(base + "stat")
    fields = text[text.rfind(")") + 2:].split()
    try:
        return fields[0], int(fields[36])
    except (IndexError, ValueError):
        return None


def huge_pages(pid):
    values = {}
    for line in read("/proc/%d/smaps_rollup" % pid).splitlines():
        key, _, rest = line.partition(":")
        if key in ("Rss", "Anonymous", "AnonHugePages"):
            values[key + "_kb"] = int(rest.split()[0])
    return values


def find(kind):
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            exe = os.readlink(entry / "exe")
        except OSError:
            continue
        if kind == "server":
            if exe.split(" ")[0].endswith("darlingserver"):
                return int(entry.name)
            continue
        if "mldr" not in exe:
            continue
        arguments = read(entry / "cmdline").lower().split("\0")
        if any(a.endswith(GAME_SUFFIX) for a in arguments):
            return int(entry.name)
        if any(line.lower().endswith(GAME_SUFFIX) for line in read(entry / "maps").splitlines()):
            return int(entry.name)
    return None


class Thread:
    def __init__(self, pid, tid):
        self.tid = tid
        self.base = "/proc/%d/task/%d/" % (pid, tid)
        self.name = read(self.base + "comm")
        try:
            self.fd = os.open(self.base + "syscall", os.O_RDONLY)
        except OSError:
            self.fd = None
        self.sched = self.read_sched()
        self.faults = self.read_faults()
        self.counts = collections.Counter()

    def read_faults(self):
        text = read(self.base + "stat")
        fields = text[text.rfind(")") + 2:].split()
        try:
            return int(fields[7]), int(fields[9])  # minflt, majflt
        except (IndexError, ValueError):
            return None

    def read_sched(self):
        try:
            return [int(x) for x in read(self.base + "schedstat").split()]
        except ValueError:
            return None

    def sample(self):
        if self.fd is None:
            return True
        try:
            fields = os.pread(self.fd, 256, 0).split()
        except ProcessLookupError:
            return False
        except OSError:
            # Not readable for this process (e.g. the server); keep scheduler statistics only.
            self.close()
            self.fd = None
            return True
        if not fields:
            return False
        head = fields[0]
        if head == b"running":
            key = "running"
        elif head.lstrip(b"-").isdigit():
            number = int(head)
            key = str(number)
            if number in FD_SYSCALLS and len(fields) > 1:
                key += " fd=%d" % int(fields[1], 16)
            elif number == FUTEX and len(fields) > 2:
                key += " op=%d" % (int(fields[2], 16) & 0x7F)
        else:
            key = "other"
        self.counts[key] += 1
        return True

    def close(self):
        if self.fd is None:
            return
        try:
            os.close(self.fd)
        except OSError:
            pass


class Process:
    def __init__(self, pid):
        self.pid = pid
        self.threads = {}
        self.refresh()

    def refresh(self):
        try:
            tids = {int(x) for x in os.listdir("/proc/%d/task" % self.pid)}
        except OSError:
            return False
        for tid in tids - self.threads.keys():
            try:
                self.threads[tid] = Thread(self.pid, tid)
            except OSError:
                pass
        for tid in self.threads.keys() - tids:
            self.threads.pop(tid).close()
        return True

    def placement(self):
        states = {}
        for tid, thread in list(self.threads.items()):
            st = stat_state(thread.base)
            if st:
                states[tid] = st
        return states

    def sample(self, only=None):
        for tid in [only] if only else list(self.threads):
            thread = self.threads.get(tid)
            if thread and not thread.sample():
                self.threads.pop(tid).close()

    def flush(self):
        rows = {}
        for tid, thread in self.threads.items():
            new = thread.read_sched()
            row = {"name": thread.name, "syscall": dict(thread.counts)}
            faults = thread.read_faults()
            if faults and thread.faults:
                row["minflt"] = faults[0] - thread.faults[0]
                row["majflt"] = faults[1] - thread.faults[1]
            thread.faults = faults
            if new and thread.sched and len(new) == 3:
                row["run_ns"] = new[0] - thread.sched[0]
                row["queue_ns"] = new[1] - thread.sched[1]
                row["slices"] = new[2] - thread.sched[2]
            thread.sched = new
            thread.counts = collections.Counter()
            rows[str(tid)] = row
        return rows

    def descriptors(self):
        links = {}
        try:
            for name in os.listdir("/proc/%d/fd" % self.pid):
                try:
                    links[name] = os.readlink("/proc/%d/fd/%s" % (self.pid, name))
                except OSError:
                    pass
        except OSError:
            pass
        return links


def gpu_paths():
    return [str(p) for p in Path("/sys/class/drm").glob("card*/device") if (p / "gpu_busy_percent").exists()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=int, default=5400, help="how long to wait for the game to start")
    parser.add_argument("--max-seconds", type=int, default=3600, help="longest capture")
    parser.add_argument("--pid", type=int, help="sample this process instead of the game (self-test)")
    parser.add_argument("--out", default=None)
    arguments = parser.parse_args()

    logs = Path(__file__).resolve().parent.parent.parent / "build/logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = Path(arguments.out or logs / ("host-sample-%s.jsonl" % datetime.now().strftime("%Y%m%d-%H%M%S")))
    deadline = time.monotonic() + arguments.wait_seconds
    pid = arguments.pid
    while pid is None:
        pid = find("game")
        if pid is None:
            if time.monotonic() > deadline:
                print(json.dumps({"event": "no_game"}), flush=True)
                return 1
            time.sleep(2)
    game = Process(pid)
    server_pid = find("server")
    server = Process(server_pid) if server_pid else None
    gpus = gpu_paths()
    pair = siblings()
    smt = collections.Counter()
    print(json.dumps({"event": "start", "log": str(out), "game": pid, "server": server_pid}), flush=True)

    own = time.process_time()
    with out.open("w") as handle:
        handle.write(json.dumps({"event": "start", "time": datetime.now(timezone.utc).isoformat(), "game": pid,
                                 "server": server_pid, "main_hz": MAIN_HZ, "other_hz": MAIN_HZ // OTHER_EVERY}) + "\n")
        for second in range(arguments.max_seconds):
            begin = time.monotonic()
            for tick in range(MAIN_HZ):
                slot = begin + (tick + random.random()) / MAIN_HZ
                delay = slot - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                if tick % OTHER_EVERY == 0:
                    game.sample()
                    if server:
                        server.sample()
                    # Which threads are runnable, and where; does anything share the main thread's core?
                    states = game.placement()
                    others = dict(server.placement()) if server else {}
                    main_state = states.pop(pid, None)
                    if main_state and main_state[0] == "R":
                        smt["main_R"] += 1
                        smt["cpu%d" % main_state[1]] += 1
                        near = pair.get(main_state[1], [])
                        for group, table in (("game", states), ("server", others)):
                            for tid, (state, cpu) in table.items():
                                if state == "R" and cpu in near:
                                    smt["sibling_" + group] += 1
                                    smt["sibling:" + game.threads[tid].name if group == "game" and tid in game.threads else "sibling:server"] += 1
                else:
                    game.sample(only=pid)
            delay = begin + 1 - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            row = {"time": datetime.now(timezone.utc).isoformat(), "elapsed_s": time.monotonic() - begin,
                   "game": game.flush(), "server": server.flush() if server else {},
                   "gpu_busy": [int(read(g + "/gpu_busy_percent") or -1) for g in gpus],
                   "observer_cpu_s": round(time.process_time() - own, 3)}
            row["smt"] = dict(smt)
            smt.clear()
            if second % 30 == 0:
                row["game_fds"] = game.descriptors()
                row["memory"] = huge_pages(pid)
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            alive = game.refresh()
            if server:
                server.refresh()
            if not alive or pid not in game.threads:
                break
            if second % 60 == 59:
                main_row = row["game"].get(str(pid), {})
                print(json.dumps({"event": "progress", "second": second + 1,
                                  "main_run_pct": round(main_row.get("run_ns", 0) / 1e7 / row["elapsed_s"], 1),
                                  "observer_cpu_s": row["observer_cpu_s"]}), flush=True)
    print(json.dumps({"event": "end", "log": str(out)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
