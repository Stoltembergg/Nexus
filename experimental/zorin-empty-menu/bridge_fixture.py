import ctypes
import sys

class Entry(ctypes.Structure):
    _fields_ = [('id', ctypes.c_int32), ('parent', ctypes.c_int32),
                ('label', ctypes.c_char_p), ('flags', ctypes.c_uint32), ('state', ctypes.c_int32)]

lib = ctypes.CDLL(sys.argv[1])
lib.DarlingStatusNotifierCreate.argtypes = [ctypes.c_char_p] * 3
lib.DarlingStatusNotifierCreate.restype = ctypes.c_void_p
lib.DarlingStatusNotifierBusName.argtypes = [ctypes.c_void_p]
lib.DarlingStatusNotifierBusName.restype = ctypes.c_char_p
lib.DarlingStatusNotifierSetMenu.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry), ctypes.c_uint32]
lib.DarlingStatusNotifierDestroy.argtypes = [ctypes.c_void_p]
obj = lib.DarlingStatusNotifierCreate(b'zorin-probe', b'Zorin probe', b'')
assert obj
try:
    flags = 1 if sys.argv[2] == 'hidden' else 3
    entries = (Entry * 4)(*(Entry(i, 0, b'', flags, 0) for i in range(1, 5)))
    assert lib.DarlingStatusNotifierSetMenu(obj, entries, 4)
    print(lib.DarlingStatusNotifierBusName(obj).decode(), flush=True)
    for line in sys.stdin:
        if line.strip() == 'update':
            for i, label in enumerate((b'One', b'Two', b'Three')):
                entries[i].label = label
            assert lib.DarlingStatusNotifierSetMenu(obj, entries, 4)
            print('updated', flush=True)
        elif line.strip() == 'quit':
            break
finally:
    lib.DarlingStatusNotifierDestroy(obj)
