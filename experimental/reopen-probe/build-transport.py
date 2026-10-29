#!/usr/bin/env python3
"""Build an isolated variant from the current native sources; fail on drift."""
import pathlib
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('production source changed; refusing ambiguous transformation: ' + old)
    return text.replace(old, new, 1)


def build(directory):
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    names = ('darling-status-notifier.c', 'darling-status-notifier.h',
             'darling-dbus-menu.c', 'darling-dbus-menu.h',
             'darling-menu-actions.c', 'darling-menu-actions.h')
    for name in names:
        text = (ROOT / 'tools' / name).read_text()
        if name == 'darling-status-notifier.h':
            text = replace_once(text,
                '    DARLING_STATUS_MENU_CLOSE  /* x = submenu ID; end guest tracking */',
                '    DARLING_STATUS_MENU_CLOSE, /* x = submenu ID; end guest tracking */\n'
                '    DARLING_STATUS_MENU_REOPEN /* x = originating menu ID */')
        if name == 'darling-dbus-menu.c':
            text = replace_once(text,
                '        if (action != DARLING_MENU_ACTION_NONE) {',
                '        if (action == DARLING_MENU_ACTION_QUIT) {')
            text = replace_once(text,
                '        if (allowed) enqueue(menu, DARLING_STATUS_MENU_CLICK, id);',
                '        if (allowed) enqueue(menu, action == DARLING_MENU_ACTION_REOPEN\n'
                '            ? DARLING_STATUS_MENU_REOPEN : DARLING_STATUS_MENU_CLICK, id);')
        (directory / name).write_text(text)
    flags = shlex.split(subprocess.check_output(
        ['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True))
    output = directory / 'reopen.so'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                    *[str(directory / n) for n in names if n.endswith('.c')],
                    '-o', str(output), *flags], check=True)
    return output


if __name__ == '__main__':
    print(build(sys.argv[1]))
