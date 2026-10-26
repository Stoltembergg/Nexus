"""Test research harness helpers with synthetic bytes and mocked subprocesses."""
import importlib.util
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('parser_lab_fixture', ROOT / 'research/pr144/parser_lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def fixture():
    segment = bytearray(72 + 80)
    struct.pack_into('<II', segment, 0, 0x19, len(segment))
    struct.pack_into('<I', segment, 64, 1)
    segment[72:88] = b'__text'.ljust(16, b'\0')
    struct.pack_into('<I', segment, 72 + 48, 256)
    header = struct.pack('<IIIIIIII', 0xfeedfacf, 0x1000007, 3, 6, 1, len(segment), 0, 0)
    return bytearray(header + segment + b'\0' * (512 - len(header) - len(segment)))


class ParserLabTests(unittest.TestCase):
    def test_text_offset_in_own_synthetic_image(self):
        self.assertEqual(lab.text_offset(fixture()), 256)

    def test_short_header_is_rejected(self):
        with self.assertRaises(ValueError):
            lab.text_offset(b'\0' * 12)

    def test_command_must_fit_declared_command_area(self):
        data = fixture()
        struct.pack_into('<I', data, 20, 8)
        with self.assertRaises(ValueError):
            lab.text_offset(data)

    def test_section_table_must_fit_command(self):
        data = fixture()
        struct.pack_into('<I', data, 32 + 64, 100)
        with self.assertRaises(ValueError):
            lab.text_offset(data)

    def test_section_must_point_inside_fixture(self):
        data = fixture()
        struct.pack_into('<I', data, 32 + 72 + 48, len(data))
        with self.assertRaises(ValueError):
            lab.text_offset(data)

    def test_embedded_copy_excludes_patch_headers(self):
        patch_text = ('diff --git a/test.c b/test.c\nnew file mode 100644\n'
                      '--- /dev/null\n+++ b/test.c\n@@ -0,0 +1,2 @@\n+one\n+two\n')
        self.assertEqual(lab.embedded_file(patch_text, 'test.c'), 'one\ntwo\n')

    def test_exported_fix_is_a_valid_patch_for_three_source_files(self):
        result = subprocess.run(['git', 'apply', '--numstat', str(ROOT / 'research/pr144/sizeofcmds-fix.patch')],
                                check=True, capture_output=True, text=True, timeout=5)
        names = {line.split('\t')[-1] for line in result.stdout.splitlines()}
        self.assertEqual(names, {'tools/dc-codesign/dc_codesign.c',
                                 'patches/darling.patch', 'patches/darlingserver.patch'})

    def test_wrong_revision_is_refused(self):
        with patch.object(lab, 'command', return_value=SimpleNamespace(stdout='wrong-head\n')):
            with self.assertRaises(ValueError):
                lab.checked_source(Path('/fixture'))

    def test_clean_pinned_revision_is_accepted(self):
        with patch.object(lab, 'command', side_effect=[SimpleNamespace(stdout=lab.PIN), SimpleNamespace(stdout='')]):
            self.assertEqual(lab.checked_source(Path('/fixture')), (lab.PIN, []))

    def test_parser_edits_require_explicit_opt_in(self):
        replies = [SimpleNamespace(stdout=lab.PIN), SimpleNamespace(stdout='tools/dc-codesign/dc_codesign.c\n')]
        with patch.object(lab, 'command', side_effect=replies):
            with self.assertRaises(ValueError):
                lab.checked_source(Path('/fixture'))
        with patch.object(lab, 'command', side_effect=replies):
            _, changes = lab.checked_source(Path('/fixture'), True)
            self.assertEqual(changes, ['tools/dc-codesign/dc_codesign.c'])

    def test_nonparser_edits_are_refused_even_with_opt_in(self):
        with patch.object(lab, 'command', side_effect=[SimpleNamespace(stdout=lab.PIN), SimpleNamespace(stdout='scripts/install-runtime.sh\n')]):
            with self.assertRaises(ValueError):
                lab.checked_source(Path('/fixture'), True)

    def test_rejection_is_distinct_from_crash_or_tool_failure(self):
        for code, expected in ((0, True), (1, False)):
            with self.subTest(code=code), patch.object(lab.subprocess, 'run',
                                                     return_value=subprocess.CompletedProcess('fixture', code, '', '')):
                self.assertIs(lab.parser_result('parser', 'info', 'fixture'), expected)
        for code, stderr in ((-11, ''), (2, ''), (1, 'AddressSanitizer: failure'), (1, 'runtime error: invalid input')):
            with self.subTest(code=code, stderr=stderr), patch.object(lab.subprocess, 'run',
                                                                     return_value=subprocess.CompletedProcess('fixture', code, '', stderr)):
                with self.assertRaises(RuntimeError):
                    lab.parser_result('parser', 'info', 'fixture')


if __name__ == '__main__':
    unittest.main()
