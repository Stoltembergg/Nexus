#!/usr/bin/env python3
"""darling-lol M58m: measure guest loopback socket latency (IPv4 vs IPv6).

The Riot UX's own Express server (browser process, bound to `::`) is
pathologically slow to serve its assets over `127.0.0.1` (IPv4-mapped),
which is why the 10.8 MB renderer.js never loads and the window is never
shown. This tool reproduces the underlying guest socket latency by running
request/response tests entirely inside the guest via the Electron main
process (`--inspect=9229`).

Usage: start the UX with --inspect=9229, then
    python3 tools/m58m-loopback-latency.py
"""
import json
import urllib.request

import websocket

REQ = "process.mainModule.require"
PORT = 9229


def rpc(ws, mid, js, timeout=60):
    ws.settimeout(timeout)
    ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                        "params": {"expression": js, "returnByValue": True,
                                   "awaitPromise": True}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            return msg.get("result", {})


def rtt(bind, connect, label, rounds=5, delay_ms=0):
    return ("(async()=>{const net=%s('net');"
            "const srv=net.createServer(c=>{c.setNoDelay(true);"
            "c.on('data',()=>c.write(Buffer.alloc(1024,120)))});"
            "return await new Promise(res=>{"
            "srv.listen(0,'%s',()=>{const p=srv.address().port;const out=[];let i=0;let last=Date.now();"
            "const c=net.connect({host:'%s',port:p},()=>{c.setNoDelay(true);last=Date.now();c.write('r0')});"
            "c.on('data',()=>{out.push(Date.now()-last);last=Date.now();i++;"
            " if(i>=%d){c.destroy();srv.close();res(JSON.stringify({label:%s,rtts_ms:out}))}"
            " else setTimeout(()=>c.write('r'+i),%d)});"
            "c.on('error',e=>{srv.close();res(JSON.stringify({label:%s,err:e.message,rtts_ms:out}))});"
            "setTimeout(()=>{try{c.destroy();srv.close()}catch(e){};"
            "res(JSON.stringify({label:%s,timeout:true,rtts_ms:out}))},40000);})})})()"
            % (REQ, bind, connect, rounds, json.dumps(label),
               delay_ms, json.dumps(label), json.dumps(label)))


def main():
    data = json.load(urllib.request.urlopen(
        "http://127.0.0.1:%d/json/list" % PORT, timeout=5))
    ws_url = next(t["webSocketDebuggerUrl"] for t in data
                  if t.get("webSocketDebuggerUrl"))
    ws = websocket.create_connection(ws_url, timeout=180)
    tests = [
        ("127.0.0.1 bind, 127.0.0.1 connect", rtt("127.0.0.1", "127.0.0.1", "v4-v4")),
        (":: bind,      127.0.0.1 connect", rtt("::", "127.0.0.1", "v6-v4")),
        (":: bind,      ::1 connect", rtt("::", "::1", "v6-v6")),
    ]
    mid = 1
    for name, js in tests:
        r = rpc(ws, mid, js, timeout=60)
        print("%-34s => %s" % (name, json.dumps(r.get("result", {}).get("value", r))[:220]))
        mid += 1
    ws.close()


if __name__ == "__main__":
    main()
