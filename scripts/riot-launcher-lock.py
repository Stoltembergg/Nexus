#!/usr/bin/env python3
"""Hold a per-prefix lock while the launcher performs one operation."""
import subprocess
import sys

from riot_operation_lock import operation_lock


def main():
    prefix, launcher, action = sys.argv[1:]
    with operation_lock(prefix):
        return subprocess.call(["bash", launcher, "--locked-" + action], close_fds=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"riot-launcher: cannot acquire lock: {exc}", file=sys.stderr)
        sys.exit(1)
