#!/usr/bin/env python3
"""Validate exported game shaders offline and save per-file diagnostics."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--scalar-block-layout', action='store_true')
    args = parser.parse_args()
    flags = ['--target-env', 'vulkan1.3', '--allow-localsizeid']
    if args.scalar_block_layout:
        flags.append('--scalar-block-layout')

    def validate(path):
        result = subprocess.run(['spirv-val', *flags, str(path)],
                                capture_output=True, text=True, timeout=30)
        return {'file': path.name, 'passed': result.returncode == 0,
                'diagnostic': result.stderr.strip()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(validate, sorted(args.directory.glob('*.spv'))))
    passed = sum(item['passed'] for item in results)
    args.report.write_text(json.dumps({'passed': passed, 'failed': len(results) - passed,
                                      'validator_flags': flags, 'results': results}, indent=2) + '\n')
    print(f'Validation: {passed} passed, {len(results) - passed} failed')
    reasons = Counter(item['diagnostic'].split(': ', 2)[-1].splitlines()[0]
                      for item in results if not item['passed'])
    for reason, count in reasons.most_common(10):
        print(f'{count}: {reason}')
    return 0 if results and passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
