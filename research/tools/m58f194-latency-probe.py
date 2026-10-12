#!/usr/bin/env python3
"""darling-lol M58F194: event-loop turn latency series in an Electron main
process (one CDP call per sample so it streams).
"""
import json
import sys
import time
import urllib.request

import websocket

PORT = 9229

EXPR = ("(async()=>{const a=Date.now();await new Promise(z=>setTimeout(z,0));"
        "const d0=Date.now()-a;const b=Date.now();await new Promise(z=>setTimeout(z,5));"
        "return JSON.stringify([d0,Date.now()-b]);})()")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data
               if t.get("webSocketDebuggerUrl"))
    ws = websocket.create_connection(url, timeout=120)
    try:
        for i in range(n):
            mid = 100 + i
            ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                "params": {"expression": EXPR,
                                           "returnByValue": True,
                                           "awaitPromise": True}}))
            v = None
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == mid:
                    v = m.get("result", {}).get("result", {}).get("value")
                    break
            try:
                d0, d5 = json.loads(v)
                print("[%s] setTimeout0=%sms setTimeout5=%sms"
                      % (time.strftime("%H:%M:%S"), d0, d5))
            except Exception:
                print("[%s] ?" % time.strftime("%H:%M:%S"), v)
            sys.stdout.flush()
            time.sleep(0.4)
    finally:
        ws.close()


if __name__ == "__main__":
    main()
