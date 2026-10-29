"""Shared helper for the experimental status-menu diagnostic patch chain.

The diagnostics are layered patches: each one refines the previous, so a
test has to apply the whole chain to a copy of the upstream AppKit sources
before it can inspect the result. Applying only the last patch fails,
because its context expects the earlier hunks.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

# The upstream AppKit tree this repository patches.
APPKIT_SOURCE = ROOT / 'build/darling-src/src/external/cocotron/AppKit'

# Layered patches, in application order. The base transport comes first,
# then the count diagnostic and its two refinements.
CHAIN = (
    'cocotron-status-notifier.patch',
    'cocotron-status-menu-count.patch',
    'cocotron-status-menu-count-visibility.patch',
    'cocotron-status-menu-count-title.patch',
)


def patch_path(name: str) -> Path:
    return ROOT / 'patches/experimental' / name


def apply_chain(directory: Path, chain=CHAIN) -> Path:
    """Apply *chain* inside *directory* and return the directory."""
    work = Path(directory)
    for name in chain:
        result = subprocess.run(
            ['patch', '-s', '--batch', '-p1', '-i', str(patch_path(name))],
            cwd=work, capture_output=True, text=True,
        )
        if result.returncode:
            raise AssertionError(
                f'{name} did not apply: {result.stdout.strip()} {result.stderr.strip()}')
    return work


def patched_appkit(chain=CHAIN) -> str:
    """Return the NSStatusItem.m source after applying *chain*.

    The upstream tree is copied first so the repository checkout is never
    modified. When the upstream tree is unavailable (a source package
    without a prepared build) the test is skipped instead of failing.
    """
    if not (APPKIT_SOURCE / 'NSStatusItem.m').is_file():
        raise unittest.SkipTest('the prepared upstream AppKit sources are not available')

    directory = Path(tempfile.mkdtemp(prefix='status-count-', dir=ROOT / 'build'))
    try:
        shutil.copytree(APPKIT_SOURCE, directory / 'AppKit')
        apply_chain(directory, chain)
        return (directory / 'AppKit/NSStatusItem.m').read_text()
    finally:
        shutil.rmtree(directory, ignore_errors=True)
