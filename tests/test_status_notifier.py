"""Build and exercise the real native SNI transport on a PRIVATE session bus."""
import ctypes
import os
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


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
    for name in ('SetTitle', 'SetToolTip', 'SetIconName'):
        getattr(lib, 'DarlingStatusNotifier' + name).argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.DarlingStatusNotifierBusName.argtypes = [ctypes.c_void_p]
    lib.DarlingStatusNotifierBusName.restype = ctypes.c_char_p
    lib.DarlingStatusNotifierPoll.argtypes = [ctypes.c_void_p, ctypes.POINTER(Event)]
    lib.DarlingStatusNotifierSetIcon.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                                ctypes.c_uint32, ctypes.c_void_p]
    lib.DarlingStatusNotifierSetMenu.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(MenuEntry), ctypes.c_uint32]
    return lib


def probe(library, watcher):
    """This function only runs below dbus-run-session, never on the real panel."""
    lib = load(library)
    assert not lib.DarlingStatusNotifierCreate(None, b'Test', b'')
    assert not lib.DarlingStatusNotifierCreate(b'', b'Test', b'')
    assert not lib.DarlingStatusNotifierCreate(b'test', b'\xff', b'')
    item = lib.DarlingStatusNotifierCreate(b'darling-test', b'Teste de bandeja', b'applications-games')
    assert item
    item2 = None
    panel = None
    name = lib.DarlingStatusNotifierBusName(item).decode()

    def call(method, *args, destination=name, check=True, path='/StatusNotifierItem'):
        return subprocess.run(['gdbus', 'call', '--session', '--dest', destination,
                               '--object-path', path, '--method', method,
                               '--', *args], text=True, capture_output=True, check=check, timeout=8)

    def prop(key):
        return call('org.freedesktop.DBus.Properties.Get',
                    'org.kde.StatusNotifierItem', key).stdout

    def panel_line(process):
        assert select.select([process.stdout], [], [], 8)[0], 'fake panel timed out'
        line = process.stdout.readline().decode().strip()
        assert line, 'fake panel exited'
        return line

    def start_panel():
        process = subprocess.Popen([watcher], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, bufsize=0)
        try:
            lines = [panel_line(process), panel_line(process)]
            assert 'READY' in lines, lines
            assert 'REGISTER ' + name in lines, lines
        except BaseException:
            process.terminate()
            process.communicate(timeout=8)
            raise
        return process

    try:
        assert 'ApplicationStatus' in prop('Category')
        assert 'darling-test' in prop('Id')
        assert 'Active' in prop('Status')
        assert 'Teste de bandeja' in prop('Title')
        assert 'false' in prop('ItemIsMenu')
        assert 'objectpath' in prop('Menu')
        lib.DarlingStatusNotifierSetTitle(item, 'Título atualizado'.encode())
        assert 'Título atualizado' in prop('Title')
        lib.DarlingStatusNotifierSetToolTip(item, 'Dica da bandeja'.encode())
        assert 'Dica da bandeja' in prop('ToolTip')
        lib.DarlingStatusNotifierSetIconName(item, b'dialog-information')
        assert 'dialog-information' in prop('IconName')
        pixels = (ctypes.c_ubyte * 4)(255, 10, 20, 30)
        assert lib.DarlingStatusNotifierSetIcon(item, 1, 1, pixels) == 1
        assert '(1, 1,' in prop('IconPixmap')
        assert lib.DarlingStatusNotifierSetIcon(item, 257, 1, pixels) == 0
        assert lib.DarlingStatusNotifierSetIcon(item, 1, 0, pixels) == 0
        assert lib.DarlingStatusNotifierSetIcon(item, 1, 1, None) == 0
        assert lib.DarlingStatusNotifierSetIcon(item, 0, 0, None) == 1
        assert '@a(iiay) []' in prop('IconPixmap')
        event = Event()
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 0
        for method, kind in [('Activate', 1), ('SecondaryActivate', 2), ('ContextMenu', 3)]:
            call('org.kde.StatusNotifierItem.' + method, '12', '-20')
            assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
            assert (event.kind, event.x, event.y) == (kind, 12, -20)
        call('org.kde.StatusNotifierItem.Scroll', '-120', 'horizontal')
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
        assert (event.kind, event.delta, event.horizontal) == (4, -120, 1)
        assert call('org.kde.StatusNotifierItem.Scroll', '1', 'invalid', check=False).returncode != 0
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 0
        # Real DBusMenu protocol, exercised both directly and through the ELF
        # wrapper. No real desktop host or application action is involved.
        def menu_call(method, *args, check=True):
            return call('com.canonical.dbusmenu.' + method, *args,
                        path='/Menu', check=check)

        # A new item has no menu; an explicit empty snapshot remains valid.
        assert "objectpath '/'" in prop('Menu')
        assert lib.DarlingStatusNotifierSetMenu(item, None, 0) == 1
        assert "objectpath '/'" in prop('Menu')

        entries = (MenuEntry * 6)(
            MenuEntry(10, 0, b'_Open', 3, 0),
            MenuEntry(20, 0, b'Options', 3, 0),
            MenuEntry(21, 20, b'Checked', 3 | 8, 1),
            MenuEntry(22, 20, b'Disabled', 2, 0),
            MenuEntry(30, 0, b'', 3 | 4, 0),
            MenuEntry(40, 0, b'Hidden', 1, 0),
        )
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        assert '/Menu' in prop('Menu')
        tree = menu_call('GetLayout', '0', '-1', '[]').stdout
        assert '_Open' in tree and 'Checked' in tree and 'separator' in tree, tree
        assert 'checkmark' in tree and "'toggle-state': <1>" in tree, tree
        root_only = menu_call('GetLayout', '0', '0', "['label']").stdout
        assert '_Open' not in root_only, root_only
        shallow = menu_call('GetLayout', '0', '1', "['label']").stdout
        assert '_Open' in shallow and 'Checked' not in shallow, shallow
        assert 'false' in menu_call('GetProperty', '22', 'enabled').stdout
        assert 'false' in menu_call('GetProperty', '40', 'visible').stdout
        group = menu_call('GetGroupProperties', '[10, 21, 999]', "['label']").stdout
        assert '_Open' in group and 'Checked' in group and '999' not in group, group
        all_properties = menu_call('GetGroupProperties', '[]', "['label']").stdout
        assert 'Hidden' in all_properties and 'Checked' in all_properties, all_properties
        for method, args in [('GetLayout', ('999', '-1', '[]')),
                             ('GetLayout', ('0', '-2', '[]')),
                             ('GetProperty', ('999', 'label')),
                             ('GetProperty', ('10', 'unknown'))]:
            assert menu_call(method, *args, check=False).returncode != 0

        menu_call('Event', '21', 'clicked', '<0>', '0')
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
        assert (event.kind, event.x) == (5, 21)
        for blocked in (20, 22, 30, 40):
            menu_call('Event', str(blocked), 'clicked', '<0>', '0')
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 0
        assert menu_call('Event', '999', 'clicked', '<0>', '0', check=False).returncode != 0
        grouped = menu_call('EventGroup', "[(10, 'clicked', <0>, uint32 0), (999, 'clicked', <0>, 0)]").stdout
        assert '999' in grouped, grouped
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
        assert (event.kind, event.x) == (5, 10)
        assert 'false' in menu_call('AboutToShow', '20').stdout
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
        assert (event.kind, event.x) == (6, 20)
        assert '999' in menu_call('AboutToShowGroup', '[0, 999]').stdout
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
        assert (event.kind, event.x) == (6, 0)
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 0
        for method, kind in [('opened', 6), ('closed', 7)]:
            menu_call('Event', '0', method, '<0>', '0')
            assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
            assert (event.kind, event.x) == (kind, 0)
            assert menu_call('Event', '10', method, '<0>', '0', check=False).returncode != 0
            assert menu_call('Event', '999', method, '<0>', '0', check=False).returncode != 0

        # Rejected snapshots do not replace the current layout or revision.
        previous = menu_call('GetLayout', '0', '-1', '[]').stdout
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        assert menu_call('GetLayout', '0', '-1', '[]').stdout == previous
        invalid = [MenuEntry(0, 0, b'bad', 3, 0), MenuEntry(10, 999, b'bad', 3, 0),
                   MenuEntry(10, 10, b'cycle', 3, 0), MenuEntry(10, 0, b'\xff', 3, 0),
                   MenuEntry(10, 0, b'bad flags', 32, 0), MenuEntry(10, 0, b'bad state', 3, 2)]
        for bad in invalid:
            assert lib.DarlingStatusNotifierSetMenu(item, ctypes.byref(bad), 1) == 0
            assert menu_call('GetLayout', '0', '-1', '[]').stdout == previous
        duplicate = (MenuEntry * 2)(MenuEntry(1, 0, b'A', 3, 0), MenuEntry(1, 0, b'B', 3, 0))
        assert lib.DarlingStatusNotifierSetMenu(item, duplicate, 2) == 0
        assert menu_call('GetLayout', '0', '-1', '[]').stdout == previous
        deep = (MenuEntry * 33)(*(MenuEntry(i, i - 1, b'Deep', 3, 0) for i in range(1, 34)))
        assert lib.DarlingStatusNotifierSetMenu(item, deep, 33) == 0
        assert menu_call('GetLayout', '0', '-1', '[]').stdout == previous
        assert lib.DarlingStatusNotifierSetMenu(item, entries, 1025) == 0
        assert menu_call('GetLayout', '0', '-1', '[]').stdout == previous
        entries[1].flags = 2 # Disabled parent must suppress child activation too.
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        menu_call('Event', '21', 'clicked', '<0>', '0')
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 0
        entries[1].flags = 3
        entries[0].label = b'Updated'
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        entries[0].label = b'Caller changed its memory'
        assert 'Updated' in menu_call('GetProperty', '10', 'label').stdout
        assert lib.DarlingStatusNotifierSetMenu(item, None, 0) == 1
        assert "objectpath '/'" in prop('Menu')
        assert menu_call('Event', '10', 'clicked', '<0>', '0', check=False).returncode != 0
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        assert "objectpath '/Menu'" in prop('Menu')
        assert 'Caller changed its memory' in menu_call('GetLayout', '0', '-1', '[]').stdout
        assert lib.DarlingStatusNotifierSetMenu(item, None, 0) == 1
        # The transport accepts events without a host, then re-registers when
        # one appears and again when it restarts. No application restart needed.
        panel = start_panel()
        panel.terminate()
        panel.communicate(timeout=8)
        panel = start_panel()
        # Separate item connections cannot destroy one another's registration.
        assert lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)) == 1
        assert panel_line(panel) == 'NEW_MENU ' + name
        assert lib.DarlingStatusNotifierSetMenu(item, None, 0) == 1
        assert panel_line(panel) == 'NEW_MENU ' + name
        item2 = lib.DarlingStatusNotifierCreate(b'second', b'Second', b'')
        assert item2
        name2 = lib.DarlingStatusNotifierBusName(item2).decode()
        assert name != name2
        lib.DarlingStatusNotifierDestroy(item2)
        item2 = None
        assert 'Título atualizado' in prop('Title')
        # A peer cannot make an unbounded allocation queue by flooding clicks.
        for i in range(140):
            call('org.kde.StatusNotifierItem.Activate', str(i), '0')
        events = []
        while lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)):
            events.append(event.x)
        assert events == list(range(12, 140)), events
    finally:
        if item2:
            lib.DarlingStatusNotifierDestroy(item2)
        lib.DarlingStatusNotifierDestroy(item)
        if panel:
            panel.terminate()
            panel.communicate(timeout=8)
    assert call('org.freedesktop.DBus.Properties.Get', 'org.kde.StatusNotifierItem',
                'Title', check=False).returncode != 0
    print('SNI_PASS properties icons activation bounded_queue independent_items watcher_restart removal')


def menu_race_probe(library):
    """Owned item and monitor on a private bus; simulate the snapshot owner."""
    lib = load(library)
    item = lib.DarlingStatusNotifierCreate(b'race-test', b'Race test', b'')
    assert item
    name = lib.DarlingStatusNotifierBusName(item).decode()
    monitor = subprocess.Popen(['gdbus', 'monitor', '--session', '--dest', name],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)

    def call(path, method, *args):
        return subprocess.run(['gdbus', 'call', '--session', '--dest', name,
                               '--object-path', path, '--method', method, '--', *args],
                              text=True, capture_output=True, check=True, timeout=8).stdout

    def menu(method, *args):
        return call('/Menu', 'com.canonical.dbusmenu.' + method, *args)

    def menu_path():
        return call('/StatusNotifierItem', 'org.freedesktop.DBus.Properties.Get',
                    'org.kde.StatusNotifierItem', 'Menu')

    try:
        assert select.select([monitor.stdout], [], [], 8)[0], 'monitor timed out'
        assert b'Monitoring signals' in monitor.stdout.readline()
        assert "objectpath '/'" in menu_path()
        before = menu('GetLayout', '0', '-1', '[]')
        assert "uint32 0" in before, before
        assert menu('GetProperty', '0', 'visible') == '(<true>,)\n'
        assert menu('GetProperty', '0', 'enabled') == '(<true>,)\n'
        entries = (MenuEntry * 4)(
            MenuEntry(1, 0, b'Play', 3, 0), MenuEntry(2, 0, b'Settings', 3, 0),
            MenuEntry(3, 0, b'Disabled', 2, 0), MenuEntry(4, 0, b'Hidden', 1, 0))
        assert lib.DarlingStatusNotifierSetMenu(item, entries, 4) == 1
        assert "objectpath '/Menu'" in menu_path()
        layout = menu('GetLayout', '0', '-1', '[]')
        assert 'uint32 1' in layout and all(label in layout for label in
                                            ('Play', 'Settings', 'Disabled', 'Hidden')), layout
        assert menu('GetProperty', '3', 'enabled') == '(<false>,)\n'
        assert menu('GetProperty', '4', 'visible') == '(<false>,)\n'
        event = Event()
        for id in (3, 4):
            menu('Event', str(id), 'clicked', '<0>', '0')
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 0

        # A panel gets false immediately; only the owner can subsequently poll
        # the queued open and publish a new snapshot, triggering LayoutUpdated.
        assert menu('AboutToShow', '0') == '(false,)\n'
        assert menu('GetLayout', '0', '-1', '[]') == layout
        assert lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)) == 1
        assert (event.kind, event.x) == (6, 0)
        entries[0].label = b'Play updated'
        assert lib.DarlingStatusNotifierSetMenu(item, entries, 4) == 1
        changed = menu('GetLayout', '0', '-1', '[]')
        assert 'uint32 2' in changed and 'Play updated' in changed, changed
        assert "objectpath '/Menu'" in menu_path()
        assert lib.DarlingStatusNotifierSetMenu(item, entries, 4) == 1
        assert menu('GetLayout', '0', '-1', '[]') == changed
        assert lib.DarlingStatusNotifierSetMenu(item, None, 0) == 1
        assert "objectpath '/'" in menu_path()
        assert 'uint32 3' in menu('GetLayout', '0', '-1', '[]')
        # Wait for the final signal rather than racing monitor termination.
        observed = b''
        while observed.count(b'.LayoutUpdated ') < 3 or observed.count(b'.NewMenu ') < 2:
            assert select.select([monitor.stdout], [], [], 8)[0], observed
            chunk = os.read(monitor.stdout.fileno(), 4096)
            assert chunk, observed
            observed += chunk
    finally:
        lib.DarlingStatusNotifierDestroy(item)
        monitor.terminate()
        output, errors = monitor.communicate(timeout=8)
    signals = (observed + output).decode()
    layouts = [line for line in signals.splitlines() if '.LayoutUpdated ' in line]
    new_menus = [line for line in signals.splitlines() if '.NewMenu ' in line]
    assert len(layouts) == 3, (signals, errors)
    for revision, line in enumerate(layouts, 1):
        assert f'(uint32 {revision}, 0)' in line, line
    assert len(new_menus) == 2, signals
    print('MENU_RACE_PASS', layouts, new_menus)


class StatusNotifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(shutil.which(name) for name in ('cc', 'pkg-config', 'dbus-run-session', 'gdbus')):
            raise unittest.SkipTest('native D-Bus test tools are not installed')
        check = subprocess.run(['pkg-config', '--exists', 'gio-2.0'])
        if check.returncode:
            raise unittest.SkipTest('gio-2.0 development files are not installed')
        cls.directory = tempfile.TemporaryDirectory(prefix='darling-status-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.library = Path(cls.directory.name) / 'status.so'
        cls.watcher = Path(cls.directory.name) / 'watcher'
        # Guard the public ABI independently of the numeric protocol assertions.
        subprocess.run(['cc', '-std=c11', '-Werror', '-fsyntax-only', '-x', 'c', '-',
                        '-I' + str(ROOT / 'tools')], input='''
#include "darling-status-notifier.h"
_Static_assert(DARLING_STATUS_MENU_OPEN == 6, "MENU_OPEN ABI changed");
_Static_assert(DARLING_STATUS_MENU_CLOSE == 7, "MENU_CLOSE ABI changed");
''', text=True, check=True)
        subprocess.run([sys.executable, str(ROOT / 'tools/build-status-notifier.py'),
                        '--output', str(cls.library)], check=True, capture_output=True, text=True)
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True))
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'tests/fixtures/status-notifier-watcher.c'),
                        '-o', str(cls.watcher), *flags], check=True)
        # Use only the public loader prefix of elfcalls. This test needs no
        # Darling checkout; production builds use the real elfcalls.h.
        directory = Path(cls.directory.name)
        (directory / 'elfcalls.h').write_text('''
#include <stddef.h>
struct elf_calls {
    void *(*dlopen)(const char *);
    int (*dlclose)(void *);
    void *(*dlsym)(void *, const char *);
    char *(*dlerror)(void);
};
''')
        bridge = directory / 'loader.c'
        bridge.write_text('''
#include <dlfcn.h>
#include "elfcalls.h"
static void *open_library(const char *path) { return dlopen(path, RTLD_NOW | RTLD_LOCAL); }
static struct elf_calls calls = {open_library, dlclose, dlsym, dlerror};
struct elf_calls *_elfcalls = &calls;
''')
        incomplete = directory / 'incomplete.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-x', 'c', '-', '-o', str(incomplete)],
                       input='void *DarlingStatusNotifierCreate(void) { return 0; }',
                       text=True, check=True)
        cls.wrappers = {}
        for name, host in [('real', cls.library), ('missing', directory / 'missing.so'),
                           ('incomplete', incomplete)]:
            output = directory / (name + '-wrapper.so')
            subprocess.run([
                'cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                '-Wl,-Bsymbolic', '-I' + str(directory),
                '-DDARLING_STATUS_HOST_LIBRARY="' + str(host) + '"',
                str(ROOT / 'tools/status-notifier-native-wrapper.c'), str(bridge),
                '-ldl', '-o', str(output),
            ], check=True)
            cls.wrappers[name] = output

    def test_private_bus_protocol_and_lifecycle(self):
        result = subprocess.run(['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
                                 '--bus-probe', str(self.library), str(self.watcher)],
                                text=True, capture_output=True, timeout=75)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('SNI_PASS', result.stdout)

    def test_private_bus_menu_snapshot_race(self):
        result = subprocess.run(['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
                                 '--menu-race-probe', str(self.library)],
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('MENU_RACE_PASS', result.stdout)

    def test_unavailable_bus_does_not_abort(self):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                 '--missing-bus', str(self.library)], text=True,
                                capture_output=True, timeout=10,
                                env=dict(os.environ, DBUS_SESSION_BUS_ADDRESS='unix:path=/nonexistent/darling-test'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_wrapper_forwards_protocol_and_lifecycle(self):
        result = subprocess.run([
            'dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
            '--bus-probe', str(self.wrappers['real']), str(self.watcher),
        ], text=True, capture_output=True, timeout=75)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('SNI_PASS', result.stdout)

    def test_wrapper_missing_or_incompatible_host_is_nonfatal(self):
        for name in ('missing', 'incomplete'):
            with self.subTest(name=name):
                lib = load(self.wrappers[name])
                self.assertFalse(lib.DarlingStatusNotifierCreate(b'test', b'Test', b''))
                self.assertFalse(lib.DarlingStatusNotifierCreate(b'test', b'Test', b''))
                lib.DarlingStatusNotifierDestroy(None)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--bus-probe':
        probe(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1 and sys.argv[1] == '--menu-race-probe':
        menu_race_probe(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == '--missing-bus':
        lib = load(sys.argv[2])
        assert not lib.DarlingStatusNotifierCreate(b'test', b'Test', b'')
    else:
        unittest.main()
