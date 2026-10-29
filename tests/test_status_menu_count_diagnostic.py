import re
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from status_count_patches import patched_appkit

# The count diagnostic on its own, before the visibility and title refinements.
COUNT_CHAIN = (
    'cocotron-status-notifier.patch',
    'cocotron-status-menu-count.patch',
)


class CountDiagnosticTest(unittest.TestCase):
    def test_patch_and_private_record_schema(self):
        source = patched_appkit(COUNT_CHAIN)
        self.assertLess(source.index('[menu update]'), source.index('SMCOUNT update'))
        self.assertLess(source.index('SMCOUNT build'), source.index('SMCOUNT send kind=snapshot'))
        self.assertEqual(source.count('strcmp(countTrace, "1") == 0'), 2)
        records = re.findall(r'"(SMCOUNT [^"\\]*(?:\\.[^"\\]*)*)"', source)
        self.assertEqual(set(records), {
            r'SMCOUNT update depth=%u items=%lu\n',
            r'SMCOUNT build valid=%d entries=%u\n',
            r'SMCOUNT send kind=snapshot entries=%u accepted=%d\n',
            r'SMCOUNT send kind=clear entries=0 accepted=%d\n',
            r'SMCOUNT send kind=skipped reason=removed\n',
        })
        self.assertIn('BOOL sent = _darlingStatus.set_menu(_nativeItem, entries, count)', source)
        self.assertIn('BOOL sent = _darlingStatus.set_menu(_nativeItem, NULL, 0)', source)

    def test_refinements_extend_the_same_records(self):
        source = patched_appkit()
        records = set(re.findall(r'"(SMCOUNT [^"\\]*(?:\\.[^"\\]*)*)"', source))
        self.assertIn(
            r'SMCOUNT aggregate depth=%u processed=%u visible=%u hidden=%u enabled=%u disabled=%u submenus=%u empty=%u nonempty=%u separators=%u complete=%d\n',
            records)


if __name__ == '__main__':
    unittest.main()
