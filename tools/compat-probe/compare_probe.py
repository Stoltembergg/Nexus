#!/usr/bin/env python3
"""Compare two compat_probe JSON dumps (e.g. macOS vs Darling).

Exit 0 when every comparable leaf matches, 1 when there are differences,
2 on usage/IO errors. Ignores host-specific noise listed in IGNORE_EXACT
and IGNORE_PREFIX.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Values that always differ between machines and are not compatibility gaps.
IGNORE_EXACT = {
    ("uname", "nodename"),
}

IGNORE_PREFIX = (
    # Serial/UUID uniqueness is expected across prefixes; compare presence/shape separately if needed.
)


def flatten(obj: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    out: dict[tuple[str, ...], Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, prefix + (str(k),)))
    elif isinstance(obj, list):
        # Compare lists as sorted multisets of string forms for stable mounts/names.
        out[prefix] = sorted(json.dumps(x, sort_keys=True) for x in obj)
    else:
        out[prefix] = obj
    return out


def ignored(path: tuple[str, ...]) -> bool:
    if path in IGNORE_EXACT:
        return True
    joined = ".".join(path)
    return any(joined.startswith(p) for p in IGNORE_PREFIX)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("left", type=Path, help="Reference JSON (usually real macOS)")
    ap.add_argument("right", type=Path, help="Candidate JSON (usually Darling)")
    ap.add_argument("--label-left", default="macOS")
    ap.add_argument("--label-right", default="Darling")
    args = ap.parse_args()

    try:
        left = json.loads(args.left.read_text())
        right = json.loads(args.right.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    fl = flatten(left)
    fr = flatten(right)
    keys = sorted(set(fl) | set(fr), key=lambda t: ".".join(t))
    diffs = []
    only_left = []
    only_right = []
    for k in keys:
        if ignored(k):
            continue
        path = ".".join(k)
        if k not in fr:
            only_left.append(path)
            continue
        if k not in fl:
            only_right.append(path)
            continue
        if fl[k] != fr[k]:
            diffs.append((path, fl[k], fr[k]))

    print(f"Comparing {args.label_left} ({args.left}) vs {args.label_right} ({args.right})")
    print(f"Compared leaves: {len(keys)} (ignored noise paths skipped)")
    if only_left:
        print(f"\nOnly in {args.label_left}:")
        for p in only_left:
            print(f"  - {p}")
    if only_right:
        print(f"\nOnly in {args.label_right}:")
        for p in only_right:
            print(f"  - {p}")
    if diffs:
        print("\nDifferences:")
        for path, a, b in diffs:
            print(f"  {path}:")
            print(f"    {args.label_left}:  {a!r}")
            print(f"    {args.label_right}: {b!r}")

    if only_left or only_right or diffs:
        print(f"\nResult: {len(diffs)} value diffs, "
              f"{len(only_left)} only-left, {len(only_right)} only-right")
        return 1
    print("\nResult: match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
