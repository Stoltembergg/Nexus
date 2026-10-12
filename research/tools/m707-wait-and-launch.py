#!/usr/bin/env python3
"""M707: wait for game_patch verification to finish; then context+attempts+launch.

Never submits a patch request (the last submit was a stale 10.10 manifest and
caused a downgrade job). If the install comes back NOT up_to_date against the
current live target, report and stop for a human/agent decision.
"""
import glob
import json
import subprocess
import time

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


def get(path, port, token, tmo=15):
    return subprocess.run(["curl", "-sk", "-m", str(tmo), "-u", f"riot:{token}",
                           f"https://127.0.0.1:{port}{path}"],
                          capture_output=True, text=True)


def main():
    t0 = time.time()
    port = token = None
    st = None
    while time.time() - t0 < 1500:
        port, token = discover()
        if not port:
            print("no UX yet", flush=True)
            time.sleep(10)
            continue
        r = get("/patch/v1/installs/league_of_legends.live.game_patch", port, token)
        try:
            s = json.loads(r.stdout)["status"]["patch"]
            st = s.get("state")
            print(f"t={time.time()-t0:4.0f}s state={st} current={s.get('currentVersion')} "
                  f"target={s.get('targetVersion')}", flush=True)
        except Exception:
            print(f"t={time.time()-t0:4.0f}s BLOCKED", flush=True)
            st = None
        if st == "up_to_date":
            break
        if st in ("out_of_date", "corrupted"):
            print("STOP: needs decision (no blind submit)", flush=True)
            return 3
        time.sleep(15)
    if st != "up_to_date":
        print("timeout waiting for state", flush=True)
        return 1
    print("context put :", get("/player-session-lifecycle/v1/product-context", port, token, 15).returncode, flush=True)
    # proper PUT needs -X PUT + body
    subprocess.run(["curl", "-sk", "-m", "20", "--http1.1", "-u", f"riot:{token}", "-X", "PUT",
                    "-H", "Content-Type: application/json",
                    "-d", '{"productContext":{"productId":"league_of_legends","patchlineId":"live"}}',
                    "-o", "/dev/null", "-w", "context=%{http_code}\n",
                    f"https://127.0.0.1:{port}/player-session-lifecycle/v1/product-context"],
                   check=False)
    subprocess.run(["curl", "-sk", "-m", "20", "--http1.1", "-u", f"riot:{token}", "-X", "POST",
                    "-H", "Content-Type: application/json", "-d", "0",
                    "-o", "/dev/null", "-w", "attempts=%{http_code}\n",
                    f"https://127.0.0.1:{port}/data-store/v1/install-settings/riot-client-app-command/upgrade_attempts"],
                   check=False)
    print("launching", flush=True)
    r = subprocess.run(["curl", "-sk", "-m", "1500", "--http1.1", "-u", f"riot:{token}",
                        "-X", "POST", "-H", "Content-Type: application/json", "-d", "{}",
                        f"https://127.0.0.1:{port}/product-launcher/v1/products/"
                        "league_of_legends/patchlines/live"],
                       capture_output=True, text=True)
    print(f"launch rc={r.returncode} body={r.stdout[:220]}", flush=True)
    return 0


raise SystemExit(main())
