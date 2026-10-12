#!/usr/bin/env python3
"""darling-lol M58n: measure the UX browser-process event-loop latency.

M58m attributed the never-loading UX page to "guest loopback latency".
M58n shows the socket layer and every primitive wait (kevent / poll /
pthread_cond_timedwait / mach_msg timeouts) are accurate (~300 us), but
the Electron **browser process**'s own event loop runs its timers and fs
completions seconds late, which starves the Node/Express asset server.

This tool runs the discriminating probe inside the browser process via
the Electron main process (`--inspect=9229`):

    nextTick      0 ms   (microtask, no loop turn needed)
    setImmediate  ~ms    (check phase, every loop iteration)
    setTimeout    2-8 s  (timer phase)
    fs.readFile   9-13 s (threadpool completion)

Usage: start the UX with --inspect=9229, then
    python3 tools/m58n-browser-loop-latency.py
"""
import json
import urllib.request

import websocket

REQ = "process.mainModule.require"
PORT = 9229

JS = (
    "(async()=>{const out={};let t0;"
    "t0=Date.now();await new Promise(r=>process.nextTick(r));out.nextTick=Date.now()-t0;"
    "t0=Date.now();await new Promise(r=>setImmediate(r));out.setImmediate=Date.now()-t0;"
    "t0=Date.now();await new Promise(r=>setTimeout(r,0));out.setTimeout0=Date.now()-t0;"
    "t0=Date.now();await new Promise(r=>setTimeout(r,100));out.setTimeout100=Date.now()-t0;"
    "t0=Date.now();await new Promise(r=>setTimeout(r,1000));out.setTimeout1000=Date.now()-t0;"
    "const fs=%s('fs');"
    "t0=Date.now();await new Promise((res)=>{"
    "fs.readFile('/System/Library/CoreServices/SystemVersion.plist',(e,b)=>{"
    "out.fs_read=Date.now()-t0;"
    "out.fs_err=e?String(e.message).slice(0,50):('bytes='+(b?b.length:0));res()})});"
    "return JSON.stringify(out)})()"
)


def rpc(ws, mid, js, timeout=120):
    ws.settimeout(timeout)
    ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                        "params": {"expression": js, "returnByValue": True,
                                   "awaitPromise": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            return msg.get("result", {})


def main():
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data
               if t.get("webSocketDebuggerUrl"))
    ws = websocket.create_connection(url, timeout=140)
    r = rpc(ws, 1, JS % REQ)
    print(json.dumps(r.get("result", {}).get("value", r))[:600])
    ws.close()


if __name__ == "__main__":
    main()
