#!/usr/bin/env python3
"""Nexus host tray using the project's native StatusNotifier transport."""
import ctypes
import fcntl
import json
import os
import stat
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'build/libdarling-status-notifier.so'


def ensure_library(library=LIBRARY):
    """Compile the native transport on demand; never require a manual step."""
    if library.is_file():
        return True
    try:
        subprocess.run([sys.executable, str(ROOT / 'tools/build-status-notifier.py'),
                        '--output', str(library)], cwd=ROOT, check=True)
        return library.is_file()
    except (OSError, subprocess.CalledProcessError):
        return False


def prefix_environment(env, config_path=ROOT / 'build/config.json'):
    """Keep an explicit caller prefix; use saved configuration only as fallback."""
    if env.get('DPREFIX'):
        return env
    try:
        env['DPREFIX'] = json.loads(config_path.read_text())['prefix']
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return env


def acquire_instance_lock(runtime_dir=None):
    runtime_dir = runtime_dir or os.environ.get('XDG_RUNTIME_DIR')
    if not runtime_dir or not Path(runtime_dir).is_absolute():
        raise RuntimeError('XDG_RUNTIME_DIR ausente ou inválido; bandeja não iniciada.')
    directory = Path(runtime_dir)
    info = directory.stat(follow_symlinks=False)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise RuntimeError('XDG_RUNTIME_DIR não pertence ao usuário ou não tem permissões privadas.')
    path = directory / 'nexus-launcher-tray.lock'
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        os.close(fd)
        raise RuntimeError('Arquivo de lock inseguro; bandeja não iniciada.')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def rendered_helper():
    helper = ROOT / 'build/runtime/tools/riot-menu-action.py'
    try:
        text = helper.read_text()
    except OSError:
        text = ''
    if not text or '@PROJECT_ROOT@' in text:
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/configure.py')],
                                cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or 'configure.py falhou').strip())
        try:
            text = helper.read_text()
        except OSError as error:
            raise RuntimeError(f'helper de ações não foi gerado: {error}') from error
    if '@PROJECT_ROOT@' in text:
        raise RuntimeError('helper de ações ainda contém caminho template; recusado por segurança.')
    return helper


class Event(ctypes.Structure):
    _fields_ = [('kind', ctypes.c_int32), ('x', ctypes.c_int32), ('y', ctypes.c_int32),
                ('delta', ctypes.c_int32), ('horizontal', ctypes.c_int32)]


class MenuEntry(ctypes.Structure):
    _fields_ = [('id', ctypes.c_int32), ('parent', ctypes.c_int32),
                ('label', ctypes.c_char_p), ('flags', ctypes.c_uint32),
                ('toggle_state', ctypes.c_int32)]


def main():
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import GLib, Gtk
    except (ImportError, ValueError) as error:
        print(f'Bandeja requer GTK 3: {error}', file=sys.stderr)
        return 1
    try:
        lock_fd = acquire_instance_lock()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if lock_fd is None:
        return 0
    os.environ.pop('DARLING_STATUS_MENU_ACTION_SCRIPT', None)
    if not ensure_library():
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE, text='Não foi possível preparar a bandeja do Nexus')
        dialog.format_secondary_text('A compilação do transporte nativo falhou. Verifique cc, pkg-config e gio-2.0; os detalhes também foram enviados ao terminal.')
        dialog.run()
        dialog.destroy()
        return 1
    try:
        lib = ctypes.CDLL(str(LIBRARY))
        lib.DarlingStatusNotifierCreate.argtypes = [ctypes.c_char_p] * 3
        lib.DarlingStatusNotifierCreate.restype = ctypes.c_void_p
        lib.DarlingStatusNotifierDestroy.argtypes = [ctypes.c_void_p]
        lib.DarlingStatusNotifierPoll.argtypes = [ctypes.c_void_p, ctypes.POINTER(Event)]
        lib.DarlingStatusNotifierPoll.restype = ctypes.c_int
        lib.DarlingStatusNotifierSetMenu.argtypes = [ctypes.c_void_p, ctypes.POINTER(MenuEntry), ctypes.c_uint32]
        lib.DarlingStatusNotifierSetMenu.restype = ctypes.c_int
    except (OSError, AttributeError) as error:
        print(f'Não foi possível carregar a bandeja nativa: {error}', file=sys.stderr)
        return 1
    item = lib.DarlingStatusNotifierCreate(b'nexus-launcher', b'Nexus Launcher', b'darling-launcher')
    if not item:
        print('Não foi possível registrar o ícone na bandeja do sistema.', file=sys.stderr)
        return 1
    menu = Gtk.Menu()
    commands = {}
    menu_items = {}
    def add(label, action, callback):
        entry = Gtk.MenuItem(label=label)
        entry.connect('activate', callback)
        menu.append(entry)
        commands[action] = label
        menu_items[action] = entry
    def open_gui(_entry):
        subprocess.Popen([sys.executable, str(ROOT / 'scripts/riot-launcher-gui.py')], cwd=ROOT)
    def action(which):
        try:
            helper = rendered_helper()
            env = prefix_environment(os.environ.copy())
            env.pop('DARLING_STATUS_MENU_ACTION_SCRIPT', None)
            subprocess.Popen([sys.executable, str(helper), which], cwd=ROOT, env=env)
        except (OSError, RuntimeError) as error:
            dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE, text='Ação do launcher indisponível')
            dialog.format_secondary_text(str(error))
            dialog.run()
            dialog.destroy()
    add('Abrir launcher', 1, open_gui)
    add('Riot Games', 2, lambda _entry: action('reopen'))
    menu.append(Gtk.SeparatorMenuItem())
    add('Sair', 3, lambda _entry: action('quit'))
    menu.show_all()
    entries = (MenuEntry * 3)(MenuEntry(1, 0, b'Abrir launcher', 3, 0),
                              MenuEntry(2, 0, b'Riot Games', 3, 0),
                              MenuEntry(3, 0, b'Sair', 3, 0))
    if not lib.DarlingStatusNotifierSetMenu(item, entries, len(entries)):
        lib.DarlingStatusNotifierDestroy(item)
        return 1
    def poll():
        event = Event()
        while lib.DarlingStatusNotifierPoll(item, ctypes.byref(event)):
            if event.kind in (1, 3):
                menu.popup_at_pointer(None)
            elif event.kind == 5 and event.x in menu_items:
                menu_items[event.x].activate()
        return GLib.SOURCE_CONTINUE
    GLib.timeout_add(100, poll)
    try:
        Gtk.main()
    finally:
        lib.DarlingStatusNotifierDestroy(item)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
