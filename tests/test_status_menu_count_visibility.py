import re
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from status_count_patches import patched_appkit

# The visibility diagnostic on its own: the count diagnostic plus the
# visibility counters, before the title refinement adds its own fields.
VISIBILITY_CHAIN = (
    'cocotron-status-notifier.patch',
    'cocotron-status-menu-count.patch',
    'cocotron-status-menu-count-visibility.patch',
)


class VisibilityDiagnosticTest(unittest.TestCase):
    def test_patch_schema_and_existing_flags(self):
        source = patched_appkit(VISIBILITY_CHAIN)
        records = re.findall(r'"(SMCOUNT [^"\\]*(?:\\.[^"\\]*)*)"', source)
        self.assertIn(r'SMCOUNT aggregate depth=%u processed=%u visible=%u hidden=%u enabled=%u disabled=%u submenus=%u complete=%d\n', records)
        self.assertIn('if (flags & 1) enabled++; else disabled++;', source)
        self.assertIn('if (flags & 2) visible++; else hidden++;', source)
        self.assertEqual(source.count('BOOL hasSubmenu = [item hasSubmenu];'), 1)


if __name__ == '__main__':
    unittest.main()
