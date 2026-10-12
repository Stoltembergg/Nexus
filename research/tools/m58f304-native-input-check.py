#!/usr/bin/env python3
"""Check native sign-in fields using synthetic text; never submits a login."""
import json, os, re, subprocess, sys, time, urllib.request
import websocket
ENV = {**os.environ, "DISPLAY": ":1"}
WINDOW=sys.argv[1] if len(sys.argv)>1 else None
started = time.monotonic()
end = started + 180
connection = None
seq = 0

def evaluate(expression):
    global seq
    seq += 1
    script = '''(async()=>{let c=process.mainModule.require("electron").webContents.getAllWebContents().find(c=>c.getURL().startsWith("http"));if(!c)return null;if(!c.debugger.isAttached())c.debugger.attach("1.1");return c.debugger.sendCommand("Runtime.evaluate",{expression:%s,returnByValue:true})})()''' % json.dumps(expression)
    connection.send(json.dumps({"id": seq, "method": "Runtime.evaluate", "params": {"expression": script, "returnByValue": True, "awaitPromise": True}}))
    while True:
        result = json.loads(connection.recv())
        if result.get("id") == seq:
            outer = result.get("result", {}).get("result", {}).get("value")
            return outer.get("result", {}).get("value") if isinstance(outer, dict) else None

def state():
    return evaluate('({focus:document.activeElement?.name,fields:[...document.querySelectorAll("input")].filter(x=>x.name==="username"||x.name==="password").map(x=>({name:x.name,type:x.type,length:x.value.length}))})')

def key(*keys):
    subprocess.run(["xdotool", "key", "--window", WINDOW, *keys], env=ENV, check=True)

def check(expected_focus, expected_length):
    for _ in range(20):
        current = state()
        if current and current.get("focus") == expected_focus:
            field = next(x for x in current["fields"] if x["name"] == expected_focus)
            if field["length"] == expected_length:
                print("NATIVE_SIGNIN", json.dumps(current), flush=True)
                return
        time.sleep(0.25)
    raise RuntimeError("Native focus or input length did not match")

while time.monotonic() < end:
    if connection is None:
        try:
            info = json.load(urllib.request.urlopen("http://127.0.0.1:9229/json/list", timeout=2))
            connection = websocket.create_connection(info[0]["webSocketDebuggerUrl"], timeout=30)
        except (OSError, ValueError):
            time.sleep(2); continue
    try:
        current = state()
    except (OSError, websocket.WebSocketException):
        connection.close(); connection = None
        time.sleep(2); continue
    if current and len(current.get("fields", [])) == 2:
        break
    time.sleep(5)
else:
    raise SystemExit("NATIVE_SIGNIN fields unavailable after 180 seconds")
if any(x["length"] for x in current["fields"]):
    raise SystemExit("NATIVE_SIGNIN skipped: fields already contain user input")
if WINDOW is None:
    tree = subprocess.check_output(["xwininfo", "-root", "-tree"], env=ENV, text=True)
    matches = re.findall(r'^\s*(0x[0-9a-f]+) "Riot Client":.*?1536x864', tree, re.M)
    if len(matches) != 1:
        raise SystemExit("NATIVE_SIGNIN expected one main window; specify its XID")
    WINDOW = matches[0]
coords=evaluate('(()=>{let r=document.querySelector("input[name=username]").getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()')
subprocess.run(["xdotool","mousemove","--window",WINDOW,str(coords["x"]),str(coords["y"]),"click","1"],env=ENV,check=True)
check("username",0)
# XSendEvent passes through AppKit and Chromium; CDP only observes lengths.
subprocess.run(["xdotool", "type", "--window", WINDOW, "--delay", "100", "darling_probe"], env=ENV, check=True)
check("username", 13)
key(*(["BackSpace"] * 13))
check("username", 0)
key("Tab")
check("password", 0)
subprocess.run(["xdotool", "type", "--window", WINDOW, "--delay", "100", "darling_probe"], env=ENV, check=True)
check("password", 13)
key(*(["BackSpace"] * 13))
check("password", 0)
key("shift+Tab")
check("username", 0)
cycles = min(10, max(0, int(os.environ.get("NATIVE_INPUT_STRESS", "0"))))
if cycles:
    print("NATIVE_STRESS begin; synthetic input; no intermediate inspector reads", flush=True)
    for field in ("username", "password"):
        check(field, 0)
        for _ in range(cycles):
            subprocess.run(["xdotool", "type", "--window", WINDOW, "--delay", "100", "darling_probe"], env=ENV, check=True)
            key(*(["BackSpace"] * 13))
        check(field, 0)
        key("Tab" if field == "username" else "shift+Tab")
    check("username", 0)
    print("NATIVE_STRESS passed; elapsed_seconds", round(time.monotonic()-started, 2), flush=True)
print("NATIVE_SIGNIN passed; both fields cleared; no submission", flush=True)
