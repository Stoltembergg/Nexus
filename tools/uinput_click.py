#!/usr/bin/env python3
"""Real (kernel-level) mouse clicks at compositor cursor positions, for driving the game without XTEST.

  uinput_click.py X Y [count] [X Y [count] ...]     move the Hyprland cursor to X,Y (global layout px), click `count` times
XTEST clicks never reached League's panel on this setup (hover worked, clicks did nothing); a uinput device produces
the same wl_pointer events as a physical mouse. Needs /dev/uinput (group uinput) and hyprctl.
"""
import fcntl, os, struct, subprocess, sys, time

EV_SYN, EV_KEY, EV_REL = 0, 1, 2
BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA = 0x110, 0x111, 0x112, 0x113, 0x114
REL_X, REL_Y, REL_HWHEEL, REL_WHEEL = 0, 1, 6, 8
_active_mouse = None

class Mouse:
    def __init__(self):
        global _active_mouse
        self.fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.fd, 0x40045564, EV_KEY)     # UI_SET_EVBIT
        fcntl.ioctl(self.fd, 0x40045564, EV_REL)
        fcntl.ioctl(self.fd, 0x40045565, BTN_LEFT)   # UI_SET_KEYBIT
        for button in (BTN_RIGHT, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA):
            fcntl.ioctl(self.fd, 0x40045565, button)
        fcntl.ioctl(self.fd, 0x40045566, REL_X)      # UI_SET_RELBIT
        for axis in (REL_Y, REL_HWHEEL, REL_WHEEL):
            fcntl.ioctl(self.fd, 0x40045566, axis)
        setup = struct.pack('<HHHH80sI', 0x03, 0x1234, 0x5678, 1, b'rclol-virtual-mouse', 0)
        fcntl.ioctl(self.fd, 0x405c5503, setup)      # UI_DEV_SETUP
        fcntl.ioctl(self.fd, 0x5501)                 # UI_DEV_CREATE
        time.sleep(1.0)                              # let the compositor pick the device up
        _active_mouse = self

    def emit(self, etype, code, value):
        os.write(self.fd, struct.pack('<qqHHi', 0, 0, etype, code, value))

    def syn(self):
        self.emit(EV_SYN, 0, 0)

    def click(self, count=1, hold=0.06, gap=0.12, button=BTN_LEFT):
        for _ in range(count):
            self.emit(EV_KEY, button, 1); self.syn(); time.sleep(hold)
            self.emit(EV_KEY, button, 0); self.syn(); time.sleep(gap)

    def close(self):
        global _active_mouse
        if _active_mouse is self:
            _active_mouse = None
        fcntl.ioctl(self.fd, 0x5502)                 # UI_DEV_DESTROY
        os.close(self.fd)

def move(x, y):
    subprocess.run(['hyprctl', 'eval', f'hl.dispatch(hl.dsp.cursor.move({{x={x},y={y}}}))'], check=True, stdout=subprocess.DEVNULL)
    if _active_mouse is not None:
        # A compositor warp alone leaves X11's last physical position stale.
        # Deliver motion at the new position so free-camera edge scrolling stops.
        _active_mouse.emit(EV_REL, REL_X, 1); _active_mouse.syn(); time.sleep(.02)
        _active_mouse.emit(EV_REL, REL_X, -1); _active_mouse.syn(); time.sleep(.02)

def hover(x, y, settle=0.35):
    move(x - 2, y - 2); time.sleep(0.1); move(x, y); time.sleep(settle)

if __name__ == '__main__':
    args = [int(a) for a in sys.argv[1:]]
    if not args or len(args) % 3:
        sys.exit(__doc__)
    mouse = Mouse()
    try:
        for x, y, n in zip(args[0::3], args[1::3], args[2::3]):
            hover(x, y)
            mouse.click(n)
    finally:
        mouse.close()
