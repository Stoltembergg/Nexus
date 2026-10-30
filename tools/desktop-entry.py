#!/usr/bin/env python3
"""Create and install the GNOME / FreeDesktop desktop entries and launcher icons.

The installer writes one entry per window class the client uses, so the dock
and the panel can tell the client, the league client and an in-game match
apart. Every entry points at the graphical launcher, so the user never has
to edit a desktop file by hand.

Icons follow the project's asset policy: the icons shipped here are original
artwork. A user who wants different artwork can drop a PNG or SVG with a
known name into their own icon directory and the installer prefers it.
"""
import os
import fcntl
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path("@PROJECT_ROOT@")
HOST_HOME = Path("@HOST_HOME@")

# Marks a launcher entry created by this project.  Previous versions pointed
# Exec at this checkout's desktop-run.sh, so an entry without that marker
# belongs to someone else and is left alone.
LEGACY_RUN_SCRIPT = "scripts/desktop-run.sh"

# Distinctive fragments of the artwork the previous helper wrote.
LEGACY_SVG_MARKERS = ('id="goldGrad"', 'M172 108 L242 108')

# Characters that force Exec quoting, per the Desktop Entry specification.
EXEC_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')

# The graphical launcher, relative to the project root.
GUI_LAUNCHER = "scripts/riot-launcher-gui.py"

# Written in every entry this installer owns. It is what lets a later run
# recognise its own files and leave foreign ones alone.
ENTRY_MARKER = "X-Nexus-Desktop-Entry=1"

# Launcher scripts that mark an entry as belonging to this project, even when
# it was written before the marker key existed. The paths are absolute, so an
# entry of another project that merely runs a script with the same name is
# not mistaken for ours.
OWNED_EXECUTABLES = tuple(
    str(PROJECT_ROOT / script) for script in (
        LEGACY_RUN_SCRIPT,
        "scripts/riot-launcher-gui.sh",
        "scripts/riot-launcher-gui.py",
        "scripts/riot-launcher.sh",
    )
)

# Entries this project wrote under other names before the current naming
# scheme. They are removed when they are recognisably ours.
PREVIOUS_ENTRY_NAMES = (
    "riot-client.desktop",
    "league-of-legends.desktop",
    "league-of-legends-game.desktop",
)

# One entry per window class. Darling's AppKit derives WM_CLASS from
# -[NSProcessInfo processName], which is the basename of argv[0], so these
# are interoperability identifiers rather than user-visible names.
ENTRIES = (
    {
        "id": "darling-launcher",
        "name": "Darling Launcher",
        "comment": "Unofficial launcher for the macOS game client via Darling",
        "wm_class": "RiotClientServices",
        "icon": "darling-launcher",
        "asset": "darling-lol.svg",
        "extra": "GenericName=Game\nKeywords=Darling;Launcher;Compatibility;\n",
    },
    {
        "id": "nexus-riot-client",
        "name": "Riot Client",
        "comment": "Unofficial compatibility launcher for the Riot Client window running under Darling",
        "wm_class": "Riot Client",
        "icon": "nexus-riot-client",
        "asset": "assets/riot-client.svg",
        "extra": "Keywords=Riot;Client;Darling;\n",
    },
    {
        "id": "nexus-league-client",
        "name": "League of Legends",
        "comment": "Unofficial compatibility launcher for the League client window running under Darling",
        "wm_class": "LeagueClientUx",
        "icon": "nexus-league-client",
        "asset": "assets/league-client.svg",
        "extra": "Keywords=League;Client;Darling;\n",
    },
    {
        "id": "nexus-league-game",
        "name": "League of Legends (match)",
        "comment": "Unofficial compatibility launcher for the League of Legends window shown during a match",
        "wm_class": "LeagueofLegends",
        "icon": "nexus-league-game",
        "asset": "assets/league-game.svg",
        "extra": "Keywords=League;Match;Darling;\n",
    },
)

# Where a user may place their own artwork. The first existing file wins.
USER_ICON_DIRECTORIES = (
    HOST_HOME / ".local/share/icons",
    HOST_HOME / ".config/nexus/icons",
)
USER_ICON_SUFFIXES = (".png", ".svg")


def escape_string(value: str) -> str:
    """Escape a value of Desktop Entry type ``string``."""
    return (value.replace("\\", "\\\\").replace("\t", "\\t")
            .replace("\n", "\\n").replace("\r", "\\r"))


def quote_exec_argument(value: str) -> str:
    """Escape and quote one Exec argument as the specification requires."""
    escaped = value.replace("%", "%%")
    if not any(char in EXEC_RESERVED for char in escaped):
        return escaped
    escaped = "".join("\\" + char if char in '"`$\\' else char for char in escaped)
    return f'"{escaped}"'


def read_text(path: Path) -> str:
    """Return the text of a desktop entry, following a dangling symlink."""
    try:
        return path.read_text(errors="ignore")
    except OSError:
        try:
            return os.readlink(path)
        except OSError:
            return ""


def legacy_entry_owned(path: Path) -> bool:
    """Return True when a launcher entry was created by this project."""
    marker = str(PROJECT_ROOT / LEGACY_RUN_SCRIPT)
    text = read_text(path)
    return marker in text or marker.replace("%", "%%") in text


def entry_owned(path: Path) -> bool:
    """Return True when this project may replace the entry at *path*.

    An entry is ours when it carries the marker key or when it runs one of
    this project's launcher scripts. Anything else belongs to somebody else
    and is never overwritten.
    """
    if not (path.is_symlink() or path.exists()):
        return False
    text = read_text(path)
    if ENTRY_MARKER in text:
        return True
    if legacy_entry_owned(path):
        return True
    return any(script in text for script in OWNED_EXECUTABLES)


def remove_legacy_entry(path: Path) -> bool:
    """Remove a previous launcher entry only when this project created it."""
    if not (path.is_symlink() or path.exists()):
        return False
    if not legacy_entry_owned(path):
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def legacy_svg_owned(path: Path) -> bool:
    """Return True when an icon is the artwork the previous helper wrote."""
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return False
    return all(marker in text for marker in LEGACY_SVG_MARKERS)


def shortcut_directories() -> list:
    """Return the desktop directories that hold launcher shortcuts."""
    directories = []
    try:
        result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            path = Path(result.stdout.strip())
            if path.is_dir():
                directories.append(path)
    except Exception:
        pass
    for candidate in [HOST_HOME / "Desktop", HOST_HOME / "Área de trabalho"]:
        if candidate.is_dir() and candidate not in directories:
            directories.append(candidate)
    return directories


def user_icon(name: str):
    """Return the user's own artwork for *name*, when they provided one."""
    for directory in USER_ICON_DIRECTORIES:
        for suffix in USER_ICON_SUFFIXES:
            candidate = directory / f"{name}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def install_icon(entry, scalable_dir, png_dir) -> str:
    """Install the icon for *entry* and return the value for ``Icon=``.

    The project's own artwork is the default. When the user supplied an
    image with the same icon name, that image wins, so the artwork can be
    replaced without editing any file by hand.
    """
    name = entry["icon"]
    supplied = user_icon(name)
    if supplied is not None:
        # A bitmap belongs in the size-specific directory, a vector in the
        # scalable one. The icon name stays the same either way, so the
        # desktop entry never has to be edited.
        target_dir = png_dir if supplied.suffix == ".png" else scalable_dir
        copy_icon(supplied, target_dir / f"{name}{supplied.suffix}")
        return name

    source = PROJECT_ROOT / entry["asset"]
    if not source.is_file():
        raise SystemExit(f"launcher icon is missing: expected {entry['asset']}")
    copy_icon(source, scalable_dir / f"{name}.svg")
    return name


def desktop_content(entry, icon_name: str) -> str:
    """Build the desktop entry text for *entry*."""
    exec_cmd = quote_exec_argument(sys.executable)
    gui = quote_exec_argument(str(PROJECT_ROOT / GUI_LAUNCHER))
    project_path = escape_string(str(PROJECT_ROOT))
    action = ''
    actions_key = ''
    if entry['id'] == 'darling-launcher':
        actions_key = 'Actions=InstallExperiment;\n'
        experiment = quote_exec_argument(str(PROJECT_ROOT / 'scripts/tray-jp2-experiment.py'))
        action = f'\n[Desktop Action InstallExperiment]\nName=Instalar atalho experimental (tray/JP2)\nExec={exec_cmd} {experiment} --install\n'
    return f"""[Desktop Entry]
Version=1.0
Type=Application
Name={entry['name']}
{entry['extra']}Comment={entry['comment']}
Exec={exec_cmd} {gui}
Path={project_path}
Icon={icon_name}
Terminal=false
Categories=Game;
StartupWMClass={entry['wm_class']}
StartupNotify=false
{actions_key}{ENTRY_MARKER}
{action}"""


def target_name(entry, directory: Path) -> Path:
    """Return the file this entry uses inside *directory*.

    The familiar name is used when it is free or already ours. A file that
    belongs to somebody else is never overwritten: the entry is written under
    a project-scoped name instead.
    """
    preferred = directory / f"{entry['id']}.desktop"
    if not (preferred.is_symlink() or preferred.exists()):
        return preferred
    if safe_owned_entry(preferred):
        return preferred
    fallback = directory / f"nexus-{entry['id']}.desktop"
    if os.path.lexists(fallback) and not safe_owned_entry(fallback):
        raise FileExistsError(f"foreign launcher collision: {fallback}")
    return fallback


def safe_owned_entry(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and entry_owned(path)
    except OSError:
        return False


def write_entry(path: Path, content: str) -> None:
    """Write a desktop entry and mark it as trusted for the desktop."""
    fd, temporary = tempfile.mkstemp(prefix='.nexus-entry-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), 0o755)
        if os.path.lexists(path):
            if not safe_owned_entry(path):
                raise FileExistsError(f"foreign launcher collision: {path}")
            os.replace(temporary, path)
        else:
            # link is an atomic no-replace publication, including dangling links.
            os.link(temporary, path)
    finally:
        os.unlink(temporary) if os.path.exists(temporary) else None
    gio = shutil.which("gio")
    if gio:
        subprocess.run([gio, "set", str(path), "metadata::trusted", "true"], check=True)
    else:
        print(f"Warning: gio unavailable; could not mark launcher as trusted: {path}", file=sys.stderr)


def copy_icon(source: Path, target: Path) -> None:
    """Publish without writing through an existing symlink or hardlink."""
    fd, temporary = tempfile.mkstemp(prefix='.nexus-icon-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream, source.open('rb') as src:
            shutil.copyfileobj(src, stream)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install():
    icons_base = HOST_HOME / ".local/share/icons"
    apps_base = HOST_HOME / ".local/share/applications"

    scalable_dir = icons_base / "hicolor/scalable/apps"
    png_dir = icons_base / "hicolor/128x128/apps"
    scalable_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)
    apps_base.mkdir(parents=True, exist_ok=True)

    # Remove artifacts created by older versions of this helper.  Only files
    # proven to be ours are deleted: an entry that pointed at this checkout's
    # desktop-run.sh, and the SVG with the old artwork.  The old PNG was
    # extracted from the client and cannot be verified, so it is removed only
    # when one of those proofs succeeded.
    owned = remove_legacy_entry(apps_base / "league-of-legends.desktop")
    desktop_dirs = shortcut_directories()
    for directory in desktop_dirs:
        owned = remove_legacy_entry(directory / "league-of-legends.desktop") or owned
    legacy_svgs = (scalable_dir / "league-of-legends.svg", icons_base / "league-of-legends.svg")
    if any(legacy_svg_owned(path) for path in legacy_svgs):
        owned = True

    # Entries this project wrote under earlier names are removed as well, so
    # the application menu does not show the same window twice. Only files
    # that are recognisably ours are touched.
    for name in PREVIOUS_ENTRY_NAMES:
        path = apps_base / name
        if entry_owned(path):
            try:
                path.unlink()
            except OSError:
                pass
        for directory in desktop_dirs:
            path = directory / name
            if entry_owned(path):
                try:
                    path.unlink()
                except OSError:
                    pass

    if owned:
        for legacy_icon in (
            *legacy_svgs,
            icons_base / "league-of-legends.png",
            icons_base / "hicolor/512x512/apps/league-of-legends.png",
        ):
            try:
                legacy_icon.unlink(missing_ok=True)
            except OSError:
                pass

    # The project's original launcher artwork is installed under a neutral
    # name.  Do not extract or install an icon from the game/client
    # installation.
    launcher_svg = PROJECT_ROOT / "darling-lol.svg"
    launcher_png = PROJECT_ROOT / "darling-lol.png"
    if not launcher_svg.is_file() or not launcher_png.is_file():
        raise SystemExit("launcher icon is missing: expected darling-lol.svg and darling-lol.png")
    copy_icon(launcher_svg, scalable_dir / "darling-launcher.svg")
    copy_icon(launcher_png, png_dir / "darling-launcher.png")

    for entry in ENTRIES:
        icon_name = install_icon(entry, scalable_dir, png_dir)
        content = desktop_content(entry, icon_name)

        desktop_file = target_name(entry, apps_base)
        write_entry(desktop_file, content)
        print(f"Created application launcher: {desktop_file}")

        for directory in desktop_dirs:
            desktop_shortcut = target_name(entry, directory)
            write_entry(desktop_shortcut, content)
            print(f"Created desktop shortcut: {desktop_shortcut}")

    # Refresh icon and desktop databases
    update_desktop = shutil.which("update-desktop-database")
    if update_desktop:
        subprocess.run([update_desktop, str(apps_base)], check=False)

    update_icons = shutil.which("gtk-update-icon-cache")
    if update_icons:
        subprocess.run([update_icons, "-f", "-t", str(icons_base / "hicolor")], check=False)

    print("GNOME application launchers and icons installed successfully.")


def main():
    # This lock coordinates cooperating installers only. External writers can
    # race ownership checks, directory components, replacement, or gio; this
    # is not a security boundary against concurrent mutation of those paths.
    lock_dir = HOST_HOME / '.nexus-desktop-entry-lock'
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    info = lock_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(f'unsafe installer lock directory: {lock_dir}')
    fd = os.open(lock_dir / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise RuntimeError('unsafe installer lock file')
        fcntl.flock(lock, fcntl.LOCK_EX)
        install()


if __name__ == "__main__":
    main()
