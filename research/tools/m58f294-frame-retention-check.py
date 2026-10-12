#!/usr/bin/env python3
"""Validate remote pixels, exposure repair, and empty input shape on Xvfb."""
import ctypes as C, ctypes.util, os, re, subprocess, time
x=C.CDLL(ctypes.util.find_library('X11')); shape=C.CDLL(ctypes.util.find_library('Xext'))
x.XOpenDisplay.argtypes=[C.c_char_p];x.XOpenDisplay.restype=C.c_void_p
d=x.XOpenDisplay(os.environ.get('FRAME_TEST_DISPLAY',':99').encode())
x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
x.XGetImage.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_ulong,C.c_int];x.XGetImage.restype=C.c_void_p
x.XGetPixel.argtypes=[C.c_void_p,C.c_int,C.c_int];x.XGetPixel.restype=C.c_ulong
x.XDestroyImage.argtypes=[C.c_void_p];x.XFree.argtypes=[C.c_void_p]
x.XClearArea.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int];x.XFlush.argtypes=[C.c_void_p]
class Rect(C.Structure):_fields_=[('x',C.c_short),('y',C.c_short),('w',C.c_ushort),('h',C.c_ushort)]
shape.XShapeGetRectangles.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.POINTER(C.c_int),C.POINTER(C.c_int)];shape.XShapeGetRectangles.restype=C.POINTER(Rect)
def pixel(w):
 im=x.XGetImage(d,w,20,20,1,1,C.c_ulong(-1).value,2)
 v=x.XGetPixel(im,0,0)&0xffffff;x.XDestroyImage(im);return v
probe_env=dict(os.environ)
probe_env.pop('ELECTRON_RUN_AS_NODE',None)
log='/tmp/riot-m280-frame-test.log'
with open(log,'w') as f:
 p=subprocess.Popen(['darling',os.environ.get('FRAME_TEST_BINARY','/tmp/opencode/m58f294-frame-retention')],stdout=f,stderr=subprocess.STDOUT,env={**probe_env,'DISPLAY':os.environ.get('FRAME_TEST_DISPLAY',':99'),'EGL_PLATFORM':'x11','XMODIFIERS':'@im=none','DYLD_FRAMEWORK_PATH':os.environ.get('DYLD_FRAMEWORK_PATH','@GUEST_HOME@/RuntimeFrameworks'),'DARLING_XSHM_LIBRARY':os.environ.get('DARLING_XSHM_LIBRARY','@GUEST_HOME@/libDarlingXShm.dylib')})
 checks={};end=time.monotonic()+30
 while time.monotonic()<end and p.poll() is None:
  matches=re.findall(r'FRAME_WINDOW xid=(\d+) phase=(first|updated)',open(log,'rb').read().decode(errors='replace'))
  if matches:
   w,phase=matches[-1];w=int(w)
   if phase not in checks:
    root,parent=C.c_ulong(),C.c_ulong();children=C.POINTER(C.c_ulong)();n=C.c_uint()
    x.XQueryTree(d,w,C.byref(root),C.byref(parent),C.byref(children),C.byref(n))
    if not n.value: raise RuntimeError('No presentation child')
    overlay=children[n.value-1];x.XFree(children)
    nr,order=C.c_int(),C.c_int();rects=shape.XShapeGetRectangles(d,overlay,2,C.byref(nr),C.byref(order));x.XFree(rects)
    expected=0x113355 if phase=='first' else 0x775533
    x.XCreateSimpleWindow.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong];x.XCreateSimpleWindow.restype=C.c_ulong
    x.XMapRaised.argtypes=[C.c_void_p,C.c_ulong];x.XDestroyWindow.argtypes=[C.c_void_p,C.c_ulong]
    sibling=x.XCreateSimpleWindow(d,w,0,0,100,122,0,0,0xff0000)
    x.XMapRaised(d,sibling);x.XFlush(d);time.sleep(.1)
    stacking=pixel(w)==expected
    x.XDestroyWindow(d,sibling);x.XFlush(d)
    if not stacking:raise RuntimeError('Local sibling covered retained remote frame')
    print('FRAME_STACKING retained True',flush=True)
    samples=[pixel(w) for _ in range(30)]
    if phase=='first':
     import glob, struct
     slots=[]
     for path in glob.glob('/dev/shm/darling-ca-frame-*'):
      with open(path,'rb') as sf: header=sf.read(32)
      if len(header)==32 and struct.unpack('<6IQ',header)[2:4]==(100,122): slots.append(path)
     path=max(slots,key=os.path.getmtime)
     if os.environ.get('FRAME_TEST_PUMP'):
      with open(path,'r+b',buffering=0) as sf:
       header=bytearray(sf.read(32));base=32+(32*1024*1024 if struct.unpack_from('<I',header,0)[0]==0x43414632 and struct.unpack_from('<I',header,20)[0]&0x40000000 else 0);sf.seek(base);original=sf.read(48800);seq=struct.unpack_from('<I',header,4)[0]
       sf.seek(4);sf.write(struct.pack('<I',seq|1));sf.seek(base);sf.write(bytes.fromhex('775533ff')*(48800//4));sf.seek(4);sf.write(struct.pack('<I',seq+2))
       start=time.monotonic()
       while pixel(w)!=0x335577 and time.monotonic()-start<.25:time.sleep(.005)
       changed=pixel(w)==0x335577
       sf.seek(4);sf.write(struct.pack('<I',(seq+2)|1));sf.seek(base);sf.write(original);sf.seek(4);sf.write(struct.pack('<I',seq+4))
      time.sleep(.06)
      print('BLOCKED_MAIN_FRAME changed',changed,'latency_ms',round((time.monotonic()-start-.06)*1000,1),flush=True)
      if not changed:raise RuntimeError('Frame pump stalled with blocked AppKit thread')
     with open(path,'r+b',buffering=0) as sf:
      saved=bytearray(sf.read(32));header=bytearray(saved)
      if struct.unpack_from('<I',header,0)[0]==0x43414632:
       seq=struct.unpack_from('<I',header,4)[0];format=struct.unpack_from('<I',header,20)[0]
       inactive=32+(0 if format&0x40000000 else 32*1024*1024)
       sf.seek(inactive);sf.write(bytes.fromhex('775533ff')*(48800//4))
       time.sleep(.06)
       if pixel(w)!=expected:raise RuntimeError('Incomplete back buffer became visible')
       struct.pack_into('<I',header,4,seq+2);struct.pack_into('<I',header,20,format^0x40000000)
       sf.seek(0);sf.write(header);time.sleep(.06)
       if pixel(w)!=0x335577:raise RuntimeError('Committed back buffer did not appear')
       struct.pack_into('<I',saved,4,seq+4);sf.seek(0);sf.write(saved);time.sleep(.06)
       if pixel(w)!=expected:raise RuntimeError('Restored front buffer did not appear')
       print('DOUBLE_BUFFER source_in_progress retained True commit True',flush=True)
     stale='/dev/shm/darling-ca-frame-%d-2147483646'%os.getuid()
     with open(path,'rb') as source: snapshot=bytearray(source.read(32))
     base=32+(32*1024*1024 if struct.unpack_from('<I',snapshot,0)[0]==0x43414632 and struct.unpack_from('<I',snapshot,20)[0]&0x40000000 else 0)
     struct.pack_into('<I',snapshot,20,struct.unpack_from('<I',snapshot,20)[0]&0x7fffffff)
     with open(stale,'wb') as target:
      target.write(snapshot);target.seek(base);target.write(bytes.fromhex('cc22aaff')*(48800//4))
     try:
      competing=[pixel(w) for _ in range(20)]
      time.sleep(.4);competing.append(pixel(w))
      if not all(v==expected for v in competing):raise RuntimeError('Stale readback replaced software pixels')
      print('SOFTWARE_PRIORITY retained True',flush=True)
     finally: os.unlink(stale)
     with open(path,'r+b',buffering=0) as sf:
      sf.seek(4);saved=sf.read(4);sf.seek(4);sf.write(struct.pack('<I',struct.unpack('<I',saved)[0]|1))
      try:
       for _ in range(25): time.sleep(.02);samples.append(pixel(w))
      finally: sf.seek(4);sf.write(saved)
     print('IN_PROGRESS_FRAME retained',all(v==expected for v in samples),flush=True)
    x.XClearArea(d,overlay,0,0,0,0,1);x.XFlush(d);time.sleep(.15)
    repaired=pixel(w)
    checks[phase]=all(v==expected for v in samples) and repaired==expected and nr.value==0
    print('FRAME_CHECK',phase,'samples',len(samples),'pixel',hex(samples[0]),'exposure_repaired',repaired==expected,'input_rectangles',nr.value,flush=True)
  time.sleep(.025)
 rc=p.wait(timeout=5)
 passed=rc==0 and len(checks)==2 and all(checks.values())
 print('FRAME_CHECK pass',passed,'exit',rc)
raise SystemExit(0 if passed else 1)
