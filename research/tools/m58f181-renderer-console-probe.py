#!/usr/bin/env python3
"""darling-lol M58F181: capture the renderer's console + DOM to explain the
reload loop.

Hooks webContents console-message / did-finish-load / did-fail-load /
render-process-gone in the Electron MAIN process, reloads the http window, waits,
then reads back document.readyState / body size to see how far the page gets.
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
 if(!globalThis.__m58f181){
   globalThis.__m58f181=true;
   globalThis.__m58f181log=[];
   const L=globalThis.__m58f181log;
   wc.on('console-message',(...a)=>{
     let m='';
     for(const x of a){ if(x&&typeof x==='object'&&x.message!==undefined) m+=' '+x.message; else if(typeof x!=='object') m+=' '+x; }
     L.push('CONSOLE'+m.slice(0,200));
   });
   wc.on('did-finish-load',()=>L.push('finish-load'));
   wc.on('did-fail-load',(e,ec,ed,u)=>L.push('FAIL '+ec+' '+ed+' '+u));
   wc.on('render-process-gone',(e,d)=>L.push('GONE '+JSON.stringify(d)));
 }
 wc.reload();
 await new Promise(z=>setTimeout(z,25000));
 try{
   const r=await Promise.race([
     wc.executeJavaScript('({href:location.href,rs:document.readyState,body:(document.body&&document.body.innerHTML.length)||0,title:document.title,nscripts:document.scripts.length})')
       .then(v=>JSON.stringify(v)).catch(e=>'ERR:'+e.message),
     new Promise(z=>setTimeout(()=>z('JS-TIMEOUT'),9000))]);
   globalThis.__m58f181log.push('DOM '+r);
 }catch(e){ globalThis.__m58f181log.push('DOM THROW '+e.message); }
 return JSON.stringify(globalThis.__m58f181log.slice(-40));
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
