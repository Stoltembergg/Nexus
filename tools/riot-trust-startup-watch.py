#!/usr/bin/env python3
"""Capture code-only faults across the transient trustd startup instances."""
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
seen = []
deadline = time.monotonic() + 600
Path("/tmp/trustd-startup-faults.jsonl").write_text("")
while time.monotonic() < deadline and len(seen) < 10:
    command = [sys.executable, str(root / "riot-league-crash-watch.py"), "--image", "trustd", "--timeout", "60"]
    for pid in seen:
        command.extend(["--exclude-pid", str(pid)])
    result = subprocess.run(command, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("observed"):
            seen.append(record["pid"])
        print(json.dumps(record), flush=True)
print(json.dumps({"watchedInstances":len(seen)}))
