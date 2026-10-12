#!/usr/bin/env python3
"""M708: context -> attempts -> submit live manifest (8841) -> wait -> launch.

HTTP/1.1 everywhere (Riot's local remoting API rejects curl's default h2;
that made all earlier "BLOCKED" readings false). Never prints the token.
"""
import glob
import json
import shutil
import subprocess
import sys
import time

import os

# release id of the live game build; pass RELEASE=<id> when Riot publishes a new one
RELEASE = os.environ.get("RELEASE", "8841D91E6665286D")
MANIFEST = ("https://lol.secure.dyn.riotcdn.net/channels/public/"
            f"releases/{RELEASE}.manifest")
MIN = "league_of_legends.live.game_patch"
FLOOR_GB = 2.5


def discover():
    for d in glob.glob("/proc/[0-9]*"):
        try:
            raw = open(d + "/cmdline", "rb").read()
        except OSError:
            continue
        text = raw.replace(b"\0", b" ").decode("utf8", "replace")
        if ("--app-port=" in text and "remoting-auth-token" in text
                and "Contents/MacOS/Riot Client --" in text):
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


def main():
    port = token = None
    for _ in range(60):
        port, token = discover()
        if port:
            break
        time.sleep(5)
    if not port:
        sys.exit("no UX")
    auth = f"riot:{token}"
    B = f"https://127.0.0.1:{port}"

    def call(method, path, data=None, tmo=20):
        a = ["curl", "-sk", "-m", str(tmo), "--http1.1", "-u", auth, "-X", method]
        if data is not None:
            a += ["-H", "Content-Type: application/json", "-d", data]
        a += ["-o", "/tmp/m708-last.json", "-w", "%{http_code}", B + path]
        return subprocess.run(a, capture_output=True, text=True).stdout

    print("context:", call("PUT", "/player-session-lifecycle/v1/product-context",
          '{"productContext":{"productId":"league_of_legends","patchlineId":"live"}}'), flush=True)
    print("attempts:", call("POST",
          "/data-store/v1/install-settings/riot-client-app-command/upgrade_attempts", "0"), flush=True)

    def state():
        subprocess.run(["curl", "-sk", "-m", "15", "--http1.1", "-u", auth,
                        B + f"/patch/v1/installs/{MIN}", "-o", "/tmp/m708-state.json"],
                       capture_output=True)
        try:
            s = json.load(open("/tmp/m708-state.json"))["status"]["patch"]
            return s.get("state"), s.get("progress", {})
        except Exception:
            return None, {}

    st, prog = state()
    print(f"state@start: {st} {prog}", flush=True)
    if st != "up_to_date":
        body = json.dumps({"url": MANIFEST, "headers": {}, "tags": ["en_GB"],
                           "repair": False, "delete_foreign_paths": False,
                           "max_download_speed": 0})
        print("submit:", call("PUT", f"/patch/v1/installs/{MIN}/requests/patch",
                              body, 300), flush=True)
    t0 = time.time()
    while time.time() - t0 < 3000:
        time.sleep(20)
        st, prog = state()
        f = shutil.disk_usage("/").free / 1e9
        print(f"t={time.time()-t0:4.0f}s state={st} phase={prog.get('phase')} "
              f"progress={prog.get('progress')} free={f:.1f}G", flush=True)
        if f < FLOOR_GB:
            sys.exit("DISK FLOOR")
        if st == "up_to_date":
            break
        if st in ("corrupted",):
            sys.exit(f"unrecoverable state {st}")
    if st != "up_to_date":
        sys.exit("never up_to_date")
    print("launch:", call("POST",
          "/product-launcher/v1/products/league_of_legends/patchlines/live", "{}", 1500), flush=True)


main()
