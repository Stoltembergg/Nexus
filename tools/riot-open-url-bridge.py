#!/usr/bin/env python3
"""Open URLs requested from inside the Darling guest in the host's browser.

Legacy tool: excluded from normal launches because it installs a client inspector hook.
The guest cannot start a Linux browser itself, so NSWorkspace -openURL: writes the URL to
~/.darling/private/tmp/rclol-open/*.url (the shared /private/tmp). This watcher validates each
file (http, https and mailto only) and hands the URL to xdg-open. It exits when the Darling
prefix goes away for good or when --once is given.
"""
import os
import subprocess
import sys
import time
import json
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

prefix = Path(os.environ.get('DPREFIX', str(Path.home() / '.darling')))
spool = prefix / 'private' / 'tmp' / 'rclol-open'
ALLOWED = {'http', 'https', 'mailto'}

def handle(path):
    try:
        url = path.read_text(encoding='utf-8').strip()
    except OSError:
        return
    finally:
        try:
            path.unlink()
        except OSError:
            pass
    if not url or len(url) > 4096 or any(ord(c) < 32 for c in url):
        return
    if urlsplit(url).scheme.lower() not in ALLOWED:
        return
    subprocess.Popen(['xdg-open', url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)

def drain():
    if spool.is_dir():
        for path in sorted(spool.glob('*.url')):
            handle(path)

def install_electron_hook():
    try:
        import websocket
    except ImportError:
        print('Riot external-link hook unavailable: websocket-client missing', flush=True)
        return
    source = Path(__file__).with_name('riot-open-url-hook.js').read_text()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        connection = None
        try:
            with urllib.request.urlopen('http://127.0.0.1:9229/json/list', timeout=2) as response:
                target = json.load(response)[0]
            connection = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=3)
            connection.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {
                'expression': source, 'returnByValue': True}}))
            while True:
                result = json.loads(connection.recv())
                if result.get('id') == 1:
                    if result.get('result', {}).get('result', {}).get('value') is True:
                        print('Riot external-link handoff configured', flush=True)
                        return
                    break
        except (OSError, ValueError, KeyError, IndexError, websocket.WebSocketException):
            pass
        finally:
            if connection is not None:
                connection.close()
        time.sleep(1)
    print('Riot external-link hook unavailable', flush=True)

if '--once' in sys.argv:
    drain()
else:
    threading.Thread(target=install_electron_hook, daemon=True).start()
    while True:
        drain()
        time.sleep(0.3)
