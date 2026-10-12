#!/usr/bin/env python3
"""darling-lol M58F198: capture a Chromium trace of a Riot Electron main process
(contentTracing, off-thread) and report the hottest tasks by total duration.
"""
import collections
import json
import urllib.request

import websocket

PORT = 9229

JS = r"""
(async()=>{
 const M=process.mainModule.require;
 const {contentTracing}=M('electron');
 const cats=['toplevel','v8','tracing','ipc','sequence_manager','scheduler','base','mojom','viz'];
 try{
   await contentTracing.startRecording({categories:cats, recordMode:'recordAsMuchAsPossible'});
   await new Promise(z=>setTimeout(z,6000));
   const p=await contentTracing.stopRecording();
   return String(p);
 }catch(e){ return 'ERR:'+e.message; }
})()
"""


def cp1252(ws):
    return ws


def main():
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data
               if t.get("webSocketDebuggerUrl"))
    ws = websocket.create_connection(url, timeout=180)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": JS, "returnByValue": True,
                                       "awaitPromise": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                v = m.get("result", {}).get("result", {}).get("value")
                break
    finally:
        ws.close()
    print("trace path:", v)
    if not v or v.startswith("ERR:"):
        return
    ev = json.load(open(v, "r", errors="ignore"))
    tn = {}
    for e in ev:
        if e.get("ph") == "M" and e.get("name") == "thread_name":
            tn[e.get("tid")] = e.get("args", {}).get("name")
    tot = collections.Counter()
    cnt = collections.Counter()
    for e in ev:
        if e.get("ph") == "X" and e.get("dur"):
            k = (e.get("tid"), e.get("name"))
            tot[k] += e["dur"]
            cnt[k] += 1
    print("events:", len(ev), " threads:", len(set(t for t, _ in tot)))
    for (tid, name), d in tot.most_common(35):
        print("  tid=%-6s %-14s %-44s %8.1fms  x%d"
              % (tid, (tn.get(tid) or "")[:14], (name or "")[:44], d / 1000.0, cnt[(tid, name)]))


if __name__ == "__main__":
    main()
