#!/usr/bin/env python3
"""darling-lol M58F191: capture the RENDERER's Network CDP events on reload, to
name which subresources fail/hang and with what error.
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
 const log=[];
 if(!globalThis.__m58f191){
   globalThis.__m58f191=true;
   globalThis.__m58f191log=log;
   try{ if(!wc.debugger.isAttached()) wc.debugger.attach('1.1'); }catch(e){}
   wc.debugger.on('message',(ev,m,params)=>{
     const me=(ev&&ev.method)||m;
     const p=(ev&&ev.params)||params||{};
     if(typeof me!=='string'||me.indexOf('Network.')!==0) return;
     let s=me;
     try{
       if(me==='Network.requestWillBeSent') s+=' '+p.request.method+' '+p.request.url;
       else if(me==='Network.responseReceived') s+=' '+p.response.status+' '+(p.response.url||'');
       else if(me==='Network.loadingFinished') s+=' '+(p.encodedDataLength||0)+'B '+(p.requestId||'');
       else if(me==='Network.loadingFailed') s+=' ERR='+p.errorText+' canceled='+p.canceled+' '+p.requestId;
       else return;
     }catch(e){}
     globalThis.__m58f191log.push(String(s).slice(0,180));
   });
 }
 try{ await wc.debugger.sendCommand('Network.enable',{}); }catch(e){ log.push('Network.enable ERR '+e.message); }
 globalThis.__m58f191log.push('RELOAD '+wc.getURL());
 wc.reload();
 await new Promise(z=>setTimeout(z,25000));
 return JSON.stringify(globalThis.__m58f191log.slice(-50));
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
                    for line in json.loads(v):
                        print(line)
                except Exception:
                    print(v)
                break
    finally:
        ws.close()


if __name__ == "__main__":
    main()
