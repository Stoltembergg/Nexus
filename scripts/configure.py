#!/usr/bin/env python3
"""Render local paths into ignored runtime tools; never alter the source snapshot."""
import argparse
import json
import os
from pathlib import Path
import sys

from common import ROOT, configuration, render


def warn(message):
    print('configure: ' + message, file=sys.stderr)


def normalized(path):
    return os.path.normpath(os.path.expanduser(str(path)))


def path_is_within(path, directory):
    try:
        Path(normalized(path)).absolute().relative_to(Path(normalized(directory)).absolute())
        return True
    except ValueError:
        return False


def rehome_prefix(config, requested):
    """Follow a moved home for the default prefix; keep user-selected prefixes."""
    home = Path.home()
    if requested is not None:
        config['prefix_is_explicit'] = True
        return str(requested)

    saved = config.get('prefix')
    if not saved:
        config['prefix_is_explicit'] = False
        return str(home / '.darling')

    previous_home = config.get('host_home')
    is_old_default = bool(previous_home) and normalized(saved) == normalized(
        Path(previous_home) / '.darling')
    # Older config files have no explicitness flag. A non-default path is
    # treated as user-selected; unknown legacy paths are preserved, not moved.
    explicit = bool(config.get('prefix_is_explicit')) or not is_old_default
    config['prefix_is_explicit'] = explicit

    if previous_home and normalized(previous_home) != normalized(home):
        if explicit:
            if path_is_within(saved, previous_home):
                warn(f'prefix {saved} is inside the previous home {previous_home}; '
                     'it was kept. Pass --prefix to select another location.')
            return saved
        if is_old_default:
            new_prefix = str(home / '.darling')
            warn(f'the default prefix now points to {new_prefix}; existing data at '
                 f'{saved} was not moved or removed')
            return new_prefix
    return saved


def link_build(runtime):
    """Keep runtime/build relative so the generated scripts survive a checkout move."""
    link = runtime / 'build'
    if link.is_symlink():
        if os.readlink(link) == '..':
            return
        link.unlink()
    elif os.path.lexists(link):
        warn(f'{link} is not a symlink; leaving it untouched')
        return
    link.symlink_to('..', target_is_directory=True)


def stale_cache(build):
    """Return a CMake cache and its recorded source path when the checkout moved."""
    cache = build / 'darling-src/build/CMakeCache.txt'
    try:
        lines = cache.read_text(errors='replace').splitlines()
    except OSError:
        return None

    expected = os.path.realpath(build / 'darling-src')
    for line in lines:
        key, _, value = line.partition('=')
        if key.partition(':')[0] != 'CMAKE_HOME_DIRECTORY':
            continue
        if os.path.realpath(value) != expected:
            return cache, value
        return None
    return None


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--guest-user')
parser.add_argument('--prefix', type=Path)
parser.add_argument('--sdk', type=Path)
args = parser.parse_args()
config = configuration()

if args.guest_user:
    if not args.guest_user.replace('_', '').replace('-', '').isalnum():
        parser.error('guest user must be a simple account name')
    config['guest_user'] = args.guest_user
    config['guest_home'] = '/Users/' + args.guest_user

# Resolve before replacing host_home so the previous location is still known.
requested_prefix = args.prefix.expanduser().resolve() if args.prefix else None
config['prefix'] = rehome_prefix(config, requested_prefix)
if args.sdk:
    config['sdk'] = str(args.sdk.expanduser().resolve())
config['project_root'] = str(ROOT)
config['host_home'] = str(Path.home())

build = ROOT / 'build'
build.mkdir(exist_ok=True)
(build / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
folder = build / 'runtime/tools'
folder.mkdir(parents=True, exist_ok=True)
for source in (ROOT / 'tools').iterdir():
    if not source.is_file():
        continue
    target = folder / source.name
    # Unlink the directory entry, including dangling symlinks. Any other error
    # must abort rather than following a leftover link or writing through it.
    target.unlink(missing_ok=True)
    target.write_text(render(source.read_text(), config))
    os.chmod(target, source.stat().st_mode & 0o777)

link_build(folder.parent)
stale = stale_cache(build)
if stale:
    cache, previous = stale
    warn(f'{cache} records CMAKE_HOME_DIRECTORY={previous}, not '
         f'{build / "darling-src"}; the cache was left untouched. Review it and '
         'rebuild manually if CMake reports stale paths.')

print('Configured', len(list(folder.iterdir())), 'runtime sources for', config['guest_home'])
