"""Offline cleanup tests: no Darling, desktop, or guest processes are launched."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('probe_prefix', ROOT / 'tools/probe_prefix.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProbeCleanupTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='probe-unit-'))
        self.owner = module.ProbePrefix(self.root, 'owned-')
        self.owner.started = 100
        self.owner.prefix.mkdir()
        (self.owner.prefix / '.init.pid').write_text('123')
        self.proc = self.root / 'proc' / '123'
        self.proc.mkdir(parents=True)
        (self.proc / 'stat').write_text('123 (darlingserver) S ' + '0 ' * 18 + '101 0')
        (self.proc / 'comm').write_text('darlingserver\n')
        (self.proc / 'cmdline').write_bytes(b'darlingserver\0' + os.fsencode(self.owner.prefix) + b'\0')
        (self.proc / 'environ').write_bytes(b'DPREFIX=' + os.fsencode(self.owner.prefix) + b'\0')

    def run_cleanup(self, **kwargs):
        real_path = Path
        with patch.object(module, 'Path', side_effect=lambda value: self.root / 'proc' if value == '/proc' else real_path(value)), \
             patch.object(module.subprocess, 'run', **kwargs) as run:
            result = self.owner.cleanup('/mock/darling')
        return result, run

    def test_success_uses_exact_owned_prefix(self):
        result, run = self.run_cleanup()
        self.assertTrue(result)
        self.assertEqual(run.call_args.args[0], ['/mock/darling', 'shutdown'])
        self.assertEqual(run.call_args.kwargs['env']['DPREFIX'], str(self.owner.prefix))

    def test_preexisting_and_wrong_identity_are_never_stopped(self):
        for data in (b'DPREFIX=/other\0', b'DPREFIX=/other\0DPREFIX=' + os.fsencode(self.owner.prefix) + b'\0'):
            (self.proc / 'environ').write_bytes(data)
            result, run = self.run_cleanup()
            self.assertFalse(result)
            run.assert_not_called()
        (self.proc / 'environ').write_bytes(b'DPREFIX=' + os.fsencode(self.owner.prefix) + b'\0')
        self.owner.started = 102
        result, run = self.run_cleanup()
        self.assertFalse(result)
        run.assert_not_called()

    def test_missing_environment_prefix_is_verified_by_exact_command(self):
        (self.proc / 'environ').write_bytes(b'')
        result, run = self.run_cleanup()
        self.assertTrue(result)
        run.assert_called_once()
        (self.proc / 'cmdline').write_bytes(b'darlingserver\0/other\0')
        result, run = self.run_cleanup()
        self.assertFalse(result)
        run.assert_not_called()

    def test_failure_and_timeout_fail_closed(self):
        for error in (subprocess.CalledProcessError(1, 'darling'), subprocess.TimeoutExpired('darling', 15)):
            result, run = self.run_cleanup(side_effect=error)
            self.assertFalse(result)
            self.assertEqual(run.call_count, 1)

    def test_symlink_pid_file_rejected(self):
        pidfile = self.owner.prefix / '.init.pid'
        pidfile.unlink()
        pidfile.symlink_to(self.proc / 'comm')
        result, run = self.run_cleanup()
        self.assertFalse(result)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
