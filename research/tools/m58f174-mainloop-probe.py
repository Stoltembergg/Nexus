#!/usr/bin/env python3
"""darling-lol M58F174: probe the Electron MAIN process event loop in steady
state (after the startup CPU burst settles).

Answers, via the main process's Node inspector (--inspect=9229):
  * setTimeout(0/1/10/50) latency  -> is the loop's timer handling delayed?
  * async fs.readFile of a real file -> do libuv I/O completions arrive?
  * HTTP GET index.html + renderer.js from the app's own static server -> is the
    server slow because the loop is stalled, or because the disk path is slow?
"""
import json
import urllib.request

import websocket

REQ = "process.mainModule.require"
PORT = 9229

JS = r"""
(async()=>{
 const M=process.mainModule.require;
 const {BrowserWindow}=M('electron');
 const http=M('http');
 const fs=M('fs');
 const out={};
 for(const d of [0,1,10,50]){
   const t=Date.now(); await new Promise(z=>setTimeout(z,d));
   out['setTimeout'+d]=Date.now()-t;
 }
 // async file I/O in the main process (libuv threadpool + completion)
 try {
   const f='/Applications/Riot Client.app/Contents/Info.plist';
   const t=Date.now();
   await new Promise((res,rej)=>fs.readFile(f,(e,d)=>e?rej(e):res(d)));
   out.fsReadInfoPlist=Date.now()-t;
 } catch(e){ out.fsReadInfoPlist='ERR:'+(e&&e.message||e); }
 const w=BrowserWindow.getAllWindows().find(x=>(x.webContents.getURL()||'').startsWith('http'));
 if(!w){ out.err='no http window'; return JSON.stringify(out); }
 out.url=w.webContents.getURL();
 const origin=new URL(out.url).origin;
 const get=p=>new Promise(res=>{const t=Date.now();let n=0;
   const r=http.get(origin+p,resp=>{resp.on('data',d=>n+=d.length);
     resp.on('end',()=>res({ms:Date.now()-t,n}));});
   r.on('error',e=>res({ms:Date.now()-t,err:String(e&&e.message||e)}));
   r.setTimeout(30000,()=>{r.destroy();res({ms:Date.now()-t,timeout:true});});});
 out.index=await get('/index.html');
 out.renderer=await get('/renderer.js');
 out.loading=w.webContents.isLoading();
 return JSON.stringify(out);
})()
"""


def _ws():
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    url = next(t["webSocketDebuggerUrl"] for t in data
               if t.get("webSocketDebuggerUrl"))
    return websocket.create_connection(url, timeout=120)


def main():
    ws = _ws()
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": JS, "returnByValue": True,
                                       "awaitPromise": True}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                r = msg.get("result", {})
                print(r.get("result", {}).get("value", r))
                break
    finally:
        ws.close()


if __name__ == "__main__":
    main()
