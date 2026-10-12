#!/usr/bin/env python3
"""M712: re-POST the product launch until accepted. Never prints the token."""
import glob
import subprocess
import sys
import time


def discover():
    for d in glob.glob("/proc/[0-9]*"):
        try:
            raw = open(d + "/cmdline", "rb").read()
        except OSError:
            continue
        if b"--app-port=" in raw and b"remoting-auth-token" in raw and b"Contents/MacOS/Riot Client\0--" in raw:
            port = token = None
            for line in raw.split(b"\0"):
                s = line.decode("utf8", "replace")
                if s.startswith("--app-port="):
                    port = s.split("=", 1)[1]
                elif s.startswith("--remoting-auth-token="):
                    token = s.split("=", 1)[1]
            if port and token:
                return port, token
    return None, None


# The Riot Client UI can take minutes to appear after the runner starts; wait for it instead of giving up.
deadline = time.monotonic() + 600
port, token = discover()
while not port and time.monotonic() < deadline:
    time.sleep(3)
    port, token = discover()
if not port:
    sys.exit("no UX")
time.sleep(5)  # let its remoting API start listening
launch_start = time.monotonic()
launch_deadline = launch_start + 150
code = None
for attempt in range(1, 151):
    if time.monotonic() >= launch_deadline:
        break
    code = subprocess.run(
        ["curl", "-sk", "-m", "30", "--http1.1", "-u", f"riot:{token}", "-X", "POST",
         "-H", "Content-Type: application/json", "-d", "{}", "-o", "/tmp/m712-launch.json",
         "-w", "%{http_code}",
         f"https://127.0.0.1:{port}/product-launcher/v1/products/league_of_legends/patchlines/live"],
        capture_output=True, text=True).stdout
    print(f"launch attempt {attempt}: {code}, elapsed_s={time.monotonic() - launch_start:.3f}", flush=True)
    if code == "200":
        break
    time.sleep(min(1 if attempt <= 5 else 2, max(0, launch_deadline - time.monotonic())))
else:
    code = None
if code != "200":
    sys.exit("League launch was not accepted within the bounded readiness retries")
