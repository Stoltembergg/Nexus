"""Offline safety/parser tests. Never start Darling or touch a desktop bus."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'status_desktop_check', ROOT / 'tools/status-notifier-desktop-check.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DesktopProbeTests(unittest.TestCase):
    def test_watcher_representation_matches_exact_items(self):
        for item in (':1.234/StatusNotifierItem', ':1.234@/StatusNotifierItem'):
            with self.subTest(item=item):
                self.assertTrue(module.watcher_contains("(<['" + item + "']>,)", ':1.234'))
                self.assertFalse(module.watcher_contains("(<['" + item + "']>,)", ':1.23'))
        self.assertFalse(module.watcher_contains('(<@as []>,)', ':1.234'))
        self.assertFalse(module.watcher_contains("(<[':1.234@/StatusNotifierItemExtra']>,)", ':1.234'))

    def test_invalid_watcher_output_is_diagnostic_not_absence(self):
        for text in ('garbage', '(<[42]>,)', '(<true>,)'):
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, 'observed|unexpected') as error:
                module.watcher_contains(text, ':1.234')
            self.assertIn(text, str(error.exception))

    def test_cleanup_permission_error_preserves_original_and_identity_guard(self):
        process = Mock()
        process.poll.return_value = None
        process.kill.side_effect = PermissionError('wrapper denied')
        snapshots = [{10: 'old', 11: 'same', 12: 'changed'}, {11: 'same'}, {12: 'new'}]
        with patch.object(module, 'owned_guests', side_effect=snapshots), \
             patch.object(module.os, 'kill', side_effect=PermissionError('guest denied')) as kill, \
             patch('sys.stderr') as stderr:
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                try:
                    raise RuntimeError('original failure')
                finally:
                    module.cleanup(process, False, Path('/probe'), {10: 'old'})
        kill.assert_called_once_with(11, module.signal.SIGKILL)
        self.assertIn('permission denied', ''.join(call.args[0] for call in stderr.write.call_args_list))

    def test_ready_line_is_parsed_amid_framework_diagnostics(self):
        text = 'framework diagnostic\nSTATUS_DESKTOP_READY bus=:1.234 click=1 blocked=2 finish=3\n'
        self.assertEqual(module.parse_ready(text), (':1.234', '1', '2', '3'))

    def test_partial_or_unrelated_lines_do_not_select_a_service(self):
        for text in ('', 'STATUS_DESKTOP_READY bus=:1.234 click=1 blocked=2',
                     'STATUS_DESKTOP_READY bus=org.other.App click=1 blocked=2 finish=3',
                     'STATUS_DESKTOP_READY bus=:1.234 click=0 blocked=2 finish=3',
                     'STATUS_DESKTOP_READY bus=:1.234 click=1 blocked=2 finish=3 injected'):
            with self.subTest(text=text):
                self.assertIsNone(module.parse_ready(text))

    def test_duplicate_or_overflowing_ids_are_rejected(self):
        for ids in ('click=1 blocked=1 finish=3', 'click=2147483648 blocked=2 finish=3'):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                module.parse_ready('STATUS_DESKTOP_READY bus=:1.234 ' + ids)

    def test_real_desktop_requires_explicit_opt_in(self):
        with patch.object(module.subprocess, 'Popen') as launch, \
             patch.object(module.subprocess, 'run') as command, \
             patch.object(module.json, 'loads') as configuration, \
             patch('sys.stderr'), self.assertRaises(SystemExit) as error:
            module.main([])
        self.assertEqual(error.exception.code, 2)
        launch.assert_not_called()
        command.assert_not_called()
        configuration.assert_not_called()

    def test_manual_mode_also_requires_desktop_opt_in(self):
        with patch.object(module.subprocess, 'Popen') as launch, \
             patch.object(module.json, 'loads') as configuration, \
             patch('sys.stderr'), self.assertRaises(SystemExit) as error:
            module.main(['--manual'])
        self.assertEqual(error.exception.code, 2)
        launch.assert_not_called()
        configuration.assert_not_called()

    def test_manual_outcome_never_marks_an_unperformed_action_as_passed(self):
        cases = {
            'STATUS_DESKTOP_DONE finished=1 clicks=1 pass=1': 'passed',
            'STATUS_DESKTOP_DONE finished=0 clicks=0 pass=0': 'deadline_reached',
            'STATUS_DESKTOP_DONE finished=1 clicks=0 pass=0': 'finished_without_confirming',
            'STATUS_DESKTOP_DONE finished=1 clicks=2 pass=0': 'unexpected_action_count',
            'STATUS_DESKTOP_READY bus=:1.2 click=1 blocked=2 finish=3': 'missing_guest_result',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(module.manual_outcome(text), expected)

    def test_manual_deadline_is_bounded_and_requires_manual_mode(self):
        for argv in (['--desktop', '--manual-timeout', '180'],
                     ['--desktop', '--manual', '--manual-timeout', '0'],
                     ['--desktop', '--manual', '--manual-timeout', '901']):
            with self.subTest(argv=argv), patch.object(module.json, 'loads') as configuration, \
                 patch('sys.stderr'), self.assertRaises(SystemExit) as error:
                module.main(argv)
            self.assertEqual(error.exception.code, 2)
            configuration.assert_not_called()


if __name__ == '__main__':
    unittest.main()
