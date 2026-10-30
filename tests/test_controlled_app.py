import importlib.util
from pathlib import Path
import threading
import unittest
from unittest import mock


APP_PATH = Path(__file__).resolve().parents[1] / 'experimental/reopen-probe/controlled-app.py'
SPEC = importlib.util.spec_from_file_location('controlled_app', APP_PATH)
APP = importlib.util.module_from_spec(SPEC)
import sys
_gi = mock.Mock()
_repo = mock.Mock()
_gi.repository = _repo
sys.modules['gi'] = _gi
sys.modules['gi.repository'] = _repo
SPEC.loader.exec_module(APP)


class FakeButton:
    def set_sensitive(self, value):
        self.sensitive = value


class ControlledAppTests(unittest.TestCase):
    def setUp(self):
        self.gi = mock.patch.dict('sys.modules', {
            'gi': _gi, 'gi.repository': _repo})
        self.gi.start()
        # Load without constructing GTK widgets; test the worker/UI handoff methods.
        APP.GLib = mock.Mock(SOURCE_REMOVE=0)

    def tearDown(self):
        self.gi.stop()

    def test_actions_run_off_thread_and_results_return_through_idle(self):
        calls = []
        app = APP.ControlledApp.__new__(APP.ControlledApp)
        app.probe = mock.Mock()
        app.probe.start.side_effect = lambda: calls.append(threading.current_thread().name) or {'map_state': 'IsViewable'}
        app.busy = False
        app.started = False
        app.closed = False
        app.status = mock.Mock()
        app.start_button, app.reopen_button, app.stop_button = (FakeButton(), FakeButton(), FakeButton())
        app.refresh_prerequisites = mock.Mock()
        app.run_action('start')
        # The mocked probe records its execution context; no backend is invoked.
        APP.GLib.idle_add.assert_called_once()
        fn, action, message, success = APP.GLib.idle_add.call_args.args
        self.assertEqual(action, 'start')
        self.assertTrue(success)
        self.assertIn('IsViewable', message)
        self.assertEqual(len(calls), 1)

    def test_failed_result_is_visible_and_does_not_claim_success(self):
        app = APP.ControlledApp.__new__(APP.ControlledApp)
        app.busy = True
        app.started = False
        app.closed = False
        app.probe = mock.Mock(process=None)
        app.status = mock.Mock()
        app.start_button, app.reopen_button, app.stop_button = (FakeButton(), FakeButton(), FakeButton())
        app.refresh_prerequisites = mock.Mock()
        app.finish_action('start', 'Falha visível: fixture ausente', False)
        self.assertIn('Falha visível', app.status.set_text.call_args.args[0])
        self.assertFalse(app.started)
        self.assertFalse(app.reopen_button.sensitive)

    def test_window_close_is_blocked_until_cooperative_stop(self):
        app = APP.ControlledApp.__new__(APP.ControlledApp)
        app.started, app.closed = True, False
        app.busy = False
        app.probe = mock.Mock(process=None)
        app.status = mock.Mock()
        self.assertFalse(app.on_delete())
        app.probe.process = mock.Mock()
        app.probe.process.poll.return_value = None
        self.assertTrue(app.on_delete())
        app.closed = True
        self.assertFalse(app.on_delete())

    def test_failed_start_with_live_process_enables_cooperative_stop(self):
        app = APP.ControlledApp.__new__(APP.ControlledApp)
        app.busy, app.started, app.closed = True, False, False
        app.probe = mock.Mock()
        app.probe.process.poll.return_value = None
        app.status = mock.Mock()
        app.start_button, app.reopen_button, app.stop_button = (FakeButton(), FakeButton(), FakeButton())
        app.refresh_prerequisites = mock.Mock()
        app.finish_action('start', 'Falha observada', False)
        self.assertTrue(app.stop_button.sensitive)
        self.assertFalse(app.started)

    def test_destroy_exits_gtk_main_loop(self):
        app = APP.ControlledApp.__new__(APP.ControlledApp)
        with mock.patch.object(APP.Gtk, 'main_quit') as quit_loop:
            app.on_destroy()
        quit_loop.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
