"""Static guest-patch checks against a clean git-derived AppKit tree; no guest."""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_count_patches import APPKIT_SOURCE, CHAIN, apply_chain

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'experimental/reopen-probe/cocotron-reopen.patch'


class ReopenGuestPatchTest(unittest.TestCase):
    def test_chains_and_event_abi(self):
        if not (APPKIT_SOURCE / 'NSStatusItem.m').is_file():
            self.skipTest('prepared upstream AppKit source unavailable')
        if not shutil.which('cc') or not shutil.which('patch'):
            self.skipTest('cc or patch unavailable')
        with tempfile.TemporaryDirectory(prefix='reopen-guest-') as tmp:
            work = Path(tmp)
            # Archive committed upstream files, never the possibly patched checkout.
            archive = subprocess.run(['git', '-C', str(APPKIT_SOURCE.parent), 'archive',
                                      'HEAD', 'AppKit'], capture_output=True, check=True)
            subprocess.run(['tar', '-xf', '-'], cwd=work, input=archive.stdout, check=True)
            # Exercise both supported layering points independently.
            pristine = work / 'AppKit'
            for chain in (CHAIN[:1], CHAIN):
                target = work / ('base' if len(chain) == 1 else 'counts')
                target.mkdir()
                shutil.copytree(pristine, target / 'AppKit')
                apply_chain(target, chain)
                result = subprocess.run(['patch', '-s', '--batch', '-p1', '-i', str(PATCH)],
                                        cwd=target, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                source = (target / 'AppKit/NSStatusItem.m').read_text()
                enum = re.search(r'enum\s*\{([^}]*DarlingStatusMenuReopen[^}]*)\};', source)
                event = re.search(r'typedef struct\s*\{([^}]*int32_t kind;[^}]*)\}\s*DarlingStatusEvent;', source)
                self.assertIsNotNone(enum)
                self.assertIsNotNone(event)
                program = '#include <stdint.h>\n#include <stddef.h>\n' + event.group(0) + '\n' + enum.group(0) + '''
_Static_assert(sizeof(DarlingStatusEvent) == 20, "event size");
_Static_assert(offsetof(DarlingStatusEvent, x) == 4 && offsetof(DarlingStatusEvent, horizontal) == 16, "event offsets");
_Static_assert(DarlingStatusMenuClick == 5 && DarlingStatusMenuOpen == 6 &&
               DarlingStatusMenuClose == 7 && DarlingStatusMenuReopen == 8, "event kinds");
'''
                subprocess.run(['cc', '-std=c11', '-Werror', '-fsyntax-only', '-x', 'c', '-'],
                               input=program, text=True, check=True)
                poll = source.split('- (void) _pollNativeEvents {', 1)[1].split('- (void) _destroyNative {', 1)[0]
                self.assertRegex(poll, r'case DarlingStatusMenuReopen:\s*\[NSApp _reopen\];\s*break;')
                self.assertIn('if (!_enabled)', poll)
                bar = (target / 'AppKit/NSStatusBar.m').read_text()
                self.assertIn('[[NSRunLoop mainRunLoop] addTimer: _darlingPollTimer', bar)
                self.assertIn('[item _pollNativeEvents]', bar)


if __name__ == '__main__':
    unittest.main()
