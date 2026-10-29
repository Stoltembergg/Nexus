"""Neutral private-session wire probe; never contacts the desktop session."""
import ctypes
import os
from pathlib import Path
import select
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
if len(sys.argv) == 1:
    os.execvp('dbus-run-session', ['dbus-run-session', '--', sys.executable, __file__, 'private'])

class Entry(ctypes.Structure):
    _fields_ = [('id', ctypes.c_int32), ('parent', ctypes.c_int32),
                ('label', ctypes.c_char_p), ('flags', ctypes.c_uint32), ('state', ctypes.c_int32)]

lib = ctypes.CDLL(str(root / 'build/dbusmenu-properties-experiment/libdarling-status-notifier.so'))
lib.DarlingStatusNotifierCreate.argtypes = [ctypes.c_char_p] * 3
lib.DarlingStatusNotifierCreate.restype = ctypes.c_void_p
lib.DarlingStatusNotifierBusName.argtypes = [ctypes.c_void_p]
lib.DarlingStatusNotifierBusName.restype = ctypes.c_char_p
lib.DarlingStatusNotifierSetMenu.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry), ctypes.c_uint32]
lib.DarlingStatusNotifierDestroy.argtypes = [ctypes.c_void_p]
obj = lib.DarlingStatusNotifierCreate(b'neutral-probe', b'Neutral', b'')
assert obj
name = lib.DarlingStatusNotifierBusName(obj).decode()
monitor = subprocess.Popen(['gdbus', 'monitor', '--session', '--dest', name, '--object-path', '/Menu'],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
try:
    assert select.select([monitor.stdout], [], [], 8)[0]
    assert b'Monitoring signals' in monitor.stdout.readline()
    assert select.select([monitor.stdout], [], [], 8)[0]
    assert b'is owned by' in monitor.stdout.readline()
    entries = (Entry * 1)(Entry(7, 0, b'Before', 3, 0))
    assert lib.DarlingStatusNotifierSetMenu(obj, entries, 1)
    entries[0].label = b'After'
    entries[0].flags = 2 | 8
    entries[0].state = 1
    assert lib.DarlingStatusNotifierSetMenu(obj, entries, 1)
    assert lib.DarlingStatusNotifierSetMenu(obj, entries, 1)
    observed = b''
    while b"'toggle-state'" not in observed:
        assert select.select([monitor.stdout], [], [], 8)[0], observed
        observed += os.read(monitor.stdout.fileno(), 4096)
    text = observed.decode()
    assert text.count('.LayoutUpdated ') == 2, text
    assert text.count('.ItemsPropertiesUpdated ') == 2, text
    assert "'label': <'After'>" in text and "'enabled': <false>" in text, text
    assert "'toggle-type': <'checkmark'>" in text and "'toggle-state': <1>" in text, text
    print('PRIVATE_WIRE_PASS', text)
finally:
    lib.DarlingStatusNotifierDestroy(obj)
    monitor.terminate()
    monitor.communicate(timeout=8)
