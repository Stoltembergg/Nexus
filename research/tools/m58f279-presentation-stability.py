#!/usr/bin/env python3
"""Sample a blank login-panel background pixel, without reading text or fields."""
import ctypes, ctypes.util, sys, time
x = ctypes.CDLL(ctypes.util.find_library('X11'))
x.XOpenDisplay.argtypes = [ctypes.c_char_p]; x.XOpenDisplay.restype = ctypes.c_void_p
x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
x.XGetImage.restype = ctypes.c_void_p
x.XGetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]; x.XGetPixel.restype = ctypes.c_ulong
x.XDestroyImage.argtypes = [ctypes.c_void_p]
x.XCloseDisplay.argtypes = [ctypes.c_void_p]
display = x.XOpenDisplay(b':1')
if not display: raise SystemExit('DISPLAY unavailable')
window = int(sys.argv[1], 0)
bright = dark = 0
for _ in range(100):
    image = x.XGetImage(display, window, 16, 500, 1, 1, ctypes.c_ulong(-1).value, 2)
    if not image: raise SystemExit('Window sample unavailable')
    pixel = x.XGetPixel(image, 0, 0)
    channels = [(pixel >> shift) & 255 for shift in (0, 8, 16)]
    bright += min(channels) > 200
    dark += max(channels) < 80
    x.XDestroyImage(image)
    time.sleep(.05)
x.XCloseDisplay(display)
print(f'PRESENT_STABILITY samples=100 bright={bright} dark={dark}')
