"""Exercise the real tray on a private bus and a private X server only."""
import os
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def probe(directory, watcher):
    directory = Path(directory)
    panel = tray = None
    try:
        panel = subprocess.Popen([watcher], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 bufsize=0)
        assert select.select([panel.stdout], [], [], 10)[0], 'watcher did not start'
        assert panel.stdout.readline().decode().strip() == 'READY'
        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = str(directory / 'runtime')
        env['DPREFIX'] = str(directory / 'safe-prefix')
        env['TRAY_TEST_LOG'] = str(directory / 'actions.log')
        env['DARLING_STATUS_MENU_ACTION_SCRIPT'] = '/nonexistent/unsafe-action'
        tray = subprocess.Popen([sys.executable, str(directory / 'scripts/riot-launcher-tray.py')],
                                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert select.select([panel.stdout], [], [], 10)[0], 'tray did not register'
        registration = panel.stdout.readline().decode().strip()
        assert registration.startswith('REGISTER '), registration
        name = registration.split(' ', 1)[1]

        def call(path, method, *args):
            return subprocess.run(['gdbus', 'call', '--session', '--dest', name,
                                   '--object-path', path, '--method', method, '--', *args],
                                  check=True, capture_output=True, text=True, timeout=8).stdout

        # Registration can precede publication of the menu snapshot.
        deadline = time.monotonic() + 10
        while True:
            try:
                layout = call('/Menu', 'com.canonical.dbusmenu.GetLayout', '0', '-1', '[]')
            except subprocess.CalledProcessError as error:
                layout = error.stderr
            if all(label in layout for label in ('Abrir launcher', 'Riot Games', 'Sair')):
                break
            assert time.monotonic() < deadline, layout
            time.sleep(0.05)
        call('/Menu', 'com.canonical.dbusmenu.Event', '0', 'opened', '<0>', '0')
        for item, expected in ((1, 'launcher'), (2, 'reopen'), (3, 'quit')):
            call('/Menu', 'com.canonical.dbusmenu.Event', str(item), 'clicked', '<0>', '0')
            deadline = time.monotonic() + 10
            while True:
                log = directory / 'actions.log'
                lines = log.read_text().splitlines() if log.exists() else []
                if expected in lines:
                    break
                assert tray.poll() is None, 'tray exited unexpectedly'
                assert time.monotonic() < deadline, (expected, lines)
                time.sleep(0.05)
        assert lines == ['launcher', 'reopen', 'quit'], lines
        assert tray.poll() is None, 'quit stub must not terminate tray or session'
    finally:
        stop(tray)
        stop(panel)


class LauncherTrayIntegrationTest(unittest.TestCase):
    def test_private_session_menu_actions(self):
        required = ('Xvfb', 'dbus-run-session', 'gdbus', 'cc', 'pkg-config')
        missing = [name for name in required if not shutil.which(name)]
        if missing:
            self.skipTest('missing isolated display or D-Bus build tools: ' + ', '.join(missing))
        if subprocess.run(['pkg-config', '--exists', 'gio-2.0']).returncode:
            self.skipTest('gio-2.0 development files unavailable')
        candidates = [sys.executable, '/usr/bin/python3']
        python = next((p for p in candidates if Path(p).exists() and subprocess.run(
            [p, '-c', "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0), None)
        if not python:
            self.skipTest('Python GTK 3 introspection bindings unavailable')
        with tempfile.TemporaryDirectory(prefix='nexus-tray-test-') as tmp:
            root = Path(tmp)
            for path in ('scripts', 'build/runtime/tools', 'runtime'):
                (root / path).mkdir(parents=True)
            (root / 'runtime').chmod(0o700)
            shutil.copy2(ROOT / 'scripts/riot-launcher-tray.py', root / 'scripts')
            stub = ("import os, sys\nfrom pathlib import Path\n"
                    "with Path(os.environ['TRAY_TEST_LOG']).open('a') as f:\n"
                    "    f.write((sys.argv[1] if len(sys.argv) > 1 else 'launcher') + '\\n')\n")
            (root / 'scripts/riot-launcher-gui.py').write_text(stub)
            (root / 'build/runtime/tools/riot-menu-action.py').write_text(stub)
            subprocess.run([python, str(ROOT / 'tools/build-status-notifier.py'), '--output',
                            str(root / 'build/libdarling-status-notifier.so')], check=True)
            flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True))
            watcher = root / 'watcher'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'tests/fixtures/status-notifier-watcher.c'),
                            '-o', str(watcher), *flags], check=True)
            read_fd, write_fd = os.pipe()
            xvfb = None
            try:
                xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(write_fd), '-screen', '0',
                                         '800x600x24', '-nolisten', 'tcp'], pass_fds=(write_fd,),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                os.close(write_fd)
                write_fd = None
                assert select.select([read_fd], [], [], 10)[0], 'Xvfb did not start'
                display = os.read(read_fd, 64).decode().strip()
                assert display.isdigit(), 'Xvfb failed to allocate an isolated display'
                env = os.environ.copy()
                env['DISPLAY'] = ':' + display
                env.pop('DBUS_SESSION_BUS_ADDRESS', None)
                env.pop('WAYLAND_DISPLAY', None)
                subprocess.run(['dbus-run-session', '--', python, str(Path(__file__).resolve()),
                                '--probe', tmp, str(watcher)], env=env, check=True, timeout=60)
            finally:
                os.close(read_fd)
                if write_fd is not None:
                    os.close(write_fd)
                stop(xvfb)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--probe':
        probe(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
