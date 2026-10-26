"""Synthetic compositor inventories only; never manipulate desktop windows."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('window_state_fixture', ROOT / 'tools/client_window_state.py')
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)
NIRI = {'NIRI_SOCKET': '/fixture/niri.sock', 'XDG_CURRENT_DESKTOP': 'niri'}
X11 = {'DISPLAY': ':fixture', 'XDG_CURRENT_DESKTOP': 'fixture'}


def window(**changes):
    return {'id': 10, 'app_id': 'RiotClientServices', 'title': 'Riot Client',
            'workspace_id': 3, 'is_focused': True, **changes}


class NiriWindowTests(unittest.TestCase):
    def query(self, inventory):
        command = Mock(return_value=json.dumps(inventory))
        result = state.client_windows_present(NIRI, command)
        command.assert_called_once_with(['niri', 'msg', '--json', 'windows'], text=True,
                                        stderr=subprocess.DEVNULL, timeout=5)
        return result

    def test_active_client_is_present(self):
        self.assertIs(self.query([window()]), True)

    def test_stashed_unfocused_window_is_present(self):
        self.assertIs(self.query([window(workspace_id=99, is_focused=False)]), True)

    def test_hidden_or_inactive_output_does_not_authorize_cleanup(self):
        self.assertIs(self.query([window(workspace_id=None, is_focused=False,
                                        hidden=True, mapped=False)]), True)

    def test_native_window_title_can_identify_xwayland_client(self):
        self.assertIs(self.query([window(app_id=None, title='LeagueClientUx')]), True)

    def test_empty_valid_list_is_absent(self):
        self.assertIs(self.query([]), False)

    def test_unrelated_identifiable_window_is_absent(self):
        self.assertIs(self.query([window(app_id='editor', title='Notes')]), False)

    def test_missing_or_invalid_identity_is_unknown(self):
        for invalid in ({}, None, {'id': True, 'app_id': 'editor', 'title': 'Notes'},
                        window(app_id=None, title=None), window(title=123), {'id': 1, 'app_id': 'editor'}):
            with self.subTest(invalid=invalid):
                self.assertIsNone(self.query([invalid]))

    def test_invalid_json_or_schema_is_unknown(self):
        for text in ('not json', '{}', 'null', '["window"]'):
            with self.subTest(text=text):
                self.assertIsNone(state.client_windows_present(NIRI, Mock(return_value=text)))

    def test_known_client_still_protects_when_another_window_is_unknown(self):
        self.assertIs(self.query([{}, window()]), True)

    def test_niri_error_never_falls_back_to_xprop(self):
        for error in (FileNotFoundError(), subprocess.CalledProcessError(1, 'niri'),
                      subprocess.TimeoutExpired('niri', 5)):
            command = Mock(side_effect=error)
            with self.subTest(error=error):
                self.assertIsNone(state.client_windows_present(NIRI, command))
                self.assertEqual(command.call_count, 1)

    def test_niri_desktop_without_socket_still_uses_niri(self):
        self.assertEqual(state.backend({'XDG_CURRENT_DESKTOP': 'GNOME:niri'}), 'niri')

    def test_large_inventory_is_unknown(self):
        self.assertIsNone(self.query([window()] * (state.MAX_WINDOWS + 1)))

    def test_oversized_output_is_unknown(self):
        self.assertIsNone(state.client_windows_present(NIRI, Mock(return_value=' ' * (state.MAX_OUTPUT + 1))))

    def test_cli_prints_only_status_not_titles(self):
        with patch.object(state, 'client_windows_present', return_value=None), \
                patch.object(state, 'backend', return_value='niri'), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(state.main(), 1)
        self.assertEqual(json.loads(output.getvalue()),
                         {'backend': 'niri', 'read_only': True, 'client_windows': 'unknown'})


class X11WindowTests(unittest.TestCase):
    def test_partial_or_escaped_classes_are_unknown_not_absent(self):
        for value in ('WM_CLASS(STRING) = "editor"',
                      'WM_CLASS(STRING) = "editor", "editor" garbage',
                      'WM_CLASS(STRING) = "editor", "unterminated',
                      'WM_CLASS(STRING) = "editor", "editor", "extra"',
                      'WM_CLASS(STRING) = "ed\\itor", "editor"',
                      'WM_CLASS(STRING) = " ", " "'):
            with self.subTest(value=value):
                query = Mock(side_effect=['_NET_CLIENT_LIST(WINDOW): window id # 0x10', value])
                self.assertIsNone(state.client_windows_present(X11, query))

    def test_empty_valid_inventory_is_absent(self):
        query = Mock(return_value='_NET_CLIENT_LIST(WINDOW): window id #\n')
        self.assertIs(state.client_windows_present(X11, query), False)

    def test_missing_or_malformed_root_property_is_unknown(self):
        for text in ('_NET_CLIENT_LIST: not found.', 'failed',
                     '_NET_CLIENT_LIST(WINDOW): window id # garbage'):
            with self.subTest(text=text):
                self.assertIsNone(state.client_windows_present(X11, Mock(return_value=text)))

    def test_minimized_riot_window_is_present(self):
        query = Mock(side_effect=['_NET_CLIENT_LIST(WINDOW): window id # 0x10',
                                  'WM_CLASS(STRING) = "RiotClientServices", "RiotClientServices"'])
        self.assertIs(state.client_windows_present(X11, query), True)
        self.assertEqual(query.call_count, 2)

    def test_no_known_class_is_unknown_not_absent(self):
        for value in ('WM_CLASS: not found.', 'WM_CLASS(STRING) = "", ""', ''):
            query = Mock(side_effect=['_NET_CLIENT_LIST(WINDOW): window id # 0x10', value])
            with self.subTest(value=value):
                self.assertIsNone(state.client_windows_present(X11, query))

    def test_unrelated_window_is_absent(self):
        query = Mock(side_effect=['_NET_CLIENT_LIST(WINDOW): window id # 0x10',
                                  'WM_CLASS(STRING) = "editor", "editor"'])
        self.assertIs(state.client_windows_present(X11, query), False)

    def test_failed_query_is_unknown(self):
        query = Mock(side_effect=subprocess.CalledProcessError(1, 'xprop'))
        self.assertIsNone(state.client_windows_present(X11, query))

    def test_missing_xprop_is_unknown(self):
        query = Mock(side_effect=FileNotFoundError('xprop'))
        self.assertIsNone(state.client_windows_present(X11, query))


class UnsupportedWaylandTests(unittest.TestCase):
    def test_non_niri_wayland_with_display_uses_x11_inventory(self):
        for env in ({'WAYLAND_DISPLAY': 'wayland-fixture', 'DISPLAY': ':fixture'},
                    {'XDG_SESSION_TYPE': 'WAYLAND', 'DISPLAY': ':fixture'}):
            with self.subTest(env=env):
                query = Mock(return_value='_NET_CLIENT_LIST(WINDOW): window id #')
                self.assertEqual(state.backend(env), 'x11')
                self.assertIs(state.client_windows_present(env, query), False)
                query.assert_called_once_with(
                    ['xprop', '-root', '_NET_CLIENT_LIST'], text=True,
                    stderr=subprocess.DEVNULL, timeout=5)

    def test_native_wayland_without_display_stays_unknown(self):
        for env in ({'WAYLAND_DISPLAY': 'wayland-fixture'},
                    {'XDG_SESSION_TYPE': 'wayland'}):
            with self.subTest(env=env):
                query = Mock(return_value='_NET_CLIENT_LIST(WINDOW): window id #')
                self.assertEqual(state.backend(env), 'unsupported-wayland')
                self.assertIsNone(state.client_windows_present(env, query))
                query.assert_not_called()

    def test_niri_still_uses_native_inventory_in_wayland_session(self):
        query = Mock(return_value='[]')
        self.assertIs(state.client_windows_present({**NIRI, 'WAYLAND_DISPLAY': 'fixture'}, query), False)
        self.assertEqual(query.call_args.args[0], ['niri', 'msg', '--json', 'windows'])


if __name__ == '__main__':
    unittest.main()
