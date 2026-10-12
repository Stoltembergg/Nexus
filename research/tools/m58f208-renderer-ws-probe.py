#!/usr/bin/env python3
"""Capture renderer WebSocket/console events while reloading Riot UX."""
import json
import urllib.request

import websocket


JS = r"""
(async()=>{
  const {BrowserWindow} = process.mainModule.require('electron');
  const w = BrowserWindow.getAllWindows().find(x => x.webContents.getURL().startsWith('http'));
  if (!w) return JSON.stringify(['no http window']);
  const c = w.webContents;
  const log = [];
  if (!c.debugger.isAttached()) c.debugger.attach('1.1');
  c.debugger.on('message', (event, method, params) => {
    const m = typeof method === 'string' ? method : event?.method;
    const p = params || event?.params || {};
    if (m?.startsWith('Network.webSocket'))
      log.push(m + ' ' + JSON.stringify(p).slice(0, 500));
    if (m === 'Runtime.exceptionThrown')
      log.push(m + ' ' + JSON.stringify(p).slice(0, 500));
    if (m === 'Log.entryAdded')
      log.push(m + ' ' + JSON.stringify(p).slice(0, 500));
  });
  c.on('console-message', (...a) => log.push('console ' + a.map(x =>
    typeof x === 'string' ? x : x?.message || '').join(' ').slice(0, 500)));
  c.on('did-finish-load', () => log.push('did-finish-load'));
  c.on('did-fail-load', (e, code, description) =>
    log.push('did-fail-load ' + code + ' ' + description));
  await c.debugger.sendCommand('Network.enable');
  await c.debugger.sendCommand('Runtime.enable');
  await c.debugger.sendCommand('Log.enable');
  c.reloadIgnoringCache();
  await new Promise(resolve => setTimeout(resolve, 100000));
  return JSON.stringify(log.slice(-120));
})()
"""


targets = json.load(urllib.request.urlopen('http://127.0.0.1:9229/json/list', timeout=5))
url = next(target['webSocketDebuggerUrl'] for target in targets
           if target.get('webSocketDebuggerUrl'))
ws = websocket.create_connection(url, timeout=120)
ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                    'params': {'expression': JS, 'returnByValue': True,
                               'awaitPromise': True}}))
while True:
    message = json.loads(ws.recv())
    if message.get('id') == 1:
        value = message.get('result', {}).get('result', {}).get('value')
        for line in json.loads(value) if value else [str(message)]:
            print(line)
        break
