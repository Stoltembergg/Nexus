"""Preparation checks only; no Darling process or session is started."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reopen_prepare', ROOT / 'experimental/reopen-probe/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
appkit_spec = importlib.util.spec_from_file_location('reopen_appkit', ROOT / 'experimental/reopen-probe/build-appkit.py')
appkit = importlib.util.module_from_spec(appkit_spec)
appkit_spec.loader.exec_module(appkit)


class IsolationTest(unittest.TestCase):
    def test_overlap_rejected_before_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'real').mkdir()
            (base / 'alias').symlink_to(base / 'real', target_is_directory=True)
            sentinel = base / 'real' / 'sentinel'
            sentinel.write_text('untouched')
            for module, invoke, protected in (
                (prepare, lambda out, tree: prepare.prepare(out, tree), 'source'),
                (appkit, lambda out, tree: appkit.build(out, tree), 'framework'),
            ):
                for target in ('root', protected):
                    for output, tree in (
                        (base / 'real' / 'new', base / 'real' / 'new' / 'nested'),
                        (base / 'alias' / 'new', base / 'real' / 'new' / 'nested'),
                        (base / 'real' / 'new' / 'nested', base / 'alias' / 'new'),
                        (base / 'alias' / 'new', base / 'real' / 'new'),
                    ):
                        with self.subTest(module=module.__name__, target=target, output=output, tree=tree):
                            root = tree if target == 'root' else base / 'other-root'
                            argument = tree if target == protected else base / 'other-input'
                            with mock.patch.object(module, 'ROOT', root), \
                                 mock.patch.object(module.subprocess, 'run') as run, \
                                 mock.patch.object(module.subprocess, 'check_output') as check:
                                with self.assertRaisesRegex(ValueError, 'disjoint'):
                                    invoke(output, argument)
                                run.assert_not_called()
                                check.assert_not_called()
                            self.assertFalse(output.exists())
                            self.assertEqual(sentinel.read_text(), 'untouched')

    def test_disjoint_output_passes_overlap_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output = base / 'output'
            with mock.patch.object(prepare, 'ROOT', base / 'root'), \
                 mock.patch.object(prepare.shutil, 'which', return_value=None):
                with self.assertRaisesRegex(ValueError, 'missing prerequisite'):
                    prepare.prepare(output, base / 'source')
            with mock.patch.object(appkit, 'ROOT', base / 'root'):
                with self.assertRaisesRegex(ValueError, 'expected framework'):
                    appkit.build(output, base / 'framework')
            self.assertFalse(output.exists())

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
