"""Private-bus transport check for the owned empty-to-four snapshot."""
import ctypes
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_status_notifier import MenuEntry, load

ROOT = Path(__file__).resolve().parents[1]


def private_probe(library):
    lib = load(library)
    item = lib.DarlingStatusNotifierCreate(b'sequence-test', b'Neutral sequence probe', b'')
    assert item
    name = lib.DarlingStatusNotifierBusName(item).decode()
    monitor = subprocess.Popen(['gdbus', 'monitor', '--session', '--dest', name], stdout=subprocess.PIPE, bufsize=0)
    try:
        assert select.select([monitor.stdout], [], [], 8)[0]
        assert b'Monitoring signals' in monitor.stdout.readline()
        def call(path, method, *args):
            return subprocess.check_output(['gdbus', 'call', '--session', '--dest', name,
                '--object-path', path, '--method', method, '--', *args], text=True, timeout=8)
        def layout():
            return call('/Menu', 'com.canonical.dbusmenu.GetLayout', '0', '-1', '[]')
        assert 'uint32 0' in layout()
        entries = (MenuEntry * 4)(*(MenuEntry(i, 0, title, 3, 0) for i, title in enumerate(
            (b'Primeiro teste', b'Segundo teste', b'Terceiro teste', b''), 1)))
        assert lib.DarlingStatusNotifierSetMenu(item, entries, 4) == 1
        observed = b''
        while b'.LayoutUpdated ' not in observed or b'.NewMenu ' not in observed:
            assert select.select([monitor.stdout], [], [], 8)[0], observed
            observed += os.read(monitor.stdout.fileno(), 4096)
        assert b'(uint32 1, 0)' in observed, observed
        after = layout()
        assert 'uint32 1' in after and all(x in after for x in ('Primeiro teste', 'Segundo teste', 'Terceiro teste'))
        for i in range(1, 5):
            for prop in ('enabled', 'visible'):
                assert call('/Menu', 'com.canonical.dbusmenu.GetProperty', str(i), prop) == '(<true>,)\n'
        assert "<''>" in call('/Menu', 'com.canonical.dbusmenu.GetProperty', '4', 'label')
        assert lib.DarlingStatusNotifierSetMenu(item, entries, 4) == 1
        assert layout() == after
        print('SEQUENCE_PRIVATE_PASS layout_updated=1 new_menu=1 static=1')
    finally:
        lib.DarlingStatusNotifierDestroy(item)
        monitor.terminate()
        monitor.communicate(timeout=8)


class SequenceTests(unittest.TestCase):
    def test_private_bus_signals(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build', prefix='sequence-test-') as folder:
            library = Path(folder) / 'status.so'
            subprocess.run([sys.executable, str(ROOT / 'tools/build-status-notifier.py'), '--output', str(library)], check=True)
            run = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '--private', str(library)],
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('SEQUENCE_PRIVATE_PASS', run.stdout)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--private':
        private_probe(sys.argv[2])
    else:
        unittest.main()
