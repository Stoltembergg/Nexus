#!/usr/bin/env python3
"""Host-side actions of the exported tray menu.

The tray menu is produced by the client application inside Darling. Two of
its entries cannot be implemented there, so they are handled on the host by
this helper:

``quit``
    Ends the Darling session of this prefix. Every process of the game tree
    belongs to that session, so they all end with it. The session is asked to
    stop through ``darling shutdown``; nothing is killed by name and no
    process outside this prefix is touched. A running match asks for
    confirmation first.

``reopen``
    Brings the Riot Client window back after it was closed, without
    restarting the session. When the window no longer exists the action
    reports that instead: the session is never restarted behind the user's
    back.

The helper only acts on the prefix of the session that started it
(``DPREFIX``). It never reads or writes account data, and it never touches
the client binaries.
"""

import argparse
import ctypes
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

GAME_NAME = 'LeagueofLegends'
CLIENT_CLASS = 'riot client'
SOCK_VARIABLE = b'__mldr_sockpath'
SOCK_NAME = '.darlingserver.sock'
STOP_WAIT_SECONDS = 30
LOG_FILE = Path("@PROJECT_ROOT@") / 'build' / 'riot-menu-action.log'


def log(message):
    """Record one line in the private log of this helper."""
    line = f"{time.strftime('%H:%M:%S')} {message}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open('a') as handle:
            handle.write(line + '\n')
    except OSError:
        pass


def session_prefix():
    """The prefix of this session. It is the only path this helper acts on."""
    value = os.environ.get('DPREFIX') or str(Path.home() / '.darling')
    prefix = Path(value).expanduser()
    if not prefix.is_absolute():
        raise SystemExit(f'DPREFIX must be an absolute path: {prefix}')
    return prefix.resolve()


def prefix_server(prefix):
    """PID of this prefix's darlingserver, or 0 when there is none."""
    try:
        pid = int((prefix / '.init.pid').read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return 0
    process = Path('/proc') / str(pid)
    try:
        argv = (process / 'cmdline').read_bytes().split(b'\0')
        owner = process.stat().st_uid
    except (FileNotFoundError, ProcessLookupError, OSError):
        return 0
    if (pid <= 0 or owner != os.getuid() or len(argv) < 2
            or os.path.basename(argv[0]) != b'darlingserver'
            or Path(os.fsdecode(argv[1])).resolve() != prefix):
        return 0
    return pid


def capture(command, timeout=5):
    """Run a command and return its output, or an empty string on failure."""
    try:
        return subprocess.check_output(command, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ''


def process_environment(proc):
    """The environment of a host process, or None when it cannot be read."""
    try:
        raw = (proc / 'environ').read_bytes()
    except (FileNotFoundError, ProcessLookupError, OSError):
        return None
    result = {}
    for item in raw.split(b'\0'):
        if b'=' in item:
            key, value = item.split(b'=', 1)
            result[key] = value
    return result


def game_running(prefix, proc_root=Path('/proc')):
    """Whether a match of this prefix is running.

    The game is attributed to the prefix through the loader socket, because
    the guest processes do not carry DPREFIX themselves.
    """
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return False
    for proc in entries:
        if not proc.name.isdigit():
            continue
        try:
            executable = (proc / 'cmdline').read_bytes().split(b'\0')[0].decode(errors='replace')
        except (FileNotFoundError, ProcessLookupError, OSError):
            continue
        if not executable.endswith('/' + GAME_NAME):
            continue
        environment = process_environment(proc)
        if environment is None:
            continue
        socket = environment.get(SOCK_VARIABLE)
        if socket is None:
            continue
        try:
            if Path(os.fsdecode(socket)).parent.resolve() == (prefix / SOCK_NAME).parent.resolve():
                return True
        except OSError:
            continue
    return False


def notify(summary, body):
    """Show a desktop notification when the desktop offers one."""
    if not shutil.which('notify-send'):
        return
    subprocess.run(['notify-send', '--app-name=Nexus', summary, body],
                   check=False, capture_output=True, timeout=10)


def confirm(summary, body):
    """Ask the user. Returns True, False, or None when no dialog is possible."""
    zenity = shutil.which('zenity')
    if not zenity:
        return None
    try:
        result = subprocess.run([zenity, '--question', f'--title={summary}', f'--text={body}'],
                                check=False, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def stop_session(prefix):
    """Ask the session to stop and wait for its server to disappear."""
    environment = dict(os.environ, DPREFIX=str(prefix))
    try:
        subprocess.run(['darling', 'shutdown'], check=False, capture_output=True,
                       timeout=60, env=environment)
    except (OSError, subprocess.SubprocessError) as error:
        log(f'the shutdown request failed: {error}')
        return False
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not prefix_server(prefix):
            return True
        time.sleep(0.5)
    return not prefix_server(prefix)


def quit_action(prefix):
    """End every process of the game tree by ending this session."""
    if game_running(prefix):
        answer = confirm('Encerrar a partida?',
                         'Uma partida está em andamento. Encerrar a sessão do '
                         'Riot Client também encerra a partida. Continuar?')
        if answer is not True:
            if answer is None:
                log('a match is running and no confirmation dialog is available; '
                    'the session was left running')
                notify('Riot Client', 'Uma partida está em andamento. Use o '
                       'lançador para encerrar a sessão.')
            else:
                log('the shutdown was cancelled')
            return 1
    log(f'asking the session of {prefix} to stop')
    if not stop_session(prefix):
        log('the session did not stop in time')
        notify('Riot Client', 'A sessão não foi encerrada. Use o lançador para tentar de novo.')
        return 1
    log('the session stopped')
    notify('Riot Client', 'A sessão do Riot Client foi encerrada.')
    return 0


def xprop_value(window, prop):
    return capture(['xprop', '-id', window, prop])


def window_pid(window):
    match = re.search(r'=\s*(\d+)', xprop_value(window, '_NET_WM_PID'))
    return int(match.group(1)) if match else None


def host_socket_for_guest(guest_pid, proc_root=Path('/proc')):
    """The loader socket of the host process that runs a guest PID."""
    direct = proc_root / str(guest_pid)
    if direct.exists():
        environment = process_environment(direct)
        if environment and SOCK_VARIABLE in environment:
            return environment[SOCK_VARIABLE]
    sockets = set()
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    for proc in entries:
        if not proc.name.isdigit():
            continue
        try:
            status = (proc / 'status').read_text()
        except (OSError, FileNotFoundError, ProcessLookupError):
            continue
        for line in status.splitlines():
            if line.startswith('NSpid:') and str(guest_pid) in line.split()[1:]:
                environment = process_environment(proc)
                if environment and SOCK_VARIABLE in environment:
                    sockets.add(environment[SOCK_VARIABLE])
                break
    return sockets.pop() if len(sockets) == 1 else None


def belongs_to_prefix(window, prefix, proc_root=Path('/proc')):
    """Whether a window belongs to this prefix. Unknown windows are refused."""
    pid = window_pid(window)
    if pid is None:
        return False
    socket = host_socket_for_guest(pid, proc_root)
    if socket is None:
        return False
    try:
        return Path(os.fsdecode(socket)).parent.resolve() == (prefix / SOCK_NAME).parent.resolve()
    except OSError:
        return False


def client_windows(prefix, proc_root=Path('/proc')):
    """Every Riot Client window of this prefix, mapped or not.

    The managed list of the desktop is checked first. When the window is not
    managed any more, the whole window tree is searched, so a window that was
    withdrawn by the client can still be found.
    """
    found = []
    listing = capture(['xprop', '-root', '_NET_CLIENT_LIST'])
    for raw in re.findall(r'0x[0-9a-fA-F]+', listing):
        value = xprop_value(raw, 'WM_CLASS').lower()
        if CLIENT_CLASS not in value:
            continue
        if belongs_to_prefix(raw, prefix, proc_root):
            found.append(raw)
    if found:
        return found
    tree = capture(['xwininfo', '-root', '-tree'], timeout=10)
    for raw, instance, klass in re.findall(
            r'^\s*(0x[0-9a-fA-F]+)\s+"[^"]*":\s+\("([^"]*)"\s+"([^"]*)"\)', tree, re.M):
        if CLIENT_CLASS not in klass.lower() and CLIENT_CLASS not in instance.lower():
            continue
        if belongs_to_prefix(raw, prefix, proc_root):
            found.append(raw)
    return found


class X11:
    """The few X11 calls this helper needs."""

    def __init__(self):
        self.lib = ctypes.CDLL('libX11.so.6')
        self.lib.XOpenDisplay.restype = ctypes.c_void_p
        self.lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.lib.XMapRaised.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.lib.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.lib.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        self.lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        error_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        self._error_handler = error_type(lambda _display, _event: 0)
        self.lib.XSetErrorHandler.argtypes = [error_type]
        self.lib.XSetErrorHandler.restype = ctypes.c_void_p
        self.lib.XSetErrorHandler(self._error_handler)
        self.display = self.lib.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError('cannot open the display')

    def show(self, window):
        """Map, raise and focus a window."""
        self.lib.XMapRaised(self.display, window)
        self.lib.XRaiseWindow(self.display, window)
        self.lib.XSync(self.display, 0)
        self.lib.XSetInputFocus(self.display, window, 1, 0)
        self.lib.XSync(self.display, 0)

    def close(self):
        self.lib.XCloseDisplay(self.display)


def reopen_action(prefix):
    """Bring the Riot Client window back without restarting the session."""
    windows = client_windows(prefix)
    if not windows:
        log('no Riot Client window of this prefix exists')
        notify('Riot Client', 'A janela do Riot Client não existe mais. '
               'A sessão não foi reiniciada.')
        return 1
    try:
        x11 = X11()
    except (OSError, RuntimeError) as error:
        log(f'the display cannot be used: {error}')
        notify('Riot Client', 'A janela do Riot Client não pôde ser aberta.')
        return 1
    try:
        for window in windows:
            x11.show(int(window, 16))
            log(f'the client window {window} was mapped and focused')
    finally:
        x11.close()
    notify('Riot Client', 'O Riot Client foi aberto.')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('quit', 'reopen'))
    arguments = parser.parse_args()
    try:
        prefix = session_prefix()
    except SystemExit as error:
        log(str(error))
        return 1
    if arguments.action == 'quit':
        return quit_action(prefix)
    return reopen_action(prefix)


if __name__ == '__main__':
    raise SystemExit(main())
