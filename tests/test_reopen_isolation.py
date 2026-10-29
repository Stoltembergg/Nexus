"""Preparation checks only; no Darling process or session is started."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reopen_prepare', ROOT / 'experimental/reopen-probe/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
appkit_spec = importlib.util.spec_from_file_location('reopen_appkit', ROOT / 'experimental/reopen-probe/build-appkit.py')
appkit = importlib.util.module_from_spec(appkit_spec)
appkit_spec.loader.exec_module(appkit)


class IsolationTest(unittest.TestCase):
    def test_appkit_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp) / 'sentinel'
            sentinel.write_text('untouched')
            with self.assertRaises(ValueError):
                appkit.build(tmp, '/nonexistent/framework')
            self.assertEqual(sentinel.read_text(), 'untouched')

    def test_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp) / 'sentinel'
            sentinel.write_text('untouched')
            with self.assertRaises(ValueError):
                prepare.prepare(tmp, prepare.DEFAULT_SOURCE)
            self.assertEqual(sentinel.read_text(), 'untouched')

    def test_clean_archive_and_patches(self):
        source = prepare.DEFAULT_SOURCE
        if not (source / '.git').exists() or not all(shutil.which(x) for x in ('git', 'patch', 'tar')):
            self.skipTest('Cocotron git source or patch tools unavailable')
        before = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'isolated'
            manifest = prepare.prepare(output, source)
            text = (output / 'AppKit/NSStatusItem.m').read_text()
            self.assertIn('DarlingStatusMenuReopen = 8', text)
            self.assertIn('[NSApp _reopen]', text)
            self.assertEqual(manifest, json.loads((output / 'manifest.json').read_text()))
            self.assertFalse(manifest['appkit_built'])
            self.assertFalse(manifest['guest_executed'])
        after = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
