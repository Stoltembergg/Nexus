#!/usr/bin/env python3
"""darling-lol M58F186: is the http window's renderer main thread truly stuck?

Attaches webContents.debugger (CDP to the renderer, a different path from
executeJavaScript) and tries Runtime.evaluate with a short timeout, then
Debugger.pause + Runtime.evaluate.  Reports which paths answer.
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
 const out=[];
 const T=(p,ms)=>Promise.race([p.then(v=>({v})).catch(e=>({e:String(e&&e.message||e)})),
                               new Promise(z=>setTimeout(()=>z({t:true}),ms))]);
 out.push('attached-before='+wc.debugger.isAttached());
 try{ if(!wc.debugger.isAttached()) wc.debugger.attach('1.1'); }catch(e){ out.push('attach-err '+e.message); }
 out.push('attached-after='+wc.debugger.isAttached());
 const ev='document.readyState+"|"+(document.title||"")+"|"+((document.body&&document.body.innerHTML.length)||0)+"|"+location.href';
 const c1=await T(wc.debugger.sendCommand('Runtime.evaluate',{expression:ev,returnByValue:true}),8000);
 out.push('Runtime.evaluate '+JSON.stringify(c1).slice(0,240));
 const c2=await T(wc.debugger.sendCommand('Debugger.enable',{}),5000);
 out.push('Debugger.enable '+JSON.stringify(c2).slice(0,120));
 const c3=await T(wc.debugger.sendCommand('Debugger.pause',{}),5000);
 out.push('Debugger.pause '+JSON.stringify(c3).slice(0,120));
 const c4=await T(wc.debugger.sendCommand('Runtime.evaluate',{expression:'1+1',returnByValue:true}),6000);
 out.push('evaluate-after-pause '+JSON.stringify(c4).slice(0,240));
 try{ await wc.debugger.sendCommand('Debugger.resume',{}); }catch(e){}
 return JSON.stringify(out);
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
