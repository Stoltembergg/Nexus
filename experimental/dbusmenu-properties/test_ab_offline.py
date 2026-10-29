import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('ab', Path(__file__).with_name('ab.py'))
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)


class OfflineTests(unittest.TestCase):
    def test_initial(self):
        self.assertEqual(ab.initial_name('SEQUENCE_INITIAL bus=:1.42 count=4\n'), ':1.42')
        self.assertIsNone(ab.initial_name('SEQUENCE_INITIAL bus=:1.42 count=3\n'))
        self.assertIsNone(ab.initial_name('SEQUENCE_INITIAL bus=:1.42 count=4\n' * 2))

    def test_watcher(self):
        self.assertTrue(ab.watcher_registered("(<[':1.42@/StatusNotifierItem', ':1.9@/Other']>,)", ':1.42'))
        self.assertFalse(ab.watcher_registered("(<[':1.420@/StatusNotifierItem', ':1.42/StatusNotifierItem']>,)", ':1.42'))
        self.assertFalse(ab.watcher_registered('(<@as []>,)', ':1.42'))
        with self.assertRaises(ValueError):
            ab.watcher_registered('invalid secret', ':1.42')

    def test_pixmap_alpha(self):
        self.assertTrue(ab.opaque_pixmap('(<[(1, 1, [0xff, 0x00, 0x00, 0x00])]>,)'))
        self.assertFalse(ab.opaque_pixmap('(<[(1, 1, [0x00, 0xff, 0xff, 0xff])]>,)'))
        self.assertFalse(ab.opaque_pixmap('(<[(2, 1, [0xff, 0x00, 0x00, 0x00])]>,)'))

    def test_checks_only_own_item(self):
        calls = []
        def call(dest, path, interface, prop):
            calls.append((dest, prop))
            return {'RegisteredStatusNotifierItems': "(<[':1.42@/StatusNotifierItem']>,)",
                    'Status': "(<'Active'>,)",
                    'IconPixmap': '(<[(1, 1, [0xff, 0x00, 0x00, 0x00])]>,)'}[prop]
        self.assertTrue(all(ab.desktop_checks(':1.42', call).values()))
        self.assertEqual(calls[1:], [(':1.42', 'Status'), (':1.42', 'IconPixmap')])
        calls.clear()
        self.assertFalse(any(ab.desktop_checks(':1.43', call).values()))
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
