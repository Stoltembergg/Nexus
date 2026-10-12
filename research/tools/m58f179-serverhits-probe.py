#!/usr/bin/env python3
"""darling-lol M58F179: do the RENDERER's requests reach the app's static server?

Patches http.Server.prototype.emit in the Electron MAIN process to record every
'request' URL and the time the response finishes, then reloads the http window
and reports what the server actually served.  If index.html is served but
renderer.js never arrives/finishes for the renderer, the stall is on the
renderer/network path; if renderer.js completes, the stall is after the fetch
(parse/execute).
"""
import json
import urllib.request

import websocket

PORT = 9229

JS = r"""
(async()=>{
 const M=process.mainModule.require;
 const http=M('http');
 globalThis.__srvlog=[];
 if(!http.Server.prototype.__m58f179){
   http.Server.prototype.__m58f179=true;
   const oe=http.Server.prototype.emit;
   http.Server.prototype.emit=function(ev,...a){
     if(ev==='request'){
       const req=a[0], res=a[1];
       const t0=Date.now(), u=(req&&req.url)||'?';
       globalThis.__srvlog.push('REQ  '+u);
       const ow=res.write.bind(res);
       let n=0;
       res.write=function(c,...b){ try{n+=(c&&c.length)||0;}catch(e){} return ow(c,...b); };
       const oe2=res.end.bind(res);
       res.end=function(...b){ try{n+=(b[0]&&b[0].length)||0;}catch(e){}
         globalThis.__srvlog.push('END  '+u+' bytes='+n+' ms='+(Date.now()-t0));
         return oe2(...b); };
     }
     return oe.call(this,ev,...a);
   };
 }
 const {BrowserWindow}=M('electron');
 const w=BrowserWindow.getAllWindows().find(x=>(x.webContents.getURL()||'').startsWith('http'));
 if(!w) return 'no http window';
 globalThis.__srvlog.push('RELOAD '+w.webContents.getURL());
 w.webContents.reload();
 await new Promise(z=>setTimeout(z,30000));
 return JSON.stringify(globalThis.__srvlog.slice(-60));
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
