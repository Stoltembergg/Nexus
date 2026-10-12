#!/usr/bin/env python3
"""darling-lol M58ag: poll the renderer's fate and responsiveness over time.

Each sample records: who owns CrRendererMain (host pids), the main window's
visible/loading state, and whether the renderer answers a bounded
executeJavaScript('1+1') — so we can see whether it hangs, dies, or when it
changes, and correlate with the app's timeline.
"""
import argparse
import json
import subprocess
import time
import urllib.request

import websocket

PROBE = (
    "(async()=>{const{BrowserWindow}=process.mainModule.require('electron');"
    "const ws=BrowserWindow.getAllWindows();"
    "const w=ws.find(x=>x.webContents.getURL().indexOf('index.html')>=0)||ws[0];"
    "if(!w)return JSON.stringify({none:true});"
    "const wc=w.webContents;const t0=Date.now();let js='?';"
    "try{js=await Promise.race([wc.executeJavaScript('1+1').then(v=>'OK:'+v).catch(e=>'ERR'),"
    "new Promise(z=>setTimeout(()=>z('TIMEOUT'),6000))])}catch(e){js='THROW'}"
    "return JSON.stringify({vis:w.isVisible(),loading:wc.isLoading(),js:js,ms:Date.now()-t0})})()"
)


def rpc(ws, mid, js, tmo=30):
    ws.settimeout(tmo)
    ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                        "params": {"expression": js, "returnByValue": True,
                                   "awaitPromise": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            return msg.get("result", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=25)
    ap.add_argument("--count", type=int, default=10)
    args = ap.parse_args()

    try:
        data = json.load(urllib.request.urlopen("http://127.0.0.1:9229/json/list", timeout=5))
        url = next(t["webSocketDebuggerUrl"] for t in data if t.get("webSocketDebuggerUrl"))
        ws = websocket.create_connection(url, timeout=60)
    except Exception as e:
        print("CONNECT-FAIL", e)
        return
    mid = 0
    for _ in range(args.count):
        try:
            pids = subprocess.check_output(["pgrep", "-x", "CrRendererMain"]).decode().split()
        except Exception:
            pids = []
        try:
            r = rpc(ws, mid, PROBE)
            st = r.get("result", {}).get("value", str(r))
        except Exception as e:
            st = "PROBE-FAIL %s" % e
        print("%s renderers=[%s] %s" % (time.strftime("%H:%M:%S"),
                                        " ".join(pids), st), flush=True)
        mid += 1
        time.sleep(args.interval)
    try:
        ws.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
