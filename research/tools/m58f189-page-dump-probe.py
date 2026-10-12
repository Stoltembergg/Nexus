#!/usr/bin/env python3
"""darling-lol M58F189: minimal page dump (head HTML + inline script text)."""
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
 const expr=[
  'JSON.stringify({'+
  ' rs:document.readyState,'+
  ' inline:[...document.scripts].filter(s=>!s.src).map(s=>(s.type||"")+":"+(s.textContent||"").slice(0,600)),'+
  ' mods:[...document.scripts].filter(s=>s.src).map(s=>s.type+":"+s.src),'+
  ' csp:(document.querySelector(\'meta[http-equiv="Content-Security-Policy"]\')||{}).content||"",'+
  ' head:document.head.innerHTML.slice(0,1500)'+
  '})'].join('');
 try{
   const r=await wc.debugger.sendCommand('Runtime.evaluate',{expression:expr,returnByValue:true});
   return JSON.stringify(r.result&&r.result.value!==undefined?JSON.parse(r.result.value):r);
 }catch(e){ return 'ERR:'+e.message; }
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
                    s = json.loads(v) if isinstance(v, str) else v
                    print(json.dumps(s, indent=1)[:4500])
                except Exception:
                    print(v)
                break
    finally:
        ws.close()


if __name__ == "__main__":
    main()
