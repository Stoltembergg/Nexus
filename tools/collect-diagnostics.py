#!/usr/bin/env python3
"""Create a private, local diagnostic report without starting or querying Riot.

Only logs explicitly named with --log are read. Nothing is uploaded.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys
import uuid

from diagnostic_redaction import redact_text

ROOT = Path(__file__).resolve().parents[1]
MAX_LOG_BYTES = 256 * 1024
MAX_LOGS = 10


def git_revision():
    try:
        return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                       stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def git_modified():
    try:
        status = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'],
                                         stderr=subprocess.DEVNULL, timeout=5)
        return bool(status.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def log_tail(path, limit=MAX_LOG_BYTES):
    # Refuse symlinks, devices and FIFOs; bound every explicit input.
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Log input must be a regular file')
        offset = max(0, info.st_size - limit)
        source.seek(offset)
        data = source.read(limit)
        if offset:
            # Omit a potentially partial line/JSON field at the truncation edge.
            data = data.split(b'\n', 1)[1] if b'\n' in data else b''
        if b'\0' in data:
            raise ValueError('Binary log input is not supported')
        return data.decode('utf-8', errors='replace'), bool(offset)


def create_report(logs, prefix):
    if len(logs) > MAX_LOGS:
        raise ValueError(f'At most {MAX_LOGS} logs may be selected')
    private = (ROOT, prefix)
    entries = []
    for index, path in enumerate(logs, 1):
        text, truncated = log_tail(path)
        entries.append({'label': f'log-{index}', 'truncated': truncated,
                        'text': redact_text(text, private)})
    return {
        'schema': 1,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'source_revision': git_revision(),
        'source_modified': git_modified(),
        'host': {'system': platform.system(), 'kernel': platform.release(),
                 'architecture': platform.machine(), 'python': platform.python_version()},
        'prefix_exists': prefix.is_dir(),
        'logs': entries,
        'notice': 'LOCAL ONLY. Best-effort redaction: manually review before sharing. '
                  'No environment, process arguments, account databases or Riot APIs collected. '
                  'This report cannot determine why Riot applied a penalty.',
    }


def write_private(report, path):
    # Never overwrite or follow a pre-existing report destination.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', action='append', default=[], type=Path,
                        help='Explicit UTF-8 log file (bounded tail; repeat up to 10 times)')
    parser.add_argument('--prefix', type=Path, default=Path.home() / '.darling',
                        help='Prefix path to mask; its contents are not scanned')
    parser.add_argument('--output', type=Path, help='New private report file; never overwritten')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        report = create_report([p.expanduser() for p in args.log], args.prefix.expanduser())
        output = args.output
        if output is None:
            folder = ROOT / 'build/diagnostics'
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            output = folder / f'report-{uuid.uuid4().hex}.json'
        write_private(report, output.expanduser())
    except (OSError, ValueError) as error:
        # Avoid echoing raw input paths or any log content to terminal/CI logs.
        print(f'Diagnostic collection failed ({type(error).__name__}); '
              'check that inputs are regular files and the output is new and writable.', file=sys.stderr)
        return 1
    print('Private report created:', output)
    print('Nothing uploaded. Review the entire file before sharing; redaction is best effort.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
