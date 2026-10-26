#!/usr/bin/env python3
"""Install the corrected core system libraries in their real prefix locations.

libsystem_kernel, libsystem_malloc, libsystem_pthread, libsystem_platform,
libobjc.A and libc++abi are Darling's own libraries, built from the pinned
Darling sources with the patches in patches/ (xnu, libmalloc, libpthread,
libplatform, objc4, libcxxabi) and relinked by tools/build-riot-*.py. Until now
the guest only reached them through DYLD_LIBRARY_PATH=<guest>/RuntimeLibraries,
and libsystem_kernel existed twice (RuntimeLibraries and the prefix), which
could diverge.

This installer puts exactly one copy of each in the place the system library
lives inside the Darling prefix (usr/lib/system/..., usr/lib/...), which
shadows the read-only SDK layer the same way the prefix copies of
LaunchServices and libvDSP already do, and then removes the RuntimeLibraries
copy of the same leaf name so dyld falls through to the system location. The
DYLD_*_PATH variables in the launcher are left alone; with the leaf names gone
from RuntimeLibraries they no longer select these six libraries.

Nothing is signed or re-labelled here: the files are Darling's build output,
unchanged. Every replaced or removed file is backed up first; --rollback
restores the previous state. Nothing is activated until every guest process
(and the Darling namespace) is restarted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

from runtime_paths import runtime_paths

ROOT = Path(__file__).resolve().parents[1]
MACHO = (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")

# (built artifact, real location inside the prefix). The artifacts are the
# final ones the install pipeline selects: the kqueue/clock relink of the
# kernel, the -O2 allocator and pthread, the -O3 platform string helpers, the
# m761 objc and the -O3 libc++abi (which contains the m765 typeinfo fix).
LIBRARIES = [
    ("build/riot-libsystem_kernel.dylib", "usr/lib/system/libsystem_kernel.dylib"),
    ("build/riot-libsystem_malloc.dylib", "usr/lib/system/libsystem_malloc.dylib"),
    ("build/riot-libsystem_pthread.dylib", "usr/lib/system/libsystem_pthread.dylib"),
    ("build/riot-libsystem_platform.dylib", "usr/lib/system/libsystem_platform.dylib"),
    ("build/riot-libobjc.A.dylib", "usr/lib/libobjc.A.dylib"),
    ("build/riot-libc++abi.dylib", "usr/lib/libc++abi.dylib"),
]
NAMES = [Path(system).name for _, system in LIBRARIES]


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def is_macho(path):
    with path.open("rb") as source:
        return source.read(4) in MACHO


def plan(root, prefix, guest_home, only=None):
    """[(artifact, system destination, RuntimeLibraries copy)] for each library."""
    entries = []
    for artifact, system in LIBRARIES:
        name = Path(system).name
        if only and name not in only:
            continue
        entries.append((root / artifact, prefix / system, guest_home / "RuntimeLibraries" / name))
    return entries


def backup_of(path, backup_folder, label):
    backup_folder.mkdir(parents=True, exist_ok=True)
    current = digest(path)
    backup = backup_folder / ("%s-%s.dylib" % (label, current))
    if backup.exists():
        if digest(backup) != current:
            raise ValueError("The existing backup has unexpected contents: " + str(backup))
    else:
        shutil.copy2(path, backup)
    return backup, current


def load_manifest(backup_folder):
    manifest = backup_folder / "manifest.json"
    if manifest.is_file():
        return json.loads(manifest.read_text())
    return {"system": {}, "removed": {}}


def install(entries, backup_folder):
    for artifact, _, _ in entries:
        if not artifact.is_file():
            raise ValueError("The artifact does not exist: " + str(artifact))
        if not is_macho(artifact):
            raise ValueError("Expected a Mach-O library: " + str(artifact))
    state = load_manifest(backup_folder)
    staged = []
    try:
        # Stage every system copy before changing anything.
        for index, (artifact, destination, _) in enumerate(entries):
            expected = digest(artifact)
            if destination.is_symlink():
                raise ValueError("Refusing to replace a symlink: " + str(destination))
            key = str(destination)
            if key not in state["system"]:
                if destination.is_file():
                    backup, previous = backup_of(destination, backup_folder, "system-%d" % index)
                    state["system"][key] = {"backup": str(backup), "previous_sha256": previous}
                else:
                    state["system"][key] = {"backup": None, "previous_sha256": None}
            state["system"][key]["sha256"] = expected
            if destination.is_file() and digest(destination) == expected:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            mode = stat.S_IMODE(destination.stat().st_mode) if destination.is_file() else 0o755
            fd, temporary = tempfile.mkstemp(prefix="." + destination.name + "-staged-",
                                             dir=destination.parent)
            staged.append((Path(temporary), destination))
            with os.fdopen(fd, "wb") as output, artifact.open("rb") as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fchmod(output.fileno(), mode)
                os.fsync(output.fileno())
            if digest(Path(temporary)) != expected:
                raise ValueError("The staged library does not match the build: " + str(artifact))
        for temporary, destination in staged:
            os.replace(temporary, destination)
        for artifact, destination, _ in entries:
            if digest(destination) != digest(artifact):
                raise ValueError("Installed library verification failed: " + str(destination))
        # Only now drop the override copies, so there is a single copy of each.
        removed = []
        for index, (_, _, overlay) in enumerate(entries):
            if overlay.is_symlink() or overlay.is_file():
                key = str(overlay)
                if key not in state["removed"]:
                    backup, previous = backup_of(overlay, backup_folder, "overlay-%d" % index)
                    state["removed"][key] = {"backup": str(backup), "previous_sha256": previous}
                overlay.unlink()
                removed.append(key)
        backup_folder.mkdir(parents=True, exist_ok=True)
        (backup_folder / "manifest.json").write_text(json.dumps(state, indent=1) + "\n")
    finally:
        for temporary, _ in staged:
            if temporary.exists():
                temporary.unlink()
    return {"installed": True, "system": [str(d) for _, d, _ in entries],
            "removed_overrides": removed, "signed": False,
            "manifest": str(backup_folder / "manifest.json"),
            "activation": "Exit the game and the clients, run darling shutdown, then start them again."}


def restore(path, backup, previous):
    backup = Path(backup)
    if not backup.is_file() or digest(backup) != previous:
        raise ValueError("The backup is missing or has unexpected contents: " + str(backup))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + "-restore-", dir=path.parent)
    with os.fdopen(fd, "wb") as output, backup.open("rb") as source:
        shutil.copyfileobj(source, output)
        output.flush()
        os.fchmod(output.fileno(), 0o755)
        os.fsync(output.fileno())
    os.replace(temporary, path)


def rollback(backup_folder):
    manifest = backup_folder / "manifest.json"
    if not manifest.is_file():
        raise ValueError("No installation manifest in " + str(backup_folder))
    state = json.loads(manifest.read_text())
    restored, removed = [], []
    for key, record in state["system"].items():
        path = Path(key)
        if record["previous_sha256"] is None:
            if path.is_file() and digest(path) == record.get("sha256"):
                path.unlink()
                removed.append(key)
        else:
            restore(path, record["backup"], record["previous_sha256"])
            restored.append(key)
    for key, record in state["removed"].items():
        restore(Path(key), record["backup"], record["previous_sha256"])
        restored.append(key)
    manifest.unlink()
    return {"rolled_back": True, "restored": restored, "removed": removed,
            "activation": "Exit the game and the clients, run darling shutdown, then start them again."}


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "build/system-libs-backups")
    parser.add_argument("--only", default=None,
                        help="comma-separated library names (run --rollback before changing the set)")
    parser.add_argument("--rollback", action="store_true")
    return parser, parser.parse_args(argv)


def main(argv=None):
    parser, arguments = parse_arguments(argv)
    try:
        if arguments.rollback:
            print(json.dumps(rollback(arguments.backup_dir)))
            return
        only = set(arguments.only.split(",")) if arguments.only else None
        if only and only - set(NAMES):
            parser.exit(1, "Unknown library: " + ", ".join(sorted(only - set(NAMES))) + "\n")
        config = json.loads((ROOT / "build/config.json").read_text())
        prefix, guest_home = runtime_paths(config)
        entries = plan(ROOT, prefix, guest_home, only)
        for artifact, _, _ in entries:
            if not artifact.is_file():
                parser.exit(1, "The library to install does not exist: " + str(artifact)
                            + "; run scripts/install-runtime.sh, which builds it first\n")
        result = install(entries, arguments.backup_dir)
    except PermissionError as error:
        parser.exit(1, "Cannot write " + str(error.filename) + "\n")
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    result["prefix"] = str(prefix)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
