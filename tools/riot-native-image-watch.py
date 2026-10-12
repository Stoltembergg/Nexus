#!/usr/bin/env python3
"""Keep code-image addresses for short-lived native startup processes; no memory reads."""
import argparse
import json
import os
from pathlib import Path
import time

parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=int, default=240)
parser.add_argument("--output", default="/tmp/riot-startup-images.jsonl")
args = parser.parse_args()
seen = {}
deadline = time.monotonic() + args.seconds
with Path(args.output).open("w") as output:
    while time.monotonic() < deadline:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if entry.stat().st_uid != os.getuid() or entry.joinpath("comm").read_text().strip() != "mldr":
                    continue
                lines = entry.joinpath("maps").read_text().splitlines()
                names = {"trustd", "RiotClientServices", "LeagueClient", "LeagueClientUx"}
                image = next((Path(line.split(None, 5)[-1]).name for line in lines
                              if len(line.split(None, 5)) == 6
                              and Path(line.split(None, 5)[-1]).name in names), None)
                if image is None:
                    continue
                namespace_pid = None
                for status in entry.joinpath("status").read_text().splitlines():
                    if status.startswith("NSpid:"):
                        namespace_pid = int(status.split()[-1])
                regions = []
                for line in lines:
                    fields = line.split(None, 5)
                    if len(fields) < 6 or "x" not in fields[1]:
                        continue
                    start, end = [int(x, 16) for x in fields[0].split("-")]
                    regions.append({"start": start, "end": end, "offset": int(fields[2], 16),
                                    "image": Path(fields[5]).name})
                if seen.get(entry.name) != regions:
                    seen[entry.name] = regions
                    output.write(json.dumps({"pid": int(entry.name), "namespacePid": namespace_pid, "primary": image, "regions": regions}) + "\n")
                    output.flush()
            except OSError:
                pass
        time.sleep(.1)
print(json.dumps({"observedProcesses": len(seen)}))
