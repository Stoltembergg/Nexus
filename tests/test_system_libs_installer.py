"""Offline check of tools/install-riot-system-libs.py; never touches a real prefix."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('system_libs', ROOT / 'tools/install-riot-system-libs.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def library(path, marker):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\xcf\xfa\xed\xfe' + marker)


class SystemLibsInstaller(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.prefix = self.base / 'prefix'
        self.guest = self.prefix / 'Users/check'
        self.backups = self.base / 'backups'
        for artifact, _ in installer.LIBRARIES:
            library(self.base / artifact, b'built ' + artifact.encode())
        self.entries = installer.plan(self.base, self.prefix, self.guest)

    def test_set_is_the_six_core_libraries_in_system_locations(self):
        self.assertEqual(installer.NAMES, ['libsystem_kernel.dylib', 'libsystem_malloc.dylib',
                                           'libsystem_pthread.dylib', 'libsystem_platform.dylib',
                                           'libobjc.A.dylib', 'libc++abi.dylib'])
        for _, system in installer.LIBRARIES:
            self.assertTrue(system.startswith('usr/lib/'))

    def test_single_copy_and_rollback(self):
        kernel = self.prefix / 'usr/lib/system/libsystem_kernel.dylib'
        library(kernel, b'old prefix kernel')
        old_kernel = installer.digest(kernel)
        overlays = self.guest / 'RuntimeLibraries'
        library(overlays / 'libsystem_kernel.dylib', b'diverged overlay kernel')
        library(overlays / 'libobjc.A.dylib', b'overlay objc')
        library(overlays / 'libsystem_c.dylib', b'unrelated overlay')
        for _ in range(2):
            result = installer.install(self.entries, self.backups)
        self.assertFalse(result['signed'])
        for artifact, destination, overlay in self.entries:
            self.assertEqual(installer.digest(destination), installer.digest(artifact))
            self.assertFalse(overlay.exists(), overlay)
        self.assertTrue((overlays / 'libsystem_c.dylib').is_file())
        installer.rollback(self.backups)
        self.assertEqual(installer.digest(kernel), old_kernel)
        self.assertTrue((overlays / 'libsystem_kernel.dylib').is_file())
        self.assertTrue((overlays / 'libobjc.A.dylib').is_file())
        self.assertFalse((self.prefix / 'usr/lib/system/libsystem_malloc.dylib').exists())

    def test_missing_or_non_macho_artifact_changes_nothing(self):
        overlay = self.guest / 'RuntimeLibraries/libsystem_malloc.dylib'
        library(overlay, b'overlay')
        (self.base / installer.LIBRARIES[-1][0]).write_bytes(b'not a library')
        with self.assertRaises(ValueError):
            installer.install(self.entries, self.backups)
        self.assertTrue(overlay.is_file())
        self.assertFalse((self.prefix / 'usr/lib/system/libsystem_kernel.dylib').exists())


if __name__ == '__main__':
    unittest.main()
