#!/usr/bin/env python3
"""darling-lol M58F190: test the RENDERER's own HTTP path from inside the page
(style.css then renderer.js) and read back styleSheets + the CSP-blocked shim.
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
              hasRequire:(typeof window.require)};
   const F=async(u,ms)=>{const t=performance.now();
     try{const c=new AbortController();const to=setTimeout(()=>c.abort(),ms);
       const r=await fetch(u,{cache:'no-store',signal:c.signal});
       const b=await r.text(); clearTimeout(to);
       return {ok:r.ok,st:r.status,ct:r.headers.get('content-type')||'',len:b.length,ms:Math.round(performance.now()-t)};}
     catch(e){return {err:String(e).slice(0,90),ms:Math.round(performance.now()-t)};}};
   out.style=await F('/style.css',10000);
   out.renderer=await F('/renderer.js',30000);
   return JSON.stringify(out);
 })()`;
 try{
   const r=await Promise.race([
     wc.debugger.sendCommand('Runtime.evaluate',{expression:expr,returnByValue:true,awaitPromise:true}),
     new Promise(z=>setTimeout(()=>z({__timeout:true}),70000))]);
   const v=r&&r.result&&r.result.value;
   return v||JSON.stringify(r).slice(0,300);
 }catch(e){ return 'ERR:'+e.message; }
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
                    print(json.dumps(json.loads(v), indent=1)[:3000])
                except Exception:
                    print(v)
                break
    finally:
        ws.close()


if __name__ == "__main__":
    main()
