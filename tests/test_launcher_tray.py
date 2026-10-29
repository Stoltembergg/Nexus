"""Offline checks for the host-side launcher tray entry point."""
import ast
import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launcher_tray', ROOT / 'scripts/riot-launcher-tray.py')
tray = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tray)


class TraySourceTests(unittest.TestCase):
    def test_tray_menu_uses_launcher_and_scoped_actions(self):
        source = (ROOT / 'scripts/riot-launcher-tray.py').read_text()
        ast.parse(source)
        for text in ('Abrir launcher', 'Riot Games', 'Iniciar Riot Client', 'Sair', 'riot-launcher-gui.py',
                     "'reopen'", "'quit'", 'darling-launcher',
                     'scripts/riot-launcher.sh', "'start'", 'threading.Thread', 'GLib.idle_add',
                     'DarlingStatusNotifierCreate', 'DarlingStatusNotifierPoll',
                     'fcntl.flock'):
            self.assertIn(text, source)
        self.assertNotIn('AppIndicator3', source)
        gui = (ROOT / 'scripts/riot-launcher-gui.py').read_text()
        self.assertIn('riot-launcher-tray.py', gui)

    def test_start_client_reports_failures_but_not_success(self):
        source = (ROOT / 'scripts/riot-launcher-tray.py').read_text()
        tree = ast.parse(source)
        start = next(node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name == 'start_client')
        launch = next(node for node in ast.walk(start)
                      if isinstance(node, ast.FunctionDef) and node.name == 'launch')
        report = next(node for node in ast.walk(launch)
                      if isinstance(node, ast.FunctionDef) and node.name == 'report')
        idle_add = next(node for node in ast.walk(launch)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == 'GLib' and node.func.attr == 'idle_add')
        self.assertNotIn(idle_add, list(ast.walk(report)))
        self.assertEqual(idle_add.args[0].id, 'report')
        self.assertTrue(any(isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                            and node.test.id == 'success'
                            and any(isinstance(child, ast.Return) for child in node.body)
                            for node in ast.walk(report)))
        self.assertTrue(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr == 'MessageDialog'
                            and any(keyword.arg == 'message_type'
                                    for keyword in node.keywords)
                            and any(isinstance(child, ast.Attribute) and child.attr == 'ERROR'
                                    for child in ast.walk(node))
                            for node in ast.walk(report)))

    def test_explicit_prefix_wins_over_saved_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.json'
            config.write_text(json.dumps({'prefix': '/configured'}))
            env = {'DPREFIX': '/explicit'}
            self.assertEqual(tray.prefix_environment(env, config)['DPREFIX'], '/explicit')

    def test_missing_transport_is_built_and_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'missing.so'
            def build(command, **kwargs):
                self.assertIn('--output', command)
                target.write_bytes(b'library')
            with patch.object(tray.subprocess, 'run', side_effect=build):
                self.assertTrue(tray.ensure_library(target))
            target.unlink()
            with patch.object(tray.subprocess, 'run', side_effect=OSError('compiler missing')):
                self.assertFalse(tray.ensure_library(target))

    def test_lock_requires_private_owned_runtime_directory_and_does_not_truncate(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            lock = Path(tmp) / 'nexus-launcher-tray.lock'
            lock.write_text('preserve')
            os.chmod(lock, 0o600)
            fd = tray.acquire_instance_lock(tmp)
            self.assertEqual(lock.read_text(), 'preserve')
            import subprocess
            probe = subprocess.run([sys.executable, '-c',
                "import importlib.util,sys; s=importlib.util.spec_from_file_location('t',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m); "
                "fd=m.acquire_instance_lock(sys.argv[2]);sys.exit(0 if fd is None else 2)",
                str(ROOT / 'scripts/riot-launcher-tray.py'), tmp], capture_output=True)
            self.assertEqual(probe.returncode, 0, probe.stderr.decode())
            os.close(fd)
            link = Path(tmp) / 'nexus-launcher-tray.lock'
            link.unlink()
            target = Path(tmp) / 'target'
            target.write_text('untouched')
            link.symlink_to(target)
            with self.assertRaises(OSError):
                tray.acquire_instance_lock(tmp)
            self.assertEqual(target.read_text(), 'untouched')

    def test_lock_fails_closed_without_private_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o755)
            with self.assertRaisesRegex(RuntimeError, 'permissões privadas'):
                tray.acquire_instance_lock(tmp)
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR': ''}):
            with self.assertRaisesRegex(RuntimeError, 'ausente'):
                tray.acquire_instance_lock()

    def test_template_action_helper_is_never_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            helper = root / 'build/runtime/tools/riot-menu-action.py'
            helper.parent.mkdir(parents=True)
            helper.write_text("LOG_FILE = Path('@PROJECT_ROOT@')")
            (root / 'scripts').mkdir()
            (root / 'scripts/configure.py').write_text('# configured')
            with patch.object(tray, 'ROOT', root), patch.object(
                    tray.subprocess, 'run', return_value=type('Result', (), {'returncode': 0})()):
                with self.assertRaisesRegex(RuntimeError, 'template'):
                    tray.rendered_helper()


if __name__ == '__main__':
    unittest.main()
