#!/usr/bin/env python3
"""Check cursor pixels/hide/restore on an isolated X server. No Riot input.
Set CURSOR_TEST_DISPLAY=:99 and CURSOR_TEST_BINARY to the built guest probe.
"""
import ctypes as C,ctypes.util,os,re,subprocess,time
x=C.CDLL(ctypes.util.find_library('X11'));fix=C.CDLL(ctypes.util.find_library('Xfixes'))
x.XOpenDisplay.argtypes=[C.c_char_p];x.XOpenDisplay.restype=C.c_void_p
display=os.environ.get('CURSOR_TEST_DISPLAY',':1');d=x.XOpenDisplay(display.encode())
x.XDefaultRootWindow.argtypes=[C.c_void_p];x.XDefaultRootWindow.restype=C.c_ulong
root=x.XDefaultRootWindow(d)
x.XWarpPointer.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_int]
x.XFlush.argtypes=[C.c_void_p];x.XFree.argtypes=[C.c_void_p]
x.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint)]
r,c=C.c_ulong(),C.c_ulong();rx,ry,wx,wy=C.c_int(),C.c_int(),C.c_int(),C.c_int();mask=C.c_uint()
x.XQueryPointer(d,root,C.byref(r),C.byref(c),C.byref(rx),C.byref(ry),C.byref(wx),C.byref(wy),C.byref(mask))
saved_rx,saved_ry=rx.value,ry.value
class Cursor(C.Structure):
 _fields_=[('x',C.c_short),('y',C.c_short),('width',C.c_ushort),('height',C.c_ushort),('xhot',C.c_ushort),('yhot',C.c_ushort),('serial',C.c_ulong),('pixels',C.POINTER(C.c_ulong))]
fix.XFixesGetCursorImage.argtypes=[C.c_void_p];fix.XFixesGetCursorImage.restype=C.POINTER(Cursor)
def sample():
 p=fix.XFixesGetCursorImage(d);s=p.contents
 result={'width':s.width,'height':s.height,'visible':sum((s.pixels[i]>>24)&255!=0 for i in range(s.width*s.height))};x.XFree(p);return result
def warp(win,px,py):x.XWarpPointer(d,0,win,0,0,0,0,px,py);x.XFlush(d)
p='/tmp/riot-m280-cursor-test.log';f=open(p,'w');proc=subprocess.Popen(['darling',os.environ.get('CURSOR_TEST_BINARY','/tmp/opencode/m58f280-cursor-window')],stdout=f,stderr=subprocess.STDOUT,env={**os.environ,'DISPLAY':display,'EGL_PLATFORM':'x11','XMODIFIERS':'@im=none'})
checks={};deadline=time.monotonic()+30
try:
 while time.monotonic()<deadline and proc.poll() is None:
  text=open(p,'rb').read().decode(errors='replace');m=re.findall(r'CURSOR_WINDOW xid=(\d+) phase=(custom|hidden)',text)
  if m:
   win,phase=m[-1];win=int(win)
   if phase=='custom' and phase not in checks:
    warp(win,50,50);time.sleep(.15);x.XQueryPointer(d,win,C.byref(r),C.byref(c),C.byref(rx),C.byref(ry),C.byref(wx),C.byref(wy),C.byref(mask));print('CURSOR_CHECK pointer_inside',c.value==win,flush=True);checks[phase]=sample();print('CURSOR_CHECK custom',checks[phase],flush=True)
   if phase=='hidden' and phase not in checks:
    time.sleep(.1);checks[phase]=sample();print('CURSOR_CHECK hidden',checks[phase],flush=True)
    warp(win,51,50);time.sleep(.4);checks['restored']=sample();print('CURSOR_CHECK restored',checks['restored'],flush=True)
  time.sleep(.025)
 rc=proc.wait(timeout=5)
 passed=rc==0 and checks.get('custom',{}).get('visible',0)>0 and checks.get('hidden',{}).get('visible',-1)==0 and checks.get('restored',{}).get('visible',0)>0
 print('CURSOR_CHECK pass',passed,'exit',rc)
finally:warp(root,saved_rx,saved_ry);f.close()
raise SystemExit(0 if passed else 1)
