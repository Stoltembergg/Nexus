#!/usr/bin/env python3
"""M704: submit game_patch request, wait up_to_date, then product-launcher.

Complements tools/riot-league-launch-recipe.sh (whose req() wrapper mis-orders
positional args for long-lived calls). Never prints the auth token.
"""
import glob
import json
import os
import subprocess
import sys
import time

MANIFEST = ("https://lol.secure.dyn.riotcdn.net/channels/public/"
            "releases/BAA127646F53294E.manifest")


def discover():
    for d in glob.glob("/proc/[0-9]*"):
        try:
            raw = open(d + "/cmdline", "rb").read()
        except OSError:
            continue
        text = raw.replace(b"\0", b" ").decode("utf8", "replace")
        if ("--app-port=" in text and "remoting-auth-token" in text
                and "Contents/MacOS/Riot Client" in text):
            port = token = None
            for line in raw.split(b"\0"):
                s = line.decode("utf8", "replace")
                if s.startswith("--app-port="):
                    port = s.split("=", 1)[1]
                elif s.startswith("--remoting-auth-token="):
                    token = s.split("=", 1)[1]
            if port and token:
                return port, token
    raise SystemExit("electron main with app-port not found")


def main():
    port, token = discover()
    base = f"https://127.0.0.1:{port}"
    auth = f"riot:{token}"

    def get(path, timeout=10):
        return subprocess.run(["curl", "-sk", "-m", str(timeout), "-u", auth,
                               base + path], capture_output=True, text=True)

    def state():
        r = get("/patch/v1/installs/league_of_legends.live.game_patch")
        try:
            return json.loads(r.stdout)["status"]["patch"]["state"]
        except Exception:
            return None

    st = state()
    print(f"state@start: {st}", flush=True)
    if st != "up_to_date":
        submit = subprocess.Popen(
            ["curl", "-sk", "-m", "1800", "--http1.1", "-u", auth, "-X", "PUT",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"url": MANIFEST, "headers": {}, "tags": ["en_GB"],
                               "repair": False, "delete_foreign_paths": False,
                               "max_download_speed": 0}),
             base + "/patch/v1/installs/league_of_legends.live.game_patch/requests/patch"],
            stdout=open("/tmp/m704-patch-submit.out", "w"), stderr=subprocess.STDOUT)
        deadline = time.time() + 1500
        while time.time() < deadline:
            time.sleep(15)
            st = state()
            print(f"state: {st} (submit_alive={submit.poll() is None})", flush=True)
            if st == "up_to_date":
                break
        if st != "up_to_date":
            print("giving up: never reached up_to_date", flush=True)
            sys.exit(1)
    t0 = time.time()
    r = subprocess.run(["curl", "-sk", "-m", "1200", "--http1.1", "-u", auth,
                        "-X", "POST", "-H", "Content-Type: application/json",
                        "-d", "{}",
                        base + "/product-launcher/v1/products/league_of_legends/patchlines/live"],
                       capture_output=True, text=True)
    body = r.stdout
    redacted = body
    if token:
        redacted = body.replace(token, "[REDACTED]")
    print(f"launch rc={r.returncode} after {time.time() - t0:.0f}s body={redacted[:300]}",
          flush=True)


main()
