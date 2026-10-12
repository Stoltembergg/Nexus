#!/usr/bin/env python3
"""Evaluate a local diagnostic script inside Riot without exporting Riot credentials."""
import json
import sys
import time
import urllib.request
from pathlib import Path

import websocket


source = Path(sys.argv[1]).read_text()
for attempt in range(15):
    try:
        with urllib.request.urlopen("http://127.0.0.1:9229/json/list", timeout=3) as response:
            target = json.load(response)[0]
        connection = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30)
        break
    except (OSError, ValueError, IndexError, websocket.WebSocketException):
        if attempt == 14:
            print(json.dumps({"error": "Riot inspector unavailable"}))
            raise SystemExit(1)
        time.sleep(1)


def evaluate(expression, number):
    connection.send(json.dumps({"id": number, "method": "Runtime.evaluate", "params": {
        "expression": expression, "returnByValue": True, "awaitPromise": True}}))
    while True:
        message = json.loads(connection.recv())
        if message.get("id") == number:
            return message


try:
    evaluate("global.__darlingLeagueInspectSource=''", 1)
    number = 1
    for offset in range(0, len(source), 500):
        number += 1
        evaluate("global.__darlingLeagueInspectSource+=" + json.dumps(source[offset:offset + 500]), number)
    number += 1
    result = evaluate("(async()=>{try{return await eval(global.__darlingLeagueInspectSource)}finally{delete global.__darlingLeagueInspectSource}})()", number)
    remote = result.get("result", {})
    print(json.dumps(remote.get("result", {}).get("value", {"error": "evaluation failed"})))
except (OSError, websocket.WebSocketException):
    print(json.dumps({"error": "Riot diagnostic request interrupted"}))
    raise SystemExit(1)
finally:
    connection.close()
