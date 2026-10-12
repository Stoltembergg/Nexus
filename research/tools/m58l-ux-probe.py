#!/usr/bin/env python3
"""darling-lol M58l: Riot UX window/present probe via the Electron main process.

The Riot UX exposes the Electron main process on --inspect=9229. This tool
answers, without any guest instrumentation:

  * which BrowserWindows exist, their bounds and isVisible()
  * whether the main window's webContents is still loading (load never ends)
  * whether the renderer main thread answers (executeJavaScript round-trip)
  * optionally force-show the windows (maps their X11 windows)

Usage:
  # start the UX with --inspect=9229, then:
  python3 tools/m58l-ux-probe.py            # print state
  python3 tools/m58l-ux-probe.py --show     # print state, then force-show
"""
import argparse
import json
import urllib.request

import websocket

REQ = "process.mainModule.require"
PORT = 9229


def _ws():
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data
               if t.get("webSocketDebuggerUrl"))
    return websocket.create_connection(url, timeout=60)


def rpc(ws, mid, js, timeout=45):
    ws.settimeout(timeout)
    ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                        "params": {"expression": js, "returnByValue": True,
                                   "awaitPromise": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            return msg.get("result", {})


def probe(ws, show=False):
    js = (
        "(async()=>{const{BrowserWindow}=%s('electron');"
        "const ws=BrowserWindow.getAllWindows();"
        "const out=[];"
        "for(const w of ws){const wc=w.webContents;const t0=Date.now();"
        " let r;"
        " try{r=await Promise.race([wc.executeJavaScript('1+1')"
        ".then(v=>'OK:'+v).catch(e=>'ERR:'+e.message),"
        "new Promise(z=>setTimeout(()=>z('TIMEOUT'),8000))]);}"
        " catch(e){r='THROW:'+e.message;}"
        " out.push({id:w.id,vis:w.isVisible(),loading:wc.isLoading(),"
        " url:(wc.getURL()||'').slice(0,70),bounds:w.getBounds(),"
        " js:r,ms:Date.now()-t0});}"
        "%s"
        "return JSON.stringify(out)})()"
    ) % (REQ, "ws.forEach(w=>{try{w.show()}catch(e){}});"
              "await new Promise(z=>setTimeout(z,1500));" if show else "")
    r = rpc(ws, 1, js, timeout=90)
    return r.get("result", {}).get("value", r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true",
                    help="force-show all windows (maps their X11 windows)")
    args = ap.parse_args()
    ws = _ws()
    try:
        print(probe(ws, show=args.show))
    finally:
        ws.close()


if __name__ == "__main__":
    main()
