#!/usr/bin/env python3
"""darling-lol M58F180: why does the main window never finish loading?

Attaches webContents load/crash listeners in the Electron MAIN process, reloads
the http window and reports the event sequence (did-start-loading, dom-ready,
did-finish-load, did-fail-load, render-process-gone, render-process-gone),
plus the renderer OS pid and crash state.
"""
import json
import urllib.request

import websocket

PORT = 9229

JS = r"""
(async()=>{
 const M=process.mainModule.require;
 const {BrowserWindow}=M('electron');
 const log=[];
 const w=BrowserWindow.getAllWindows().find(x=>(x.webContents.getURL()||'').startsWith('http'));
 if(!w) return 'no http window';
 const wc=w.webContents;
 if(!globalThis.__m58f180){
   globalThis.__m58f180=true;
   const add=(ev)=>wc.on(ev,(...a)=>{
     try{ log.push(ev+' '+JSON.stringify(a.map(x=>(x&&x.constructor&&x.constructor.name)||typeof x==='object'?'obj':x)).slice(0,120)); }catch(e){}
   });
   ['did-start-loading','did-stop-loading','dom-ready','did-finish-load',
    'did-fail-load','did-fail-provisional-load','render-process-gone','crashed',
    'unresponsive','responsive','destroyed'].forEach(add);
 } else { globalThis.__m58f180log && log.push(...globalThis.__m58f180log); }
 // capture events into a global so repeated calls accumulate
 const push=()=>{ globalThis.__m58f180log=log; };
 const t0=Date.now();
 log.push('PID '+wc.getOSProcessId()+' crashed='+wc.isCrashed()+' url='+wc.getURL());
 wc.reload();
 await new Promise(z=>setTimeout(z,30000));
 log.push('after 30s: loading='+wc.isLoading()+' crashed='+wc.isCrashed()+' url='+wc.getURL());
 push();
 return JSON.stringify(log);
})()
"""


def main():
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data
               if t.get("webSocketDebuggerUrl"))
    ws = websocket.create_connection(url, timeout=120)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": JS, "returnByValue": True,
                                       "awaitPromise": True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                r = msg.get("result", {})
                v = r.get("result", {}).get("value", r)
                try:
                    for line in json.loads(v):
                        print(line)
                except Exception:
                    print(v)
                break
    finally:
        ws.close()


if __name__ == "__main__":
    main()
