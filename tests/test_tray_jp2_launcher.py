"""Offline tests: never start the real client or touch the user's desktop."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('tray_jp2', ROOT / 'scripts/tray-jp2-experiment.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ExperimentTests(unittest.TestCase):
    def stage(self, stage):
        for name in ('AppKit', 'Onyx2D'):
            binary = stage / (name + '.framework') / 'Versions/C' / name
            binary.parent.mkdir(parents=True)
            binary.write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
        for name in ('libopenjp2.dylib', 'libDarlingStatusNotifier.dylib'):
            (stage / name).write_bytes(bytes.fromhex('cffaedfe') + b'fixture')
        (stage / 'libdarling-status-notifier.so').write_bytes(b'\x7fELFfixture')
        (stage / 'libDarlingStatusNotifier.dylib').write_bytes(
            bytes.fromhex('cffaedfe') + os.fsencode(str(stage / 'libdarling-status-notifier.so')) + b'\0')

    def test_missing_stage_reports_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'NEXUS_TRAY_JP2_STAGE': tmp}):
            with self.assertRaisesRegex(ValueError, 'Estágio experimental ausente ou incompleto'):
                launcher.experiment_environment()

    def test_environment_preserves_configured_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            self.stage(stage)
            env = {'NEXUS_TRAY_JP2_STAGE': tmp, 'DPREFIX': '/tmp/prefix',
                   'RIOT_GUEST_HOME': '/tmp/prefix/Users/test', 'DYLD_LIBRARY_PATH': '/custom/lib'}
            with patch.dict(os.environ, env, clear=True), patch.object(launcher, 'configuration', return_value={'prefix': '/unused', 'guest_home': '/Users/test'}), patch.object(launcher, 'no_new_privs', return_value=False):
                result = launcher.experiment_environment()
            self.assertEqual(result['DYLD_FRAMEWORK_PATH'], '/Volumes/SystemRoot' + tmp + ':/Users/test/RuntimeFrameworks')
            self.assertTrue(result['DYLD_LIBRARY_PATH'].endswith(':/custom/lib'))
            self.assertEqual(result['RCLOL_CLEAN_ON_EXIT'], '0')
            self.assertNotIn('DARLING_STATUS_MENU_COUNT_TRACE', result)
            self.assertEqual(result['DPREFIX'], '/tmp/prefix')

    def test_stage_rejects_missing_host_and_invalid_framework(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            self.stage(stage)
            (stage / 'libdarling-status-notifier.so').unlink()
            (stage / 'AppKit.framework/Versions/C/AppKit').write_text('not a binary')
            with patch.dict(os.environ, {'NEXUS_TRAY_JP2_STAGE': tmp}):
                with self.assertRaises(ValueError) as error:
                    launcher.experiment_environment()
            self.assertIn('AppKit.framework', str(error.exception))
            self.assertIn('libdarling-status-notifier.so', str(error.exception))

    def test_stage_rejects_wrapper_bound_to_another_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            self.stage(stage)
            (stage / 'libDarlingStatusNotifier.dylib').write_bytes(bytes.fromhex('cffaedfe') + b'/other/library\0')
            with patch.dict(os.environ, {'NEXUS_TRAY_JP2_STAGE': tmp}):
                with self.assertRaisesRegex(ValueError, 'outro estágio'):
                    launcher.experiment_environment()

    def test_start_delegates_to_safe_start_and_propagates_failure(self):
        with patch.object(launcher.subprocess, 'run') as run:
            run.return_value.returncode = 1
            run.return_value.stdout = 'A session is already running; it was not interrupted.'
            result = launcher.start_experiment({'DPREFIX': '/prefix'})
        self.assertEqual(run.call_args.args[0], ['bash', str(ROOT / 'scripts/riot-launcher.sh'), 'start'])
        self.assertEqual(result.returncode, 1)
        self.assertIn('already running', result.stdout)

    def test_real_start_action_refuses_existing_prefix_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'scripts/riot-launcher.sh', root / 'scripts/riot-launcher.sh')
            shutil.copy(ROOT / 'scripts/riot-launcher-lock.py', root / 'scripts/riot-launcher-lock.py')
            shutil.copy(ROOT / 'scripts/riot_operation_lock.py', root / 'scripts/riot_operation_lock.py')
            (root / 'scripts/nix-stop.py').write_text('def prefix_server(prefix):\n    return 12345\n')
            runtime = root / 'runtime'
            runtime.mkdir(mode=0o700)
            result = subprocess.run(['bash', str(root / 'scripts/riot-launcher.sh'), 'start'],
                                    env=dict(os.environ, XDG_RUNTIME_DIR=str(runtime), DPREFIX=str(root / 'prefix')),
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('already running', result.stdout)
            self.assertEqual(result.stderr, '')
            self.assertEqual(len(list(runtime.glob('riot-launcher-*.lock'))), 1)
            self.assertFalse((root / 'build/riot-runtime.log').exists())

    def test_install_never_overwrites_foreign_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            foreign = directory / 'nexus-tray-jp2-experimental.desktop'
            foreign.write_text('foreign')
            (directory / 'nexus-tray-jp2-experimental-1.desktop').symlink_to(directory / 'missing')
            with patch.object(launcher, 'desktop_directory', return_value=directory), patch.object(launcher.subprocess, 'run'):
                result = launcher.install_shortcut()
            self.assertEqual(result.name, 'nexus-tray-jp2-experimental-2.desktop')
            self.assertEqual(foreign.read_text(), 'foreign')
            self.assertIn('tray-jp2-experiment.py', result.read_text())


if __name__ == '__main__':
    unittest.main()
