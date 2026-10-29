"""Offline safety/parser tests. Never start Darling or touch a desktop bus."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'status_desktop_check', ROOT / 'tools/status-notifier-desktop-check.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DesktopProbeTests(unittest.TestCase):
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
