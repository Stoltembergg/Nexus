#!/usr/bin/env python3
"""Measure a temporary compositor transform animation; never inspect field contents."""
import glob, struct
import ctypes as C, ctypes.util, json, os, statistics, subprocess, sys, time, urllib.request, websocket
ws=websocket.create_connection(json.load(urllib.request.urlopen('http://127.0.0.1:9229/json/list',timeout=3))[0]['webSocketDebuggerUrl'],timeout=20)
seq=0
def evaluate(expr):
 global seq
 seq+=1
 script='(async()=>{let c=process.mainModule.require("electron").webContents.getAllWebContents().find(c=>c.getURL().startsWith("http"));if(!c.debugger.isAttached())c.debugger.attach("1.1");return c.debugger.sendCommand("Runtime.evaluate",{expression:'+json.dumps(expr)+',returnByValue:true})})()'
 ws.send(json.dumps({'id':seq,'method':'Runtime.evaluate','params':{'expression':script,'awaitPromise':True,'returnByValue':True}}))
 while True:
  r=json.loads(ws.recv())
  if r.get('id')==seq:return r.get('result',{}).get('result',{}).get('value',{}).get('result',{}).get('value')
x=C.CDLL(ctypes.util.find_library('X11'));x.XOpenDisplay.argtypes=[C.c_char_p];x.XOpenDisplay.restype=C.c_void_p
x.XGetImage.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_ulong,C.c_int];x.XGetImage.restype=C.c_void_p
x.XGetPixel.argtypes=[C.c_void_p,C.c_int,C.c_int];x.XGetPixel.restype=C.c_ulong;x.XDestroyImage.argtypes=[C.c_void_p]
d=x.XOpenDisplay(b':1')
window_arg=sys.argv[1] if len(sys.argv)>1 else 'auto'
if window_arg=='auto':
 candidates=[]
 for value in subprocess.check_output(['xdotool','search','--onlyvisible','--class','Riot'],text=True).split():
  try:
   fields=dict(line.split('=',1) for line in subprocess.check_output(['xdotool','getwindowgeometry','--shell',value],text=True).splitlines())
   candidates.append((int(fields['WIDTH'])*int(fields['HEIGHT']),int(value)))
  except (OSError,subprocess.CalledProcessError,KeyError,ValueError):pass
 if not candidates:raise RuntimeError('No visible Riot window')
 window=max(candidates)[1]
else:window=int(window_arg,0)
evaluate('''(()=>{document.getElementById("darling-frame-probe")?.remove();let e=document.createElement("div");e.id="darling-frame-probe";e.style="position:fixed;left:500px;top:40px;width:32px;height:32px;z-index:2147483647;pointer-events:none;overflow:hidden";let strip=document.createElement("div");strip.style="width:8192px;height:32px;will-change:transform;display:flex";for(let n=0;n<256;n++){let tile=document.createElement("div");tile.style="width:32px;height:32px;flex-shrink:0;background:rgb("+n+",100,200)";strip.append(tile)}e.append(strip);document.body.append(e);strip.animate([{transform:"translate3d(0,0,0)"},{transform:"translate3d(-8192px,0,0)"}],{duration:256*1000/60,iterations:Infinity,easing:"steps(256,end)"});setTimeout(()=>e.remove(),12000);return true})()''')
t=time.monotonic();values=[];changes=[];last=None;slotvalues={};slotseq={};slottimes={}
try:
 while time.monotonic()-t<8:
  im=x.XGetImage(d,window,510,50,1,1,C.c_ulong(-1).value,2)
  if not im:raise RuntimeError('Window unavailable')
  v=x.XGetPixel(im,0,0)&0xffffff;x.XDestroyImage(im)
  if v!=last:changes.append(time.monotonic()-t);last=v
  values.append(v)
  for path in glob.glob('/dev/shm/darling-ca-frame-*'):
   with open(path,'rb') as f:
    h=struct.unpack('<6IQ',f.read(32))
    if h[2:4]!=(1536,864):continue
    f.seek(32+(32*1024*1024 if h[0]==0x43414632 and h[5]&0x40000000 else 0)+50*h[4]+510*4);pixel=struct.unpack('<I',f.read(4))[0]&0xffffff
    slotvalues.setdefault(path,[]).append(pixel);slotseq.setdefault(path,set()).add(h[1])
    timestamps=slottimes.setdefault(path,[])
    if not (h[1]&1) and (not timestamps or timestamps[-1][1]!=h[1]):timestamps.append((time.monotonic()-t,h[1]))
  time.sleep(.008)
 marker_changes=[]
 for v in values:
  if (v&65535)==0x64c8 and (not marker_changes or marker_changes[-1]!=(v>>16)):
   marker_changes.append(v>>16)
 backward_steps=sum((b-a)%256>128 for a,b in zip(marker_changes,marker_changes[1:]))
 state=None
 try: state=evaluate('window.__frameProbe')
 except (OSError,websocket.WebSocketException): state={'error':'renderer observation timed out'}
 gaps=[b-a for a,b in zip(changes,changes[1:])]
 print(json.dumps({'backward_steps':backward_steps,'samples':len(values),'display_changes':len(changes),'distinct_colors':len(set(values)),'unexpected_pixels':sum((v&65535)!=0x64c8 for v in values),'steady_unexpected_pixels':sum((v&65535)!=0x64c8 for v in values[next((i for i,v in enumerate(values) if (v&65535)==0x64c8),len(values)):]),'display_fps':round(len(changes)/8,1),'max_gap_ms':round(max(gaps,default=0)*1000,1),'renderer':state,'first_marker_sample':next((i for i,v in enumerate(values) if (v&65535)==0x64c8),None),'slots':{p:{'colors':len(set(v)),'unexpected':sum((c&65535)!=0x64c8 for c in v),'sequences':len(slotseq[p]),'max_sequence_gap_ms':round(max((b[0]-a[0] for a,b in zip(slottimes[p],slottimes[p][1:])),default=0)*1000,1)} for p,v in slotvalues.items()}}),flush=True)
finally:
 try: evaluate('document.getElementById("darling-frame-probe")?.remove()')
 except (OSError,websocket.WebSocketException): pass
 ws.close()
