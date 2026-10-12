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
log='/tmp/riot-m280-frame-test.log'
with open(log,'w') as f:
 p=subprocess.Popen(['darling',os.environ.get('FRAME_TEST_BINARY','/tmp/opencode/m58f280-frame-window')],stdout=f,stderr=subprocess.STDOUT,env={**os.environ,'DISPLAY':os.environ.get('FRAME_TEST_DISPLAY',':99'),'EGL_PLATFORM':'x11','XMODIFIERS':'@im=none'})
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
    samples=[pixel(w) for _ in range(30)]
    x.XClearArea(d,overlay,0,0,0,0,1);x.XFlush(d);time.sleep(.15)
    repaired=pixel(w)
    checks[phase]=all(v==expected for v in samples) and repaired==expected and nr.value==0
    print('FRAME_CHECK',phase,'samples',len(samples),'pixel',hex(samples[0]),'exposure_repaired',repaired==expected,'input_rectangles',nr.value,flush=True)
  time.sleep(.025)
 rc=p.wait(timeout=5)
 passed=rc==0 and len(checks)==2 and all(checks.values())
 print('FRAME_CHECK pass',passed,'exit',rc)
raise SystemExit(0 if passed else 1)
