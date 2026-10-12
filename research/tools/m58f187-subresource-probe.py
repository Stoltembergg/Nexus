#!/usr/bin/env python3
"""darling-lol M58F187: name the subresource that keeps the page in
readyState='interactive' (so the app's UI is never built).

Uses webContents.debugger (CDP) Runtime.evaluate to dump document.readyState,
document.scripts, link/img elements and performance.getEntriesByType('resource').
"""
import json
import urllib.request

import websocket

PORT = 9229

JS = r"""
(async()=>{
 const M=process.mainModule.require;
 const {BrowserWindow}=M('electron');
 const w=BrowserWindow.getAllWindows().find(x=>(x.webContents.getURL()||'').startsWith('http'));
 if(!w) return 'no http window';
 const wc=w.webContents;
 try{ if(!wc.debugger.isAttached()) wc.debugger.attach('1.1'); }catch(e){}
 const expr=`JSON.stringify({
   rs:document.readyState, title:document.title,
   head:document.head?document.head.innerHTML.length:0,
   body:document.body?document.body.innerHTML.slice(0,200):null,
   scripts:[...document.scripts].map(s=>({src:(s.src||'').slice(-46),async:s.async,defer:s.defer,type:s.type||''})),
   links:[...document.querySelectorAll('link')].map(l=>({rel:l.rel,href:(l.href||'').slice(-46)})),
   imgs:[...document.images].map(i=>({src:(i.src||'').slice(-46),complete:i.complete})),
   res:performance.getEntriesByType('resource').map(r=>({n:(r.name||'').slice(-46),d:Math.round(r.duration),sz:r.transferSize||0,rs:r.responseStatus||0}))
 })`;
 const r=await Promise.race([
   wc.debugger.sendCommand('Runtime.evaluate',{expression:expr,returnByValue:true}),
   new Promise(z=>setTimeout(()=>z({__timeout:true}),10000))]);
 return JSON.stringify(r);
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
                    obj = json.loads(v)
                    inner = obj.get("result", {}).get("value", obj)
                    try:
                        inner = json.loads(inner)
                    except Exception:
                        pass
                    print(json.dumps(inner, indent=1)[:4000])
                except Exception:
                    print(v)
                break
    finally:
        ws.close()


if __name__ == "__main__":
    main()
