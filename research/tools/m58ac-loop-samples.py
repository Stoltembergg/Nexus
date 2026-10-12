#!/usr/bin/env python3
"""darling-lol M58ac: sample the UX browser-process loop latency repeatedly.

Connects to the Electron main process (--inspect=9229) and takes N samples;
each sample measures setTimeout(0) latency and the number of setImmediate
turns in a 500 ms window. Prints one line per sample:

    <time> t0_ms=<n> imm500=<n>

so slow phases can be correlated with a timestamp (host load, app log
milestones, OTLP attempts).
"""
import argparse
import json
import time
import urllib.request

import websocket

JS = ("(async()=>{const o={};let t=Date.now();"
      "await new Promise(r=>setTimeout(r,0));o.t0=Date.now()-t;"
      "let n=0;t=Date.now();while(Date.now()-t<500){n++;await new Promise(r=>setImmediate(r))}"
      "o.imm500=n;return JSON.stringify(o)})()")


def connect():
    data = json.load(urllib.request.urlopen("http://127.0.0.1:9229/json/list", timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data if t.get("webSocketDebuggerUrl"))
    return websocket.create_connection(url, timeout=60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=12, help="number of samples")
    ap.add_argument("-i", type=float, default=4.0, help="seconds between samples")
    ap.add_argument("--tag", default="", help="label printed with each line")
    args = ap.parse_args()

    try:
        ws = connect()
    except Exception as e:
        print("%s CONNECT-FAIL %s" % (time.strftime("%H:%M:%S"), e))
        return
    mid = 0
    for _ in range(args.n):
        try:
            ws.settimeout(30)
            ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                "params": {"expression": JS, "returnByValue": True,
                                           "awaitPromise": True}}))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == mid:
                    v = m.get("result", {}).get("result", {}).get("value", m.get("result"))
                    print("%s %s %s" % (time.strftime("%H:%M:%S"), args.tag, v), flush=True)
                    break
        except Exception as e:
            print("%s %s SAMPLE-FAIL %s" % (time.strftime("%H:%M:%S"), args.tag, e), flush=True)
        mid += 1
        time.sleep(args.i)
    try:
        ws.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
