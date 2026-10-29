"""Private-bus proof of the experimental real native menu producer."""
import ctypes
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Event(ctypes.Structure):
    _fields_ = [(n, ctypes.c_int32) for n in ('kind', 'x', 'y', 'delta', 'horizontal')]


class Entry(ctypes.Structure):
    _fields_ = [('id', ctypes.c_int32), ('parent', ctypes.c_int32),
                ('label', ctypes.c_char_p), ('flags', ctypes.c_uint32),
                ('toggle_state', ctypes.c_int32)]


def probe(library, log):
    lib = ctypes.CDLL(library)
    lib.DarlingStatusNotifierCreate.argtypes = [ctypes.c_char_p] * 3
    lib.DarlingStatusNotifierCreate.restype = ctypes.c_void_p
    lib.DarlingStatusNotifierDestroy.argtypes = [ctypes.c_void_p]
    lib.DarlingStatusNotifierBusName.argtypes = [ctypes.c_void_p]
    lib.DarlingStatusNotifierBusName.restype = ctypes.c_char_p
    lib.DarlingStatusNotifierSetMenu.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry), ctypes.c_uint32]
    lib.DarlingStatusNotifierPoll.argtypes = [ctypes.c_void_p, ctypes.POINTER(Event)]
    item = lib.DarlingStatusNotifierCreate(b'probe', b'Probe', b'')
    assert item
    try:
        entries = (Entry * 4)(Entry(11, 0, b'Riot Games', 3, 0),
                              Entry(12, 0, b'Sair', 3, 0),
                              Entry(13, 0, b'Ordinary', 3, 0),
                              Entry(14, 0, b'Disabled parent', 2, 0))
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        name = lib.DarlingStatusNotifierBusName(item).decode()
        event = Event()

        def click(id):
            subprocess.run(['gdbus', 'call', '--session', '--dest', name,
                            '--object-path', '/Menu', '--method', 'com.canonical.dbusmenu.Event',
                            '--', str(id), 'clicked', '<0>', '0'],
                           check=True, capture_output=True, timeout=8)

        def poll(expected=None):
            got = lib.DarlingStatusNotifierPoll(item, ctypes.byref(event))
            assert got == (expected is not None), (got, expected)
            if expected is not None:
                assert (event.kind, event.x, event.y, event.delta, event.horizontal) == (*expected, 0, 0, 0)
                assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 0

        poll()
        click(11)
        poll((8, 11))
        click(13)
        poll((5, 13))
        click(12)
        poll()
        deadline = time.monotonic() + 5
        while not Path(log).exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert Path(log).read_text() == 'quit\n'
        entries[0].flags = 2
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        click(11)
        poll()
        entries[0].flags = 3
        entries[0].parent = 14
        # Parent must precede child in a snapshot.
        nested = (Entry * 2)(entries[3], entries[0])
        assert lib.DarlingStatusNotifierSetMenu(item, nested, len(nested)) == 1
        click(11)
        poll()
        assert Path(log).read_text() == 'quit\n'
        ordinary = (Entry * 1)(Entry(13, 0, b'Ordinary', 3, 0))
        assert lib.DarlingStatusNotifierSetMenu(item, ordinary, 1) == 1
        click(1000002)  # The real producer's synthetic reopen entry.
        poll((8, 1000002))
        assert Path(log).read_text() == 'quit\n'
    finally:
        lib.DarlingStatusNotifierDestroy(item)
    print('REOPEN_TRANSPORT_PASS')


class ReopenTransportTest(unittest.TestCase):
    def test_private_bus(self):
        if not all(shutil.which(x) for x in ('cc', 'pkg-config', 'dbus-run-session', 'gdbus')):
            self.skipTest('native D-Bus test tools unavailable')
        if subprocess.run(['pkg-config', '--exists', 'gio-2.0']).returncode:
            self.skipTest('gio-2.0 development files unavailable')
        with tempfile.TemporaryDirectory(prefix='reopen-probe-') as tmp:
            spec = importlib.util.spec_from_file_location('reopen_build', ROOT / 'experimental/reopen-probe/build-transport.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            library = module.build(Path(tmp) / 'build')
            subprocess.run(['cc', '-std=c11', '-Werror', '-fsyntax-only', '-x', 'c', '-',
                            '-I' + str(library.parent)], input='''
#include "darling-status-notifier.h"
_Static_assert(DARLING_STATUS_MENU_CLICK == 5 && DARLING_STATUS_MENU_OPEN == 6 &&
               DARLING_STATUS_MENU_CLOSE == 7 && DARLING_STATUS_MENU_REOPEN == 8, "ABI");
''', text=True, check=True)
            helper = Path(tmp) / 'helper'
            helper.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$REOPEN_PROBE_LOG"\n')
            helper.chmod(0o755)
            log = Path(tmp) / 'actions.log'
            env = dict(os.environ, DARLING_STATUS_MENU_ACTION_SCRIPT=str(helper),
                       DARLING_STATUS_MENU_QUIT_LABEL='Sair', DARLING_STATUS_MENU_REOPEN_LABEL='Riot Games',
                       REOPEN_PROBE_LOG=str(log))
            result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__,
                                     '--probe', str(library), str(log)], env=env,
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('REOPEN_TRANSPORT_PASS', result.stdout)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--probe':
        probe(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
