#!/usr/bin/env python3
"""Measure a temporary solid-color animation; never inspect field contents."""
import glob, struct, mmap
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
duration=float(sys.argv[2]) if len(sys.argv)>2 else 8.0
if not 2<=duration<=120:raise ValueError('Sampling duration must be between 2 and 120 seconds')
probe_rate=float(os.environ.get('RCLOL_FRAME_PROBE_RATE','0'))
if probe_rate<0 or probe_rate>240:raise ValueError('Probe rate must be 0 (unbounded), or at most 240 Hz')
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
# The presenter draws in an input-transparent child surface. Sampling the
# top-level window assumes a content origin that Cocoa titlebars can offset.
# Select only a live GPU target whose ancestry reaches the requested window.
x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
x.XQueryTree.restype=C.c_int
x.XFree.argtypes=[C.c_void_p]
root_window=window
gpu_target_path=None
for path in glob.glob('/dev/shm/darling-ca-gpu-target-*'):
 try:
  with open(path,'rb') as f:target=struct.unpack('<16I',f.read(64))
 except (OSError,struct.error):continue
 if target[0]!=0x47505532 or target[4]!=3:continue
 current=target[1]
 for depth in range(5):
  if current==root_window:
   window=target[1];gpu_target_path=path;break
  root=C.c_ulong();parent=C.c_ulong();children=C.POINTER(C.c_ulong)();count=C.c_uint()
  if not x.XQueryTree(d,current,C.byref(root),C.byref(parent),C.byref(children),C.byref(count)):break
  if children:x.XFree(children)
  if parent.value==current or not parent.value:break
  current=parent.value
 if window!=root_window:break
evaluate('''(()=>{document.getElementById("darling-frame-probe")?.remove();let e=document.createElement("div");e.id="darling-frame-probe";e.style="position:fixed;left:500px;top:40px;width:32px;height:32px;z-index:2147483647;pointer-events:none";document.body.append(e);let n=0,updates=0,next=0,start=performance.now(),bins=[],updateBins=[],rate=PROBE_RATE;window.__frameProbe={n:0,updates:0,elapsed:0,bins,updateBins,requestedRate:rate};function tick(){if(!e.isConnected)return;n++;let elapsed=performance.now()-start;if(!rate||elapsed>=next){updates++;e.style.backgroundColor="rgb("+(updates%256)+",100,200)";updateBins[Math.floor(elapsed/1000)]=(updateBins[Math.floor(elapsed/1000)]||0)+1;if(rate)next=(Math.floor(elapsed*rate/1000)+1)*1000/rate;}bins[Math.floor(elapsed/1000)]=(bins[Math.floor(elapsed/1000)]||0)+1;window.__frameProbe={n,updates,elapsed,bins,updateBins,requestedRate:rate};if(performance.now()-start<12000)requestAnimationFrame(tick);else e.remove()}requestAnimationFrame(tick);return true})()'''.replace('12000',str(int((duration+4)*1000))).replace('PROBE_RATE',str(probe_rate)))
t=time.monotonic();values=[];changes=[];last=None;slotvalues={};slotseq={};slottimes={}
try:
 if os.environ.get('RCLOL_FRAME_METADATA_ONLY')=='1':
  if not gpu_target_path:raise RuntimeError('No live native GPU presentation metadata')
  with open(gpu_target_path,'rb') as metadata_file:
   with mmap.mmap(metadata_file.fileno(),64,access=mmap.ACCESS_READ) as metadata:
    initial_header=struct.unpack_from('<16I',metadata);initial=initial_header[6];previous=initial;swaps=[];samples=0
    clock_path='/dev/shm/darling-cvlink-'+str(initial_header[5])+'.state'
    def clock_ticks():
     try:
      with open(clock_path,'rb') as clock_file:record=clock_file.read(64)
      return struct.unpack_from('<I',record,32)[0] if len(record)==64 and struct.unpack_from('<I',record)[0]==0xc81dfa10 else None
     except OSError:return None
    initial_ticks=clock_ticks()
    while time.monotonic()-t<duration:
     header=struct.unpack_from('<16I',metadata)
     if header[0]!=0x47505532 or header[1]!=window or header[4]!=3:raise RuntimeError('Native presentation target became unavailable')
     current=header[6];delta=(current-previous)&0xffffffff
     if delta:
      if delta>1000:raise RuntimeError('Native presentation counter reset')
      swaps.append((time.monotonic()-t,delta));previous=current
     samples+=1;time.sleep(.004)
  state=evaluate('window.__frameProbe')
  gaps=[b[0]-a[0] for a,b in zip(swaps,swaps[1:])]
  timing={}
  final_ticks=clock_ticks()
  if initial_ticks is not None and final_ticks is not None:timing['display_link_ticks_per_second']=round(((final_ticks-initial_ticks)&0xffffffff)/duration,2)
  if header[15] in (0x544d4731,0x544d4732):
   delta=lambda index:(header[index]-initial_header[index])&0xffffffff
   count=sum(n for _,n in swaps)
   timing.update({'native_vsync':header[15]==0x544d4732,'producer_fps':round(delta(9)/duration,2),'empty_polls':delta(10),'phase_resets':delta(11),'average_swap_work_ms':round(delta(12)/max(count,1)/1000,3),'upload_calls_per_second':round(delta(13)/duration,2),'average_upload_ms':round(delta(14)/max(delta(13),1)/1000,3)})
  print(json.dumps({'sample_window':window,'requested_window':root_window,'measurement':'successful-native-swaps-without-pixel-readback','samples':samples,'duration_seconds':duration,'presentation_fps':round(sum(n for _,n in swaps)/duration,2),'second_fps':[sum(n for stamp,n in swaps if second<=stamp<second+1) for second in range(int(duration))],'max_swap_gap_ms':round(max(gaps,default=0)*1000,1),'renderer':state,'timing':timing}),flush=True)
  raise SystemExit(0)
 native_initial=None
 if gpu_target_path:
  with open(gpu_target_path,'rb') as metadata_file:native_initial=struct.unpack('<16I',metadata_file.read(64))
 while time.monotonic()-t<duration:
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
 if not marker_changes:raise RuntimeError('Synthetic marker never reached the sampled drawable; FPS result is invalid')
 state=None
 try: state=evaluate('window.__frameProbe')
 except (OSError,websocket.WebSocketException): state={'error':'renderer observation timed out'}
 gaps=[b-a for a,b in zip(changes,changes[1:])]
 native_observation={}
 if native_initial is not None:
  with open(gpu_target_path,'rb') as metadata_file:native_final=struct.unpack('<16I',metadata_file.read(64))
  if native_final[0]==0x47505532 and native_final[1]==window and native_final[4]==3:
   native_swaps=(native_final[6]-native_initial[6])&0xffffffff
   native_observation={'successful_swaps':native_swaps,'presentation_fps':round(native_swaps/duration,2),'native_vsync':native_final[15]==0x544d4732}
 print(json.dumps({'native':native_observation,'sample_window':window,'requested_window':root_window,'backward_steps':backward_steps,'samples':len(values),'display_changes':len(changes),'distinct_colors':len(set(values)),'unexpected_pixels':sum((v&65535)!=0x64c8 for v in values),'steady_unexpected_pixels':sum((v&65535)!=0x64c8 for v in values[next((i for i,v in enumerate(values) if (v&65535)==0x64c8),len(values)):]),'second_fps':[sum(second<=c<second+1 for c in changes) for second in range(int(duration))],'duration_seconds':duration,'display_fps':round(len(changes)/duration,2),'steady_display_fps':round(sum(c>=1 for c in changes)/(duration-1),2),'max_gap_ms':round(max(gaps,default=0)*1000,1),'renderer':state,'first_marker_sample':next((i for i,v in enumerate(values) if (v&65535)==0x64c8),None),'slots':{p:{'colors':len(set(v)),'unexpected':sum((c&65535)!=0x64c8 for c in v),'sequences':len(slotseq[p]),'max_sequence_gap_ms':round(max((b[0]-a[0] for a,b in zip(slottimes[p],slottimes[p][1:])),default=0)*1000,1)} for p,v in slotvalues.items()}}),flush=True)
finally:
 try: evaluate('(()=>{document.getElementById("darling-frame-probe")?.remove();delete window.__frameProbe})()')
 except (OSError,websocket.WebSocketException): pass
 ws.close()
