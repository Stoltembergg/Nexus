"""Synthetic inputs only: never inspect a real account, prefix or client process."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
spec = importlib.util.spec_from_file_location('diagnostic_redaction', TOOLS / 'diagnostic_redaction.py')
redaction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(redaction)


class RedactionTests(unittest.TestCase):
    def test_prefixed_riot_tokens_and_separate_arguments(self):
        for name in ('--token', '--riotclient-auth-token', '--agent-auth-token',
                     '--access-token', '--refresh-token', '--password', '--api-key'):
            for separator in ('=', ' '):
                for value in ('SYNTHETIC_VALUE', '"SYNTHETIC VALUE"', "'SYNTHETIC VALUE'"):
                    with self.subTest(name=name, separator=separator, value=value):
                        result = redaction.redact_text(name + separator + value)
                        self.assertNotIn('SYNTHETIC', result)
                        self.assertIn('<redacted>', result)

    def test_json_fields_and_camel_case_identifiers(self):
        for key in ('accessToken', 'refresh_token', 'riotclient-auth-token', 'puuid',
                    'riotId', 'accountId', 'session_id', 'apiKey', 'authorization'):
            with self.subTest(key=key):
                result = redaction.redact_text(json.dumps({key: 'SYNTHETIC_VALUE'}))
                self.assertNotIn('SYNTHETIC_VALUE', result)
                self.assertEqual(json.loads(result)[key], '<redacted>')

    def test_http_headers_and_url_secrets(self):
        text = ('Authorization: Bearer SYNTHETIC_VALUE\n'
                'Cookie: first=SYNTHETIC_ONE; second=SYNTHETIC_TWO\n'
                'Set-Cookie: session=SYNTHETIC_THREE; Secure\n'
                'https://test-user:SYNTHETIC_PASS@example.test/path?'
                'code=SYNTHETIC_CODE&state=SYNTHETIC_STATE&region=BR\n')
        result = redaction.redact_text(text)
        self.assertNotIn('SYNTHETIC', result)
        self.assertNotIn('test-user:', result)
        self.assertIn('region=BR', result)

    def test_email_home_and_custom_paths(self):
        text = f'person@example.test {Path.home()}/file /home/other/file /Users/guest/file /srv/private-prefix/file'
        result = redaction.redact_text(text, ['/srv/private-prefix'])
        for value in ('person@example.test', str(Path.home()), '/home/other',
                      '/Users/guest', '/srv/private-prefix'):
            self.assertNotIn(value, result)

    def test_private_key_jwt_and_github_token(self):
        key = ('-----BEGIN PRIVATE ' + 'KEY-----\nSYNTHETIC_KEY\n'
               '-----END PRIVATE KEY-----')
        jwt = 'eyJ' + 'A' * 24 + '.' + 'B' * 24 + '.' + 'C' * 24
        github = 'ghp_' + 'x' * 32
        result = redaction.redact_text(key + '\n' + jwt + '\n' + github)
        for value in ('SYNTHETIC_KEY', jwt, github):
            self.assertNotIn(value, result)

    def test_diagnostics_are_not_all_redacted(self):
        text = 'SIGSEGV code=1 kernel=7.3.0 region=BR --locale pt_BR --log-dir=/srv/logs'
        self.assertEqual(redaction.redact_text(text), text)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='safe diagnostics ')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.output = self.folder / 'report.json'
        self.prefix = self.folder / 'prefix'
        self.prefix.mkdir()

    def collect(self, *args):
        env = {**os.environ, 'SYNTHETIC_ENV_SECRET': 'DO_NOT_COLLECT_ENVIRONMENT'}
        return subprocess.run([sys.executable, str(TOOLS / 'collect-diagnostics.py'),
                               '--output', str(self.output), '--prefix', str(self.prefix), *args],
                              text=True, capture_output=True, env=env, timeout=10)

    def test_default_reads_no_logs_or_account_data(self):
        (self.prefix / 'account.log').write_text('DO_NOT_COLLECT_ACCOUNT_DATA')
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stderr)
        raw = self.output.read_text()
        report = json.loads(raw)
        self.assertEqual(report['logs'], [])
        self.assertTrue(report['prefix_exists'])
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        for private in ('DO_NOT_COLLECT_ACCOUNT_DATA', 'DO_NOT_COLLECT_ENVIRONMENT', str(self.prefix)):
            self.assertNotIn(private, raw)
        self.assertNotIn('hostname', report['host'])

    def test_explicit_log_is_redacted_without_modifying_input(self):
        source = self.folder / 'selected.log'
        original = '--agent-auth-token=SYNTHETIC_VALUE\nerror=SIGSEGV\n'
        source.write_text(original)
        result = self.collect('--log', str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(self.output.read_text())
        self.assertIn('SIGSEGV', report['logs'][0]['text'])
        self.assertNotIn('SYNTHETIC_VALUE', self.output.read_text())
        self.assertEqual(source.read_text(), original)
        self.assertEqual(report['logs'][0]['label'], 'log-1')

    def test_large_input_is_bounded_and_discards_partial_first_line(self):
        source = self.folder / 'large.log'
        source.write_text('DISCARDED_PREFIX\n' + 'x' * (300 * 1024) + '\nlast=OK\n')
        result = self.collect('--log', str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = json.loads(self.output.read_text())['logs'][0]
        self.assertTrue(entry['truncated'])
        self.assertEqual(entry['text'], 'last=OK\n')

    def test_symlink_input_is_refused(self):
        source = self.folder / 'real.log'
        source.write_text('PRIVATE_CONTENT')
        link = self.folder / 'link.log'
        link.symlink_to(source)
        result = self.collect('--log', str(link))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertNotIn('PRIVATE_CONTENT', result.stdout + result.stderr)

    def test_fifo_and_binary_are_refused(self):
        for name, binary in (('pipe', False), ('binary.log', True)):
            with self.subTest(name=name):
                source = self.folder / name
                if binary:
                    source.write_bytes(b'BINARY\0DATA')
                else:
                    os.mkfifo(source)
                result = self.collect('--log', str(source))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())

    def test_existing_output_and_symlink_are_not_overwritten(self):
        self.output.write_text('KEEP_EXISTING_REPORT')
        result = self.collect()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_text(), 'KEEP_EXISTING_REPORT')
        self.output.unlink()
        victim = self.folder / 'victim'
        victim.write_text('KEEP_VICTIM')
        self.output.symlink_to(victim)
        result = self.collect()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(victim.read_text(), 'KEEP_VICTIM')

    def test_missing_input_fails_without_echoing_private_path(self):
        missing = self.folder / 'PRIVATE_ACCOUNT_NAME'
        result = self.collect('--log', str(missing))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('PRIVATE_ACCOUNT_NAME', result.stdout + result.stderr)
        self.assertFalse(self.output.exists())

    def test_too_many_logs_are_refused(self):
        source = self.folder / 'sample.log'
        source.write_text('OK')
        args = [part for _ in range(11) for part in ('--log', str(source))]
        result = self.collect(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
