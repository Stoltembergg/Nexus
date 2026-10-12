#!/usr/bin/env python3
"""darling-lol M58F192: measure raw guest loopback TCP throughput from inside a
Riot process (same libuv/socket stack the app's static server and the renderer's
network service use).

Transfers 32 MB over 127.0.0.1 with 64 KiB writes and reports MB/s.  If this is
~0.6 MB/s the large-transfer socket path is the root of the renderer.js stall.
"""
import json
import urllib.request

import websocket

PORT = 9229

JS = r"""
(async()=>{
 const net=process.mainModule.require('net');
 const run=(N,CH,capMs)=>new Promise((resolve)=>{
   let t0=0, got=0, done=false;
   const fin=(o)=>{ if(done)return; done=true; try{o.__srv&&o.__srv.close()}catch(e){} resolve(o); };
   const srv=net.createServer(sock=>{
     const buf=Buffer.alloc(CH,0x41); let sent=0;
     const pump=()=>{ while(sent<N){ const n=Math.min(CH,N-sent); const ok=sock.write(buf.subarray(0,n)); sent+=n; if(!ok){ sock.once('drain',pump); return; } } try{sock.end();}catch(e){} };
     pump();
   });
   srv.on('error',e=>{ const o={err:'srv '+e.message}; o.__srv=srv; fin(o); });
   srv.listen(0,'127.0.0.1',()=>{
     const c=net.connect(srv.address().port,'127.0.0.1');
     t0=Date.now();
     c.on('error',e=>{ const o={err:'cli '+e.message}; o.__srv=srv; fin(o); });
     c.on('data',d=>{ got+=d.length; });
     c.on('end',()=>{ const ms=Date.now()-t0;
       const o={MB:(N/1048576),chunkKB:(CH/1024),ms:ms,MBps:+((N/1048576)/(ms/1000)).toFixed(2),gotMB:+(got/1048576).toFixed(1)};
       o.__srv=srv; fin(o); });
     setTimeout(()=>{ if(done)return; const o={stalled:true,MB:(N/1048576),capMs:capMs,gotMB:+(got/1048576).toFixed(2),MBps:+((got/1048576)/(capMs/1000)).toFixed(2)}; o.__srv=srv; fin(o); }, capMs);
   });
 });
 const out=[];
 out.push(await run(1*1048576, 65536, 20000));
 out.push(await run(4*1048576, 65536, 20000));
 out.push(await run(16*1048576, 65536, 30000));
 return JSON.stringify(out);
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
                    print(json.dumps(json.loads(v), indent=1)[:2000])
                except Exception:
                    print(v)
                break
    finally:
        ws.close()


if __name__ == "__main__":
    main()
