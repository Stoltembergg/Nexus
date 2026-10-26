"""Static checks only: the interposing diagnostic must never reach an install, build or launch path."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / 'research/diagnostics'
NEEDLES = ('riot-mvg-dependency-trace', 'mvg-dependency-trace', 'RiotMvgDependencyTrace',
           'research/diagnostics', 'NEXUS_DIAG_ALLOW_INTERPOSE')
SUFFIXES = {'.sh', '.py', '.nix', '.desktop', '.cmake', '.txt', '.json', '.c', '.m', '.patch'}


def launch_and_install_files():
    roots = [ROOT / 'scripts', ROOT / 'tools', ROOT / 'patches', ROOT / 'upstream']
    files = [p for r in roots if r.exists() for p in r.rglob('*') if p.is_file()]
    files += [p for p in ROOT.iterdir() if p.is_file() and (p.suffix in SUFFIXES or p.name in ('flake.nix',))]
    return [p for p in files if p.suffix in SUFFIXES or p.name == 'flake.nix']


class DiagnosticIsolationTests(unittest.TestCase):
    def test_diagnostic_lives_only_in_research(self):
        self.assertTrue((DIAG / 'riot-mvg-dependency-trace.c').is_file())
        self.assertFalse((ROOT / 'tools/riot-mvg-dependency-trace.c').exists())
        self.assertFalse((ROOT / 'tools/build-riot-mvg-dependency-trace.py').exists())

    def test_no_install_build_or_launch_path_references_it(self):
        for path in launch_and_install_files():
            text = path.read_text(errors='ignore')
            for needle in NEEDLES:
                with self.subTest(path=str(path.relative_to(ROOT)), needle=needle):
                    self.assertNotIn(needle, text)

    def test_configure_copies_only_tools(self):
        text = (ROOT / 'scripts/configure.py').read_text()
        self.assertNotIn('research', text)

    def test_only_interpose_source_is_the_guarded_diagnostic(self):
        hits = [p for p in launch_and_install_files() if '__interpose' in p.read_text(errors='ignore')]
        self.assertEqual(hits, [])

    def test_runtime_guard_and_warning(self):
        source = (DIAG / 'riot-mvg-dependency-trace.c').read_text()
        self.assertIn('NEVER USE WITH A REAL OR MAIN ACCOUNT', source)
        self.assertIn('LIVE RIOT SERVERS', source)
        self.assertIn('getenv("NEXUS_DIAG_ALLOW_INTERPOSE")', source)
        self.assertIn('if (diag_allowed && (observe)', source)
        build = (DIAG / 'build-mvg-dependency-trace.py').read_text()
        self.assertIn("os.environ.get('NEXUS_DIAG_ALLOW_INTERPOSE') != '1'", build)

    def test_dyld_insert_libraries_never_set_in_launch_paths(self):
        assign = re.compile(r'(?<![-\w])DYLD_INSERT_LIBRARIES\s*=\s*\S')
        launchers = [ROOT / 'darling-lol-launcher.sh', *(ROOT / 'scripts').glob('*.sh'),
                     *(ROOT / 'tools').glob('*.sh'), *(ROOT / 'tools').glob('*.desktop')]
        for path in launchers:
            for number, line in enumerate(path.read_text(errors='ignore').splitlines(), 1):
                with self.subTest(path=str(path.relative_to(ROOT)), line=number):
                    self.assertIsNone(assign.search(line), line)
        self.assertIn('-u DYLD_INSERT_LIBRARIES', (ROOT / 'tools/run-riot-client.sh').read_text())


if __name__ == '__main__':
    unittest.main()
