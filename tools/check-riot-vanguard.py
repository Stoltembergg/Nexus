#!/usr/bin/env python3
"""Read Vanguard status from the running League client, without restarting it."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

import requests
import urllib3


def read_status(lockfile):
    try:
        parts = lockfile.read_text().strip().split(':')
        if len(parts) != 5 or parts[4] != 'https':
            raise ValueError
        port = int(parts[2])
        if not 1 <= port <= 65535 or not parts[3]:
            raise ValueError
    except FileNotFoundError:
        raise RuntimeError('League is not running: no lockfile') from None
    except (OSError, ValueError):
        raise RuntimeError('Cannot read a valid League lockfile') from None
    try:
        # This loopback API uses the client's self-signed certificate.
        response = requests.get(
            f'https://127.0.0.1:{port}/lol-vanguard/v1/session',
            auth=('riot', parts[3]), verify=False, timeout=5)
        if response.status_code != 200:
            raise RuntimeError(f'League API returned HTTP {response.status_code}')
        body = response.json()
        state, status = body['state'], body['vanguardStatus']
        if not isinstance(state, str) or not state.isupper() or len(state) > 40:
            raise ValueError
        if not isinstance(status, int) or isinstance(status, bool):
            raise ValueError
        return state, status
    except requests.RequestException:
        raise RuntimeError('Cannot reach the running League API') from None
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('League returned an unexpected Vanguard response') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch', type=float, default=0, metavar='SECONDS',
                        help='require continuous CONNECTED/0 for this duration')
    parser.add_argument('--interval', type=float, default=5,
                        help='seconds between samples (default: 5)')
    parser.add_argument('--lockfile', type=Path, default=Path.home() /
                        '.darling/Applications/League of Legends.app/Contents/LoL/lockfile')
    args = parser.parse_args()
    if not 0 <= args.watch <= 3600 or not 0 < args.interval <= 60:
        parser.error('--watch must be 0..3600 and --interval must be >0..60')
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    started = time.monotonic()
    while True:
        try:
            state, status = read_status(args.lockfile)
        except RuntimeError as error:
            print(f'UNAVAILABLE: {error}', flush=True)
            return 2
        stamp = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
        elapsed = time.monotonic() - started
        print(f'{stamp} +{elapsed:.1f}s state={state} vanguardStatus={status}', flush=True)
        if state != 'CONNECTED' or status != 0:
            print('FAIL: Vanguard is not connected with status 0', flush=True)
            return 1
        if elapsed >= args.watch:
            if args.watch:
                print(f'PASS: CONNECTED/0 at every sample for {elapsed:.1f}s', flush=True)
            else:
                print('Snapshot only; use --watch 120 to check the delayed failure', flush=True)
            return 0
        time.sleep(min(args.interval, args.watch - elapsed))


if __name__ == '__main__':
    raise SystemExit(main())
