#!/usr/bin/env python3
"""Set a bounded decoder thread count before Riot creates its renderer.

Uses only the main-process command-line API and window readiness metadata.
Never reads page contents, account information, or other command-line values.
"""
import argparse
import json
import time
import urllib.request
import websocket

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--threads',type=int,choices=(0,1,2,4),default=1)
parser.add_argument("--unthrottled",action="store_true")
parser.add_argument("--disable-gpu-vsync",action="store_true")
parser.add_argument('--raster-threads',type=int,choices=(0,1,2,4),default=0)
args=parser.parse_args()
expression='''(()=>{let e=process.mainModule?.require("electron");if(!e?.app)return {retry:true};
let windows=e.BrowserWindow.getAllWindows().length;
if(windows)return {tooLate:true};
if(Number(THREADS))e.app.commandLine.appendSwitch("video-threads",THREADS);
if(Number(RASTER))e.app.commandLine.appendSwitch("num-raster-threads",RASTER);
if(UNTHROTTLED)e.app.commandLine.appendSwitch("disable-frame-rate-limit");
if(DISABLEVSYNC)e.app.commandLine.appendSwitch("disable-gpu-vsync");
return {applied:true,ready:e.app.isReady(),windows,unthrottled:e.app.commandLine.hasSwitch("disable-frame-rate-limit"),gpuVsyncDisabled:e.app.commandLine.hasSwitch("disable-gpu-vsync"),threads:Number(e.app.commandLine.getSwitchValue("video-threads")),rasterThreads:Number(e.app.commandLine.getSwitchValue("num-raster-threads"))}})()'''.replace('THREADS',json.dumps(str(args.threads))).replace('RASTER',json.dumps(str(args.raster_threads))).replace('UNTHROTTLED',str(args.unthrottled).lower()).replace('DISABLEVSYNC',str(args.disable_gpu_vsync).lower())
deadline=time.monotonic()+120
while time.monotonic()<deadline:
    ws=None
    try:
        with urllib.request.urlopen('http://127.0.0.1:9229/json/list',timeout=.5) as r:targets=json.load(r)
        ws=websocket.create_connection(targets[0]['webSocketDebuggerUrl'],timeout=1)
        ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':expression,'returnByValue':True}}))
        while True:
            reply=json.loads(ws.recv())
            if reply.get('id')==1:
                value=reply.get('result',{}).get('result',{}).get('value',{})
                if value.get('tooLate'):raise SystemExit('Decoder scheduling too late: renderer already created')
                if value.get('applied'):
                    print(json.dumps(value),flush=True);raise SystemExit(0)
                break
    except (OSError,ValueError,KeyError,IndexError,websocket.WebSocketException):pass
    finally:
        if ws:ws.close()
    time.sleep(.05)
raise SystemExit('Decoder scheduling unavailable before startup deadline')
