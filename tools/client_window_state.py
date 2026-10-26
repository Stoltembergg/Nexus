#!/usr/bin/env python3
"""Read-only client-window detection for recovery/supervision safety decisions.

True means a client window exists (including minimized or off-workspace), False
means a valid inventory contained none, and None means the state is unknown.
A caller must never treat None as permission to stop a session.
"""
import json
import os
import re
import subprocess

CLIENT_NAMES = ('riot', 'league')
MAX_WINDOWS = 256
MAX_OUTPUT = 1024 * 1024
X11_LIST = re.compile(r'^_NET_CLIENT_LIST\(WINDOW\):\s*window id #\s*'
                      r'((?:0x[0-9a-fA-F]+\s*,?\s*)*)$')


def backend(environ=None):
    env = os.environ if environ is None else environ
    desktops = re.split(r'[:;]', env.get('XDG_CURRENT_DESKTOP', '').lower())
    return 'niri' if env.get('NIRI_SOCKET') or 'niri' in desktops else 'x11'


def niri_windows_present(text):
    """Niri enumerates windows on every workspace, including the iNiR stash."""
    try:
        windows = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(windows, list) or len(windows) > MAX_WINDOWS:
        return None
    unknown = False
    for window in windows:
        if (not isinstance(window, dict) or type(window.get('id')) is not int
                or window['id'] < 0 or 'app_id' not in window or 'title' not in window):
            unknown = True
            continue
        app, title = window['app_id'], window['title']
        if any(value is not None and not isinstance(value, str) for value in (app, title)):
            unknown = True
            continue
        identity = ((app or '') + ' ' + (title or '')).lower().strip()
        if any(name in identity for name in CLIENT_NAMES):
            return True
        if not identity:
            unknown = True
    return None if unknown else False


def client_windows_present(environ=None, check_output=None):
    """Query the native compositor when on Niri; do not fall back on its failure.

    Xwayland's EWMH root list can be missing or incomplete under Niri. Falling
    back could mistake a minimized or off-workspace window for a closed client.
    Titles/IDs are inspected locally and are never printed or persisted.
    """
    query = subprocess.check_output if check_output is None else check_output

    def output(command):
        result = query(command, text=True, stderr=subprocess.DEVNULL, timeout=5)
        if not isinstance(result, str) or len(result) > MAX_OUTPUT:
            raise ValueError('Invalid window inventory')
        return result.strip()

    try:
        if backend(environ) == 'niri':
            return niri_windows_present(output(['niri', 'msg', '--json', 'windows']))
        listing = X11_LIST.fullmatch(output(['xprop', '-root', '_NET_CLIENT_LIST']))
        if listing is None:
            return None
        ids = set(re.findall(r'0x[0-9a-fA-F]+', listing[1]))
        if len(ids) > MAX_WINDOWS:
            return None
        unknown = False
        for window_id in ids:
            classes = output(['xprop', '-id', window_id, 'WM_CLASS'])
            if not classes.startswith('WM_CLASS(STRING) ='):
                unknown = True
                continue
            names = re.findall(r'"([^"\n]*)"', classes)
            if not names or not any(names):
                unknown = True
            if any(marker in name.lower() for name in names for marker in CLIENT_NAMES):
                return True
        return None if unknown else False
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main():
    state = client_windows_present()
    print(json.dumps({'backend': backend(), 'read_only': True,
                      'client_windows': 'unknown' if state is None else 'present' if state else 'absent'}))
    return 1 if state is None else 0


if __name__ == '__main__':
    raise SystemExit(main())
