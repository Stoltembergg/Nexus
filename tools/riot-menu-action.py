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

The helper only acts on the prefix of the session that started it, identified
by its loader socket or an explicit ``DPREFIX``. It never reads or writes account data, and it never touches
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
    """Identify the session explicitly, never from the guest's HOME."""
    socket = os.environ.get(os.fsdecode(SOCK_VARIABLE))
    value = os.environ.get('DPREFIX')
    prefix = None
    if value is not None:
        path = Path(value)
        if not path.is_absolute():
            raise SystemExit(f'DPREFIX must be an absolute path: {value}')
        prefix = path.resolve()
    if socket is not None:
        path = Path(socket)
        if not path.is_absolute() or os.path.basename(socket) != SOCK_NAME:
            raise SystemExit(f'invalid loader socket path: {socket}')
        socket_prefix = path.parent.resolve()
        if prefix is not None and prefix != socket_prefix:
            raise SystemExit('DPREFIX conflicts with the loader socket')
        return socket_prefix
    if prefix is None:
        raise SystemExit('session prefix is not available')
    return prefix


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
    """Whether a match is running, or None if inspection is inconclusive.

    The game is attributed to the prefix through the loader socket, because
    the guest processes do not carry DPREFIX themselves.
    """
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    unknown = False
    for proc in entries:
        if not proc.name.isdigit():
            continue
        try:
            executable = (proc / 'cmdline').read_bytes().split(b'\0')[0].decode(errors='replace')
        except OSError:
            unknown = True
            continue
        if not executable.endswith('/' + GAME_NAME):
            continue
        environment = process_environment(proc)
        if environment is None:
            unknown = True
            continue
        socket = environment.get(SOCK_VARIABLE)
        if socket is None:
            unknown = True
            continue
        try:
            if Path(os.fsdecode(socket)).resolve() == (prefix / SOCK_NAME).resolve():
                return True
        except (OSError, ValueError):
            unknown = True
    return None if unknown else False


def session_processes_running(prefix, proc_root=Path('/proc')):
    """Return True for a scoped process, False if absent, None if unprovable.

    Guest processes identify their session by loader socket; the server uses
    its prefix argument. DPREFIX also identifies host-side session processes.
    Unreadable processes owned by us prevent a claim of successful shutdown.
    """
    try:
        entries = list(proc_root.iterdir())
        target = prefix.resolve()
    except (OSError, ValueError):
        return None
    unknown = False
    for proc in entries:
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            argv = (proc / 'cmdline').read_bytes().split(b'\0')
            environment = process_environment(proc)
            if environment is None:
                unknown = True
                continue
            socket = environment.get(SOCK_VARIABLE)
            dprefix = environment.get(b'DPREFIX')
            if socket and Path(os.fsdecode(socket)).resolve() == target / SOCK_NAME:
                return True
            if dprefix and Path(os.fsdecode(dprefix)).resolve() == target:
                return True
            if (len(argv) > 1 and os.path.basename(argv[0]) == b'darlingserver'
                    and Path(os.fsdecode(argv[1])).resolve() == target):
                return True
        except (OSError, ValueError):
            unknown = True
    return None if unknown else False


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


def stop_session(prefix, proc_root=Path('/proc')):
    """Ask the session to stop and prove its processes have disappeared."""
    environment = dict(os.environ, DPREFIX=str(prefix))
    try:
        result = subprocess.run(['darling', 'shutdown'], check=False, capture_output=True,
                                timeout=60, env=environment)
    except (OSError, subprocess.SubprocessError) as error:
        log(f'the shutdown request failed: {error}')
        return False
    if result.returncode != 0:
        log(f'the shutdown request returned {result.returncode}')
        return False
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if session_processes_running(prefix, proc_root) is False:
            return True
        time.sleep(0.5)
    return session_processes_running(prefix, proc_root) is False


def quit_action(prefix):
    """End every process of the game tree by ending this session."""
    match = game_running(prefix)
    if match is not False:
        answer = confirm('Encerrar a partida?',
                         ('Uma partida está em andamento. ' if match else
                          'Não foi possível verificar se há uma partida. ') +
                         'Encerrar a sessão do '
                         'Riot Client também encerra a partida. Continuar?')
        if answer is not True:
            if answer is None:
                log('a match is running or its status is unknown and no confirmation dialog is available; '
                    'the session was left running')
                notify('Riot Client', 'Uma partida pode estar em andamento. Use o '
                       'lançador para encerrar a sessão.')
            else:
                log('the shutdown was cancelled')
            return 1
    log(f'asking the session of {prefix} to stop')
    if not stop_session(prefix):
        log('the session shutdown result is inconclusive')
        notify('Riot Client', 'Não foi possível confirmar o encerramento da sessão. Use o lançador para verificar.')
        return 1
    log('the session stopped')
    notify('Riot Client', 'A sessão do Riot Client foi encerrada.')
    return 0


def xprop_value(window, prop):
    return capture(['xprop', '-id', window, prop])


class XResClientIdSpec(ctypes.Structure):
    _fields_ = [('client', ctypes.c_ulong), ('mask', ctypes.c_uint)]


class XResClientIdValue(ctypes.Structure):
    _fields_ = [('spec', XResClientIdSpec), ('length', ctypes.c_long),
                ('value', ctypes.c_void_p)]


class XRes:
    """Resolve an X resource to its local host PID, never a window property."""

    def __init__(self):
        self.x11 = ctypes.CDLL('libX11.so.6')
        self.res = ctypes.CDLL('libXRes.so.1')
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        error_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        self._error_handler = error_type(lambda _display, _event: 0)
        self.x11.XSetErrorHandler.argtypes = [ctypes.c_void_p]
        self.x11.XSetErrorHandler.restype = ctypes.c_void_p
        self._previous_handler = self.x11.XSetErrorHandler(
            ctypes.cast(self._error_handler, ctypes.c_void_p))
        self.res.XResQueryVersion.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                              ctypes.POINTER(ctypes.c_int)]
        self.res.XResQueryVersion.restype = ctypes.c_int
        self.res.XResQueryClientIds.argtypes = [ctypes.c_void_p, ctypes.c_long,
            ctypes.POINTER(XResClientIdSpec), ctypes.POINTER(ctypes.c_long),
            ctypes.POINTER(ctypes.POINTER(XResClientIdValue))]
        self.res.XResQueryClientIds.restype = ctypes.c_int
        self.res.XResGetClientPid.argtypes = [ctypes.POINTER(XResClientIdValue)]
        self.res.XResGetClientPid.restype = ctypes.c_int
        self.res.XResClientIdsDestroy.argtypes = [ctypes.c_long, ctypes.POINTER(XResClientIdValue)]
        self.res.XResClientIdsDestroy.restype = None
        self.display = self.x11.XOpenDisplay(None)
        if not self.display:
            self.x11.XSetErrorHandler(self._previous_handler)
            raise RuntimeError('cannot open the display')
        major, minor = ctypes.c_int(), ctypes.c_int()
        if (not self.res.XResQueryVersion(self.display, ctypes.byref(major), ctypes.byref(minor))
                or (major.value, minor.value) < (1, 2)):
            self.close()
            raise RuntimeError('XRes 1.2 is unavailable')

    def window_pid(self, window):
        try:
            xid = int(window, 16)
        except (ValueError, TypeError):
            return None
        if not 0 < xid <= 0xffffffff:
            return None
        spec = XResClientIdSpec(xid, 2)
        count = ctypes.c_long()
        values = ctypes.POINTER(XResClientIdValue)()
        try:
            # libXRes versions can return 0 even with a successful reply.
            # Accept only one unambiguous, populated PID result instead.
            self.res.XResQueryClientIds(self.display, 1, ctypes.byref(spec),
                                        ctypes.byref(count), ctypes.byref(values))
            if count.value != 1 or not values or not (values[0].spec.mask & 2):
                return None
            if not values[0].value or values[0].length != 4:
                return None
            pid = self.res.XResGetClientPid(ctypes.byref(values[0]))
            return pid if pid > 0 else None
        finally:
            if values:
                self.res.XResClientIdsDestroy(count.value, values)

    def close(self):
        self.x11.XCloseDisplay(self.display)
        self.x11.XSetErrorHandler(self._previous_handler)


def belongs_to_prefix(window, prefix, proc_root=Path('/proc'), xres=None):
    """Require the X server's host PID, its UID and the exact loader socket."""
    if xres is None:
        return False
    try:
        pid = xres.window_pid(window)
        if not isinstance(pid, int) or pid <= 0:
            return False
        proc = proc_root / str(pid)
        if proc.stat().st_uid != os.getuid():
            return False
        environment = process_environment(proc)
        return (environment is not None and
                environment.get(SOCK_VARIABLE) == os.fsencode(prefix / SOCK_NAME))
    except (OSError, ValueError, RuntimeError):
        return False


def plausible_client_window(window):
    """Reject auxiliary or uninspectable windows, including withdrawn ones."""
    info = capture(['xwininfo', '-id', window])
    title = re.search(r'^xwininfo: Window id: 0x[0-9a-fA-F]+ "([^"\n]+)"', info, re.M)
    width = re.search(r'^\s*Width:\s*(\d+)\s*$', info, re.M)
    height = re.search(r'^\s*Height:\s*(\d+)\s*$', info, re.M)
    override = re.search(r'^\s*Override Redirect State:\s*(yes|no)\s*$', info, re.M)
    return bool(title and title.group(1).strip() and width and height and override
                and int(width.group(1)) >= 100 and int(height.group(1)) >= 100
                and override.group(1) == 'no')


def client_windows(prefix, proc_root=Path('/proc'), xres=None):
    """Plausible Riot Client windows of this prefix, mapped or not.

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
        if belongs_to_prefix(raw, prefix, proc_root, xres) and plausible_client_window(raw):
            found.append(raw)
    if found:
        return found
    tree = capture(['xwininfo', '-root', '-tree'], timeout=10)
    for raw, instance, klass in re.findall(
            r'^\s*(0x[0-9a-fA-F]+)\s+(?:"[^"]*":|\(has no name\):)\s+\("([^"]*)"\s+"([^"]*)"\)', tree, re.M):
        if CLIENT_CLASS not in klass.lower() and CLIENT_CLASS not in instance.lower():
            continue
        if belongs_to_prefix(raw, prefix, proc_root, xres) and plausible_client_window(raw):
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
    try:
        xres = XRes()
    except (OSError, RuntimeError, AttributeError) as error:
        log(f'XRes cannot be used: {error}')
        notify('Riot Client', 'A janela do Riot Client não pôde ser identificada.')
        return 1
    try:
        windows = client_windows(prefix, xres=xres)
    finally:
        xres.close()
    if not windows:
        log('no identifiable main Riot Client window of this prefix found')
        notify('Riot Client', 'A janela principal do Riot Client não foi identificada. '
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
