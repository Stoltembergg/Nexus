#!/usr/bin/env python3
"""Apply Riot's Darling scheduling workaround through its local main inspector.

Reads no page, field, clipboard, URL, or account data. Exits after installing
the main-process window hook; no continuous host polling is needed.
"""
import json
import time
import urllib.request
import websocket

expression = r'''(()=>{
 const e=process.mainModule.require("electron");
 if(!e.app.getName().toLowerCase().includes("riot"))return false;
 if(!global.__darlingForegroundScheduling){
   const configure=w=>{if(!w.isDestroyed())w.webContents.setBackgroundThrottling(false)};
   e.app.on("browser-window-created",(_event,w)=>configure(w));
   e.BrowserWindow.getAllWindows().forEach(configure);
   global.__darlingForegroundScheduling=true;
 }
 return true;
})()'''

deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    connection = None
    try:
        with urllib.request.urlopen('http://127.0.0.1:9229/json/list', timeout=2) as response:
            targets = json.load(response)
        connection = websocket.create_connection(targets[0]['webSocketDebuggerUrl'], timeout=3)
        connection.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {
            'expression': expression, 'returnByValue': True}}))
        while True:
            result = json.loads(connection.recv())
            if result.get('id') == 1:
                if result.get('result', {}).get('result', {}).get('value') is True:
                    print('Riot foreground scheduling configured', flush=True)
                    raise SystemExit(0)
                break
    except (OSError, ValueError, KeyError, IndexError, websocket.WebSocketException):
        pass
    finally:
        if connection is not None:
            connection.close()
    time.sleep(1)
raise SystemExit('Riot foreground scheduling unavailable: local main inspector did not become ready')
