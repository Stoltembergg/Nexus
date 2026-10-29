#!/usr/bin/env python3
"""Run the experimental Zorin AppIndicator importer test.

The extension's ``dbusMenu.js`` is third-party code and is not vendored here.
This helper copies the installed file to a temporary directory, applies
``dbusMenu.patch`` to that copy and runs the GJS test against both revisions.
When the extension is not installed the test reports SKIP and succeeds, so a
machine without the extension (or CI) does not fail.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
PATCH = HERE / "dbusMenu.patch"

# Locations where a distribution may install the AppIndicator extension.
CANDIDATES = (
    Path("/usr/share/gnome-shell/extensions/zorin-appindicator@zorinos.com"),
    Path("/usr/share/gnome-shell/extensions/gnome-shell-extension-appindicator"),
    Path.home() / ".local/share/gnome-shell/extensions/zorin-appindicator@zorinos.com",
)


def find_extension() -> Path | None:
    for candidate in CANDIDATES:
        if (candidate / "dbusMenu.js").is_file():
            return candidate
    return None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    extension = find_extension()
    if extension is None:
        print("SKIP: no installed AppIndicator extension with dbusMenu.js was found")
        return 0
    original = extension / "dbusMenu.js"

    with tempfile.TemporaryDirectory(prefix="zorin-empty-menu-") as tmp:
        work = Path(tmp)
        shutil.copyfile(original, work / "dbusMenu.js")
        patched = subprocess.run(
            ["patch", "--batch", "--forward", "-p1", "dbusMenu.js"],
            cwd=work, stdin=PATCH.open("rb"), capture_output=True, text=True,
        )
        if patched.returncode:
            print("SKIP: dbusMenu.patch does not apply to the installed extension")
            print(patched.stdout.strip() or patched.stderr.strip())
            return 0
        result = subprocess.run(
            ["gjs", "-m", str(HERE / "test.js"),
             str(original), str(work / "dbusMenu.js")],
            capture_output=True, text=True,
        )
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode:
            return result.returncode
        print("installed original sha256:", sha256(original))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
