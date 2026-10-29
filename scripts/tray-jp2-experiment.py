#!/usr/bin/env python3
"""Optional desktop-only entry point for the isolated tray/JP2 stage."""
import os
from pathlib import Path
import subprocess
import sys

from common import ROOT, configuration


def quote(value):
    value = value.replace('%', '%%')
    return '"' + ''.join('\\' + c if c in '"`$\\' else c for c in value) + '"'


def desktop_directory():
    try:
        result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, check=True)
        path = Path(result.stdout.strip())
        if result.stdout.strip() and path.is_dir():
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    for name in ('Desktop', 'Área de trabalho'):
        path = Path.home() / name
        if path.is_dir():
            return path
    raise ValueError('Pasta da área de trabalho não encontrada.')


def install_shortcut():
    directory = desktop_directory()
    content = ('[Desktop Entry]\nType=Application\nVersion=1.0\n'
               'Name=Nexus tray/JP2 (experimental)\n'
               'Comment=Inicia o estágio experimental, fora da API\n'
               f'Exec={quote(sys.executable)} {quote(str(Path(__file__).resolve()))}\n'
               f'Path={str(ROOT).replace(chr(92), chr(92)*2)}\n'
               'Icon=darling-launcher\nTerminal=false\nCategories=Game;\n'
               'X-Nexus-Tray-JP2-Experiment=1\n')
    for number in range(1000):
        suffix = '' if number == 0 else f'-{number}'
        path = directory / f'nexus-tray-jp2-experimental{suffix}.desktop'
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
        except FileExistsError:
            continue
        with os.fdopen(fd, 'w') as file:
            file.write(content)
        try:
            subprocess.run(['gio', 'set', str(path), 'metadata::trusted', 'true'], check=False, capture_output=True)
        except OSError:
            pass
        return path
    raise ValueError('Não há nome disponível para o atalho experimental.')


def no_new_privs():
    return any(line.split() == ['NoNewPrivs:', '1'] for line in Path('/proc/self/status').read_text().splitlines())


def binary_valid(path, magic):
    try:
        if not path.is_file():
            return False
        with path.open('rb') as file:
            return file.read(4) in magic
    except OSError:
        return False


MACHO_MAGIC = {bytes.fromhex(value) for value in
               ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe',
                'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}


def framework_valid(stage, name):
    framework = stage / (name + '.framework')
    candidates = [framework / name, *framework.glob('Versions/*/' + name)]
    return any(binary_valid(path, MACHO_MAGIC) for path in candidates)


def experiment_environment():
    stage = Path(os.environ.get('NEXUS_TRAY_JP2_STAGE', str(ROOT / 'build/tray-jp2-experiment'))).expanduser()
    if not stage.is_absolute() or ':' in str(stage):
        raise ValueError('O caminho do estágio experimental deve ser absoluto e não conter dois-pontos.')
    stage = stage.resolve()
    missing = [name + '.framework' for name in ('AppKit', 'Onyx2D') if not framework_valid(stage, name)]
    for name, magic in (('libopenjp2.dylib', MACHO_MAGIC), ('libDarlingStatusNotifier.dylib', MACHO_MAGIC),
                        ('libdarling-status-notifier.so', {b'\x7fELF'})):
        if not binary_valid(stage / name, magic):
            missing.append(name)
    if missing:
        raise ValueError(f'Estágio experimental ausente ou incompleto: {stage}\nFaltando: {", ".join(missing)}')
    # The Mach-O bridge embeds the host ELF path at build time; moving the
    # stage without rebuilding it would otherwise silently load another copy.
    host_library = os.fsencode(str(stage / 'libdarling-status-notifier.so')) + b'\0'
    if host_library not in (stage / 'libDarlingStatusNotifier.dylib').read_bytes():
        raise ValueError('A biblioteca experimental aponta para outro estágio; reconstrua o wrapper para este caminho.')
    if no_new_privs():
        raise ValueError('NoNewPrivs está ativo. Abra o atalho diretamente pela área de trabalho, não pela API.')
    config = configuration()
    prefix = Path(os.environ.get('DPREFIX') or config['prefix'])
    home = Path(os.environ.get('RIOT_GUEST_HOME') or str(prefix / config['guest_home'].lstrip('/')))
    try:
        guest_home = '/' + str(home.relative_to(prefix))
    except ValueError:
        raise ValueError('RIOT_GUEST_HOME deve estar dentro de DPREFIX.')
    env = os.environ.copy()
    guest_stage = '/Volumes/SystemRoot' + str(stage)
    for key, fallback in (('DYLD_FRAMEWORK_PATH', 'RuntimeFrameworks'), ('DYLD_LIBRARY_PATH', 'RuntimeLibraries')):
        env[key] = guest_stage + ':' + (env.get(key) or guest_home + '/' + fallback)
    env['DARLING_STATUS_NOTIFIER_LIBRARY'] = guest_stage + '/libDarlingStatusNotifier.dylib'
    # Tracing is deliberately not enabled: menu-count diagnostics may disclose activity.
    env['RCLOL_CLEAN_ON_EXIT'] = '0'
    for key in ('RCLOL_RECOVER_STALE_CLIENT', 'RCLOL_RECOVER_HIDDEN_CLIENT',
                'RCLOL_CLEAN_STALE_HELPERS', 'RCLOL_CLOSE_CLIENT_IN_GAME', 'RCLOL_HIDE_CLIENT_IN_GAME'):
        env[key] = '0'
    env['DPREFIX'] = str(prefix)
    return env


def start_experiment(env):
    # The normal start action verifies the prefix server and refuses to reuse it.
    # It never invokes stop/restart; its output explains failures to the user.
    return subprocess.run(['bash', str(ROOT / 'scripts/riot-launcher.sh'), 'start'],
                          env=env, capture_output=True, text=True, check=False)


def main():
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
    except (ImportError, ValueError) as error:
        print(f'GTK 3 indisponível: {error}', file=sys.stderr)
        return

    def dialog(kind, text, buttons):
        window = Gtk.MessageDialog(message_type=kind, buttons=buttons, text='Nexus experimental')
        window.format_secondary_text(text)
        try:
            return window.run()
        finally:
            window.destroy()

    try:
        if sys.argv[1:] == ['--install']:
            if dialog(Gtk.MessageType.QUESTION, 'Criar um atalho experimental tray/JP2 na área de trabalho? Não altera o lançador normal.', Gtk.ButtonsType.YES_NO) != Gtk.ResponseType.YES:
                return
            path = install_shortcut()
            dialog(Gtk.MessageType.INFO, f'Atalho criado: {path}\nAbra-o diretamente pela área de trabalho.', Gtk.ButtonsType.OK)
            return
        if sys.argv[1:]:
            raise ValueError('Opção desconhecida.')
        env = experiment_environment()
        result = start_experiment(env)
        if result.returncode:
            dialog(Gtk.MessageType.ERROR, 'Não foi possível iniciar o experimento. Nenhuma sessão foi encerrada.\n' + (result.stdout + result.stderr).strip(), Gtk.ButtonsType.OK)
    except (OSError, ValueError, KeyError) as error:
        dialog(Gtk.MessageType.ERROR, str(error), Gtk.ButtonsType.OK)


if __name__ == '__main__':
    main()
