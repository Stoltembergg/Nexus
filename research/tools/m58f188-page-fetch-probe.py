#!/usr/bin/env python3
"""darling-lol M58F188: dump the page <head> (inline script + CSP) and test the
RENDERER's own HTTP path (fetch renderer.js from inside the page).
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
 const expr=`(async()=>{
   const out={rs:document.readyState, sheets:document.styleSheets.length,
              head:document.head.innerHTML.slice(0,1200)};
   const t0=performance.now();
   try{ const ctl=new AbortController(); const to=setTimeout(()=>ctl.abort(),20000);
        const r=await fetch('/style.css',{cache:'no-store',signal:ctl.signal});
        out.cssFetch={ok:r.ok,status:r.status,ms:Math.round(performance.now()-t0)};
        clearTimeout(to);}catch(e){out.cssFetch={err:String(e).slice(0,80),ms:Math.round(performance.now()-t0)};}
   const t1=performance.now();
   try{ const ctl=new AbortController(); const to=setTimeout(()=>ctl.abort(),25000);
        const r=await fetch('/renderer.js',{cache:'no-store',signal:ctl.signal});
        const b=await r.text();
        out.jsFetch={ok:r.ok,status:r.status,len:b.length,ms:Math.round(performance.now()-t1)};
        clearTimeout(to);}catch(e){out.jsFetch={err:String(e).slice(0,80),ms:Math.round(performance.now()-t1)};}
   return JSON.stringify(out);
 })()`;
 const r=await Promise.race([
   wc.debugger.sendCommand('Runtime.evaluate',{expression:expr,returnByValue:true,awaitPromise:true}),
   new Promise(z=>setTimeout(()=>z({__timeout:true}),60000))]);
 return JSON.stringify(r);
})()
"""


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
