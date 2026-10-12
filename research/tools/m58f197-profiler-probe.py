#!/usr/bin/env python3
"""darling-lol M58F197: V8 CPU profile (self time by function) of a Riot Electron
main process via the Node inspector Profiler domain.
"""
import collections
import json
import time
import urllib.request

import websocket

PORT = 9229
SECS = 5


def rpc(ws, mid, method, params=None, timeout=90):
    ws.settimeout(timeout)
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == mid:
            return m.get("result", {}), m.get("error")


def main():
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data
               if t.get("webSocketDebuggerUrl"))
    ws = websocket.create_connection(url, timeout=180)
    try:
        rpc(ws, 1, "Profiler.enable")
        rpc(ws, 2, "Profiler.setSamplingInterval", {"interval": 500})
        r, e = rpc(ws, 3, "Profiler.start")
        print("start:", r, e)
        time.sleep(SECS)
        res, err = rpc(ws, 4, "Profiler.stop", timeout=120)
        prof = res.get("profile") or {}
        print("stop err:", err, "nodes:", len(prof.get("nodes", [])),
              "samples:", len(prof.get("samples", [])))
        nodes = {n["id"]: n for n in prof.get("nodes", [])}
        samples = prof.get("samples", [])
        deltas = prof.get("timeDeltas", [])
        self_us = collections.Counter()
        for i, sid in enumerate(samples):
            d = deltas[i] if i < len(deltas) else 0
            self_us[sid] += d
        rows = []
        for sid, us in self_us.most_common(20):
            cf = nodes.get(sid, {}).get("callFrame", {})
            fn = cf.get("functionName") or "(anon)"
            urlf = (cf.get("url") or "").split("/")[-1]
            rows.append((us / 1000.0, fn, urlf, cf.get("lineNumber", -1)))
        print("total sampled ms:", round(sum(self_us.values()) / 1000.0))
        for ms, fn, urlf, ln in rows:
            print("  %8.1fms  %-40s %s:%s" % (ms, fn[:40], urlf, ln))
    finally:
        ws.close()


if __name__ == "__main__":
    main()
