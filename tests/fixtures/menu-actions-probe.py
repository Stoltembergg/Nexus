"""Drive the native transport on a private bus and report what the host owns.

The probe never touches the real desktop: it runs below dbus-run-session and
uses its own bus name.
"""
import ctypes
import os
import subprocess
import sys
import time


class Event(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int32)
                for name in ('kind', 'x', 'y', 'delta', 'horizontal')]


class MenuEntry(ctypes.Structure):
    _fields_ = [('id', ctypes.c_int32), ('parent', ctypes.c_int32),
                ('label', ctypes.c_char_p), ('flags', ctypes.c_uint32),
                ('toggle_state', ctypes.c_int32)]


def load(path):
    lib = ctypes.CDLL(str(path))
    lib.DarlingStatusNotifierCreate.argtypes = [ctypes.c_char_p] * 3
    lib.DarlingStatusNotifierCreate.restype = ctypes.c_void_p
    lib.DarlingStatusNotifierDestroy.argtypes = [ctypes.c_void_p]
    lib.DarlingStatusNotifierBusName.argtypes = [ctypes.c_void_p]
    lib.DarlingStatusNotifierBusName.restype = ctypes.c_char_p
    lib.DarlingStatusNotifierPoll.argtypes = [ctypes.c_void_p, ctypes.POINTER(Event)]
    lib.DarlingStatusNotifierSetMenu.argtypes = [ctypes.c_void_p,
                                                 ctypes.POINTER(MenuEntry), ctypes.c_uint32]
    return lib


def main():
    library, helper = sys.argv[1], sys.argv[2]
    os.environ['DARLING_STATUS_MENU_ACTION_SCRIPT'] = helper
    lib = load(library)
    item = lib.DarlingStatusNotifierCreate(b'darling-actions-test', b'Teste de acoes', b'')
    assert item
    name = lib.DarlingStatusNotifierBusName(item).decode()

    def menu_call(method, *args):
        return subprocess.run(['gdbus', 'call', '--session', '--dest', name,
                               '--object-path', '/Menu', '--method',
                               'com.canonical.dbusmenu.' + method, '--', *args],
                              text=True, capture_output=True, timeout=15)

    entries = (MenuEntry * 2)(MenuEntry(10, 0, b'Configuracoes', 3, -1),
                               MenuEntry(11, 0, b'Sair', 3, -1))
    assert lib.DarlingStatusNotifierSetMenu(item, entries, 2)
    time.sleep(0.5)

    layout = menu_call('GetLayout', '0', '-1', '[]').stdout
    print('LAYOUT=' + layout.strip(), flush=True)

    # The host owns the actions: the click must not reach the guest. The
    # guest already provided a "Sair", so the project added only the
    # "Riot Games" entry with its own ID.
    clicked = menu_call('Event', '1000002', 'clicked', '<0>', '0')
    print('EVENT_OK=' + str(clicked.returncode == 0), flush=True)
    time.sleep(1.0)

    # A guest entry with the same label is owned by the host as well.
    guest_clicked = menu_call('Event', '11', 'clicked', '<0>', '0')
    print('GUEST_EVENT_OK=' + str(guest_clicked.returncode == 0), flush=True)
    time.sleep(1.0)

    # An ordinary entry still reaches the guest.
    ordinary = menu_call('Event', '10', 'clicked', '<0>', '0')
    print('ORDINARY_EVENT_OK=' + str(ordinary.returncode == 0), flush=True)
    time.sleep(0.5)

    kinds = []
    event = Event()
    while lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)):
        kinds.append(event.kind)
    print('EVENTS=' + ','.join(str(kind) for kind in kinds), flush=True)
    lib.DarlingStatusNotifierDestroy(item)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
