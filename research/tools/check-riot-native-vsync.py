#!/usr/bin/env python3
"""Present generated colors only into an owned X11 test window."""
import argparse
import ctypes as C
import ctypes.util
import json
import os
import signal
import shutil
from pathlib import Path
import struct
import subprocess
import tempfile
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--producer-hz',type=int,choices=(60,120),default=60)
args=parser.parse_args()
root = Path(__file__).resolve().parent.parent
width, height = 337, 339
path = Path(f'/dev/shm/darling-ca-gpu-target-{os.getuid()}-{width}-{height}')

def owned_guests():
    result = {}
    binary = str(root / 'build/m327-cgl-direct-check')
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if binary in entry.joinpath('maps').read_text():
                result[int(entry.name)] = entry.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19]
        except OSError:
            pass
    return result

class VisualInfo(C.Structure):
    _fields_ = [('visual', C.c_void_p), ('id', C.c_ulong), ('screen', C.c_int),
                ('depth', C.c_int), ('kind', C.c_int), ('red', C.c_ulong),
                ('green', C.c_ulong), ('blue', C.c_ulong),
                ('colormap_size', C.c_int), ('bits', C.c_int)]

class Attributes(C.Structure):
    _fields_ = [('background_pixmap', C.c_ulong), ('background_pixel', C.c_ulong),
                ('border_pixmap', C.c_ulong), ('border_pixel', C.c_ulong),
                ('bit_gravity', C.c_int), ('win_gravity', C.c_int),
                ('backing_store', C.c_int), ('backing_planes', C.c_ulong),
                ('backing_pixel', C.c_ulong), ('save_under', C.c_int),
                ('event_mask', C.c_long), ('propagate', C.c_long),
                ('override_redirect', C.c_int), ('colormap', C.c_ulong),
                ('cursor', C.c_ulong)]

x = C.CDLL(ctypes.util.find_library('X11'))
def bind(name, result, args):
    fn = getattr(x, name)
    fn.restype, fn.argtypes = result, args
    return fn
open_display = bind('XOpenDisplay', C.c_void_p, [C.c_char_p])
root_window = bind('XDefaultRootWindow', C.c_ulong, [C.c_void_p])
get_visual = bind('XGetVisualInfo', C.POINTER(VisualInfo),
                  [C.c_void_p, C.c_long, C.POINTER(VisualInfo), C.POINTER(C.c_int)])
create_colormap = bind('XCreateColormap', C.c_ulong,
                       [C.c_void_p, C.c_ulong, C.c_void_p, C.c_int])
create_window = bind('XCreateWindow', C.c_ulong,
                     [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint,
                      C.c_uint, C.c_uint, C.c_int, C.c_uint, C.c_void_p,
                      C.c_ulong, C.POINTER(Attributes)])
map_window = bind('XMapWindow', C.c_int, [C.c_void_p, C.c_ulong])
sync = bind('XSync', C.c_int, [C.c_void_p, C.c_int])
destroy_window = bind('XDestroyWindow', C.c_int, [C.c_void_p, C.c_ulong])
free_colormap = bind('XFreeColormap', C.c_int, [C.c_void_p, C.c_ulong])
free = bind('XFree', C.c_int, [C.c_void_p])
close_display = bind('XCloseDisplay', C.c_int, [C.c_void_p])
get_image = bind('XGetImage', C.c_void_p,
                 [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint,
                  C.c_uint, C.c_ulong, C.c_int])
get_pixel = bind('XGetPixel', C.c_ulong, [C.c_void_p, C.c_int, C.c_int])
destroy_image = bind('XDestroyImage', C.c_int, [C.c_void_p])

display = open_display(os.environ.get('DISPLAY', ':1').encode())
if not display:
    raise RuntimeError('X11 display unavailable')
window = colormap = 0
fd = None
visuals = None
try:
    # O_EXCL prevents replacing any existing application presentation target.
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    query = VisualInfo(depth=32, kind=4)
    count = C.c_int()
    visuals = get_visual(display, 4 | 8, C.byref(query), C.byref(count))
    if not visuals or not count.value:
        raise RuntimeError('No 32-bit TrueColor visual')
    visual = visuals[0]
    colormap = create_colormap(display, root_window(display), visual.visual, 0)
    attrs = Attributes(override_redirect=1, colormap=colormap)
    window = create_window(display, root_window(display), 40, 40, width, height,
                           0, visual.depth, 1, visual.visual, 2 | 8 | 512 | 8192,
                           C.byref(attrs))
    # The generated fixture must not intercept the user's pointer input.
    shape = C.CDLL(ctypes.util.find_library('Xext'))
    shape.XShapeCombineRectangles.argtypes = [C.c_void_p, C.c_ulong, C.c_int,
        C.c_int, C.c_int, C.c_void_p, C.c_int, C.c_int, C.c_int]
    shape.XShapeCombineRectangles(display, window, 2, 0, 0, None, 0, 0, 0)
    map_window(display, window)
    sync(display, 0)
    os.write(fd, struct.pack('<16I', 0x47505532, window, width, height, 2,
                             0, 0, visual.id, visual.depth, *([0] * 7)))
    framework_root = root / 'build/riot-native-vsync-check-frameworks'
    framework = framework_root / 'OpenGL.framework'
    (framework / 'Versions/A').mkdir(parents=True, exist_ok=True)
    binary = framework / 'Versions/A/OpenGL'
    shutil.copy2(root / 'build/m327-OpenGL', str(binary) + '.next')
    Path(str(binary) + '.next').replace(binary)
    for link, target in ((framework / 'Versions/Current', 'A'),
                         (framework / 'OpenGL', 'Versions/Current/OpenGL')):
        if not link.is_symlink():
            link.symlink_to(target)
    frameworks = '/Volumes/SystemRoot' + str(framework_root)
    environment = dict(os.environ, DISPLAY=os.environ.get('DISPLAY', ':1'),
                       DYLD_LIBRARY_PATH='@GUEST_HOME@/RuntimeLibraries',
                       DYLD_FRAMEWORK_PATH=frameworks + ':@GUEST_HOME@/RuntimeFrameworks',
                       EGL_PLATFORM='x11', mesa_glthread='false',
                       RCLOL_GPU_DIRECT_PRESENT='1', RCLOL_GPU_DIRECT_ASYNC='1', RCLOL_GPU_DIRECT_VSYNC='1')
    previous = owned_guests()
    changes = []
    last = None
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(['darling', 'shell', '/Volumes/SystemRoot' +
                                        str(root / 'build/m327-cgl-direct-check'),str(args.producer_hz)],
                                       env=environment, stdout=output, stderr=output)
            deadline = time.monotonic() + 20
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait(timeout=3)
                    raise subprocess.TimeoutExpired(process.args, 20)
                image = get_image(display, window, 10, 10, 1, 1, C.c_ulong(-1).value, 2)
                if image:
                    color = get_pixel(image, 0, 0) & 0xffffff
                    destroy_image(image)
                    if color & 0xffff == 0x64c8 and color != last:
                        changes.append(time.monotonic())
                        last = color
                time.sleep(.004)
        except subprocess.TimeoutExpired:
            for pid, identity in owned_guests().items():
                if pid not in previous and owned_guests().get(pid) == identity:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            raise
        output.seek(0)
        for line in output.read().decode(errors='replace').splitlines():
            if line.startswith(('DIRECT_SOURCE', 'DIRECT_PRESENT')):
                print(line)
    header = struct.unpack('<16I', os.pread(fd, 64, 0))
    visible_fps = (len(changes)-1)/(changes[-1]-changes[0]) if len(changes)>1 else 0
    expected = 360 * 60 / args.producer_hz
    passed = (process.returncode == 0 and header[15] == 0x544d4732 and
              header[9] == 360 and expected*.95 <= header[6] <= expected+3 and
              len(changes) >= expected*.95 and 58 <= visible_fps <= 62)
    print(json.dumps({'pass': passed, 'owned_window': True, 'producer_hz': args.producer_hz, 'native_vsync': header[15] == 0x544d4732,
                      'successful_swaps': header[6], 'submissions': header[9],
                      'visible_frames': len(changes),
                      'visible_fps': round(visible_fps, 2),
                      'exit': process.returncode}))
    raise SystemExit(0 if passed else 1)
finally:
    if fd is not None:
        os.close(fd)
        path.unlink(missing_ok=True)
    if window:
        destroy_window(display, window)
    if colormap:
        free_colormap(display, colormap)
    if visuals:
        free(visuals)
    close_display(display)
