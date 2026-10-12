#!/usr/bin/env python3
"""Install the League Update compatibility hook through Riot's local inspector.

Installs an app-local hook. Authentication stays inside Riot; host reads no credentials. Exits after installing
the main-process update hook; no continuous host polling is needed.
"""
import json
import time
import urllib.request
import websocket

from pathlib import Path
expression = Path(__file__).with_name("riot-league-update-hook.js").read_text()

deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    connection = None
    try:
        with urllib.request.urlopen('http://127.0.0.1:9229/json/list', timeout=2) as response:
            targets = json.load(response)
        connection = websocket.create_connection(targets[0]['webSocketDebuggerUrl'], timeout=3)
        def evaluate(code, sequence):
            connection.send(json.dumps({'id': sequence, 'method': 'Runtime.evaluate',
                'params': {'expression': code, 'returnByValue': True}}))
            while True:
                response = json.loads(connection.recv())
                if response.get('id') == sequence:
                    return response
        evaluate('global.__darlingLeagueHookSource=""', 1)
        sequence = 1
        for offset in range(0, len(expression), 500):
            sequence += 1
            evaluate('global.__darlingLeagueHookSource+=' + json.dumps(expression[offset:offset+500]), sequence)
        sequence += 1
        result = evaluate('(()=>{try{return eval(global.__darlingLeagueHookSource)}finally{delete global.__darlingLeagueHookSource}})()', sequence)
        if result.get('result', {}).get('result', {}).get('value') is True:
            print('Riot League update handoff configured', flush=True)
            raise SystemExit(0)
    except (OSError, ValueError, KeyError, IndexError, websocket.WebSocketException):
        pass
    finally:
        if connection is not None:
            connection.close()
    time.sleep(1)
raise SystemExit('Riot League update handoff unavailable: local main inspector did not become ready')
