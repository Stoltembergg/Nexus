"""Offline contract checks only: no display, guest, prefix or input."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experimental/reopen-probe/window-probe.m'


class WindowProbeTest(unittest.TestCase):
    def test_owned_window_and_policy_contract(self):
        source = SOURCE.read_text()
        for fragment in ('[window orderOut:nil]', '[eligible orderFront:nil]',
                         '[app _reopen]', 'before == hidden && before == after',
                         '![ineligible isVisible]', 'delegate->calls == 2',
                         'return NO;', 'windowHandle'):
            self.assertIn(fragment, source)
        for prohibited in ('sendEvent:', 'mouseEventWithType:', 'performClose:', 'system('):
            self.assertNotIn(prohibited, source)


if __name__ == '__main__':
    unittest.main()
