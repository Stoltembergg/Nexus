#!/usr/bin/env python3
"""M705: (re)submit game_patch request, wait up_to_date, POST product-launcher.

Runs detached (setsid). Never prints the auth token. Tolerates the blocking
state endpoint (empty response = job in flight). df guard: bails if free space
drops under a floor so the disk never hits zero mid-patch.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import time

MIN = "league_of_legends.live.game_patch"
MANIFEST = ("https://lol.secure.dyn.riotcdn.net/channels/public/"
            "releases/BAA127646F53294E.manifest")
FLOOR_GB = 2.5


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
    return None, None


def state(port, token):
    r = subprocess.run(["curl", "-sk", "-m", "12", "-u", f"riot:{token}",
                        f"https://127.0.0.1:{port}/patch/v1/installs/{MIN}"],
                       capture_output=True, text=True)
    try:
        return json.loads(r.stdout)["status"]["patch"]["state"]
    except Exception:
        return None


def free_gb():
    return shutil.disk_usage("/").free / 1e9


def main():
    port, token = discover()
    if not port:
        sys.exit("no UX")
    print(f"free={free_gb():.1f}G", flush=True)
    st = state(port, token)
    print(f"state@start: {st or 'BLOCKED'}", flush=True)
    if st != "up_to_date":
        body = json.dumps({"url": MANIFEST, "headers": {}, "tags": ["en_GB"],
                           "repair": False, "delete_foreign_paths": False,
                           "max_download_speed": 0})
        submit = subprocess.Popen(
            ["curl", "-sk", "-m", "3000", "--http1.1", "-u", f"riot:{token}",
             "-X", "PUT", "-H", "Content-Type: application/json", "-d", body,
             f"https://127.0.0.1:{port}/patch/v1/installs/{MIN}/requests/patch"],
            stdout=open("/tmp/m705-submit.out", "w"), stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < 2400:
            time.sleep(20)
            st = state(port, token)
            f = free_gb()
            print(f"t={time.time()-t0:4.0f}s state={st or 'BLOCKED'} free={f:.1f}G "
                  f"submit_alive={submit.poll() is None}", flush=True)
            if f < FLOOR_GB:
                print("DISK FLOOR: killing submitter", flush=True)
                submit.kill()
                sys.exit(2)
            if st == "up_to_date":
                break
        if st != "up_to_date":
            sys.exit("never up_to_date")
    if submit_alive_needed := False:
        pass
    print("launching", flush=True)
    r = subprocess.run(["curl", "-sk", "-m", "1500", "--http1.1", "-u", f"riot:{token}",
                        "-X", "POST", "-H", "Content-Type: application/json",
                        "-d", "{}",
                        f"https://127.0.0.1:{port}/product-launcher/v1/products/"
                        "league_of_legends/patchlines/live"],
                       capture_output=True, text=True)
    print(f"launch rc={r.returncode} body={r.stdout[:200]}", flush=True)


main()
