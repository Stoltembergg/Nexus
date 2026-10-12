#!/usr/bin/env python3
"""Measure only a generated fixture in an owned temporary Riot video element."""
import argparse
import json
from pathlib import Path
import time
import urllib.request
import websocket

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("fixture", choices=("synthetic-video-only.webm", "synthetic-long-video.webm", "synthetic-hd-video.webm", "synthetic-counter-video.webm", "synthetic-audio.webm", "synthetic-vorbis.webm"))
parser.add_argument("--seconds", type=int, default=12)
parser.add_argument("--warmup", type=int, default=5)
parser.add_argument("--audio-output", action="store_true", help="exercise audio output at volume 0.0001")
args = parser.parse_args()
if not 4 <= args.seconds <= 120:
    parser.error("seconds must be between 4 and 120")
if not 0 <= args.warmup <= 60:
    parser.error("warmup must be between 0 and 60 seconds")
fixture = Path(__file__).resolve().parent.parent / "build/vpx-interop" / args.fixture
if not fixture.is_file():
    parser.error("generated fixture is missing")
with urllib.request.urlopen("http://127.0.0.1:9229/json/list", timeout=3) as response:
    target = json.load(response)[0]
ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=20)
sequence = 0

def main_eval(expression):
    global sequence
    sequence += 1
    ws.send(json.dumps({"id": sequence, "method": "Runtime.evaluate", "params": {
        "expression": expression, "awaitPromise": True, "returnByValue": True}}))
    while True:
        result = json.loads(ws.recv())
        if result.get("id") == sequence:
            if "exceptionDetails" in result.get("result", {}):
                raise RuntimeError("synthetic evaluation failed")
            return result.get("result", {}).get("result", {}).get("value")

def page_eval(expression):
    script = """(async()=>{const c=process.mainModule.require('electron').webContents.getAllWebContents().find(c=>c.getURL().startsWith('http'));if(!c.debugger.isAttached())c.debugger.attach('1.1');return c.debugger.sendCommand('Runtime.evaluate',{expression:EXPR,returnByValue:true})})()""".replace("EXPR", json.dumps(expression))
    return main_eval(script).get("result", {}).get("value")

cleanup = "(()=>{let v=document.getElementById('darling-owned-video-probe');if(v){v.pause();v.remove()}return true})()"
try:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if main_eval("(()=>{const e=process.mainModule?.require('electron');return !!e?.webContents.getAllWebContents().find(c=>c.getURL().startsWith('http'))})()"):
            break
        time.sleep(.25)
    else:
        raise RuntimeError("Riot page did not become ready for the owned fixture")
    setup = """(()=>{document.getElementById('darling-owned-video-probe')?.remove();let v=document.createElement('video');v.id='darling-owned-video-probe';v.muted=true;v.loop=true;v.src=SOURCE;v.style='position:fixed;left:550px;top:100px;width:160px;height:90px;pointer-events:none;z-index:2147483647';document.body.append(v);v.play().catch(()=>{});setTimeout(()=>{v.pause();v.remove()},TIMEOUT);return true})()""".replace("TIMEOUT", str((args.seconds + args.warmup + 10) * 1000))
    if args.audio_output:
        setup = setup.replace("v.muted=true;", "v.muted=false;v.volume=0.0001;")
    script = """(async()=>{const fs=process.mainModule.require('fs'),c=process.mainModule.require('electron').webContents.getAllWebContents().find(c=>c.getURL().startsWith('http'));if(!c.debugger.isAttached())c.debugger.attach('1.1');const source='data:video/webm;base64,'+fs.readFileSync(FIXTURE).toString('base64');return c.debugger.sendCommand('Runtime.evaluate',{expression:SETUP.replace('SOURCE',JSON.stringify(source)),returnByValue:true})})()""".replace("FIXTURE", json.dumps("/Volumes/SystemRoot" + str(fixture))).replace("SETUP", json.dumps(setup))
    main_eval(script)
    page_eval("(()=>{const v=document.getElementById('darling-owned-video-probe');v.__callbackCount=0;v.__presented=0;const tick=(_,m)=>{v.__callbackCount++;v.__presented=m.presentedFrames;if(v.isConnected&&!v.paused)v.requestVideoFrameCallback(tick)};v.requestVideoFrameCallback(tick);return true})()")
    time.sleep(args.warmup)
    samples = []
    start = time.monotonic()
    for second in range(args.seconds):
        time.sleep(max(0, start + second + 1 - time.monotonic()))
        sample = page_eval("(()=>{const v=document.getElementById('darling-owned-video-probe');const q=v?.getVideoPlaybackQuality();return v?{time:v.currentTime,frames:q.totalVideoFrames,dropped:q.droppedVideoFrames,callbacks:v.__callbackCount,presented:v.__presented,stamp:performance.now(),ready:v.readyState,error:v.error?.code||0}:null})()")
        if sample is None:
            raise RuntimeError("owned video disappeared")
        samples.append(sample)
    advancing = all(b["frames"] > a["frames"] for a, b in zip(samples, samples[1:]))
    callbacks_advancing = all(b["callbacks"] > a["callbacks"] for a, b in zip(samples, samples[1:]))
    presented_advancing = all(b["presented"] > a["presented"] for a, b in zip(samples, samples[1:]))
    elapsed = (samples[-1]["stamp"] - samples[0]["stamp"]) / 1000
    rates = {key + "_fps": round((samples[-1][key] - samples[0][key]) / elapsed, 2)
             for key in ("frames", "callbacks", "presented")}
    print(json.dumps({"fixture": args.fixture, "seconds": args.seconds, "warmup": args.warmup, "audio_output": args.audio_output, "advancing": advancing, "callbacks_advancing": callbacks_advancing, "presented_advancing": presented_advancing, "rates": rates, "samples": samples}))
    if not advancing or not callbacks_advancing or not presented_advancing:
        raise SystemExit(1)
finally:
    try:
        try:
            page_eval(cleanup)
        except RuntimeError:
            pass  # A closed page has already discarded the owned element.
    finally:
        ws.close()
