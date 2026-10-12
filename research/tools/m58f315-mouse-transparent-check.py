#!/usr/bin/env python3
"""Check native X11 input shape before and after restoring mouse handling."""
import ctypes as C
import ctypes.util
import os
import re
import subprocess
import time
x = C.CDLL(ctypes.util.find_library('X11'))
s = C.CDLL(ctypes.util.find_library('Xext'))
x.XOpenDisplay.argtypes = [C.c_char_p]
x.XOpenDisplay.restype = C.c_void_p
x.XFree.argtypes = [C.c_void_p]
s.XShapeGetRectangles.argtypes = [C.c_void_p,C.c_ulong,C.c_int,C.POINTER(C.c_int),C.POINTER(C.c_int)]
s.XShapeGetRectangles.restype = C.c_void_p
d = x.XOpenDisplay(b':99')
assert d, 'Xvfb :99 unavailable'
env = {**os.environ, 'DISPLAY':':99', 'EGL_PLATFORM':'x11',
       'DYLD_FRAMEWORK_PATH':'@GUEST_HOME@/RuntimeFrameworks', 'XMODIFIERS':'@im=none'}
env.pop('ELECTRON_RUN_AS_NODE',None)
log = '/tmp/m315-mouse-shape.log'
with open(log,'w') as f:
    p = subprocess.Popen(['darling','/tmp/m58f315-mouse-transparent'],env=env,stdout=f,stderr=subprocess.STDOUT)
    checked = set()
    deadline = time.monotonic()+30
    while time.monotonic()<deadline and p.poll() is None:
        for xid,ignored in re.findall(r'MOUSE_SHAPE xid=(\d+) ignored=([01])',open(log).read()):
            if ignored in checked: continue
            count,order = C.c_int(),C.c_int()
            rects = s.XShapeGetRectangles(d,int(xid),2,C.byref(count),C.byref(order))
            x.XFree(rects)
            assert (count.value==0)==(ignored=='1'), (ignored,count.value)
            checked.add(ignored)
            print('MOUSE_SHAPE ignored='+ignored+' rectangles='+str(count.value),flush=True)
        time.sleep(.05)
    assert checked=={'0','1'}, 'Both input shape states must be observed'
    assert p.wait(timeout=5)==0
