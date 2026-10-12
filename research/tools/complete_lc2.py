#!/usr/bin/env python3
"""Complete short files by appending missing tail chunks.
Theory: downloader stops mid-file; disk content = exact prefix of chunks.
Self-check: disk size MUST align to a chunk boundary, else full re-fetch.
Usage: complete_lc2.py <export.json> <dir> <bundles-url> [--workers N]
"""
import json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

def fetch_range(url, a, b, retries=6):
    ua = "RiotClient/138.0.0.4786 (Macintosh; Intel Mac OS X 10_15_7)"
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": ua, "Range": f"bytes={a}-{b}"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if r.status in (200, 206) and len(data) == b - a + 1:
                return data
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed {url} [{a}-{b}]")

def complete_one(args):
    f, outdir, bundles_url = args
    out = os.path.join(outdir, f["name"])
    try:
        disk = os.path.getsize(out)
    except OSError:
        disk = -1
    want = f["size"]
    if disk == want:
        return ("ok", None)
    import zstandard
    dctx = zstandard.ZstdDecompressor()
    # map chunks to file offsets
    off = 0
    start_idx = None
    for i, c in enumerate(f["chunks"]):
        u = c["uncompressed_size"]
        if off == disk:
            start_idx = i
            break
        if off < disk < off + u:
            start_idx = None  # mid-chunk gap: not a clean prefix
            break
        off += u
    mode = "append" if start_idx is not None else "full"
    if mode == "full":
        start_idx = 0
        part = out + ".part"
        fh = open(part, "wb")
    else:
        fh = open(out, "r+b")
        fh.seek(disk)
    got = disk if mode == "append" else 0
    with fh:
        for c in f["chunks"][start_idx:]:
            url = f"{bundles_url}/{c['bundle_id']:016X}.bundle"
            comp = fetch_range(url, c["bundle_offset"],
                               c["bundle_offset"] + c["compressed_size"] - 1)
            data = dctx.decompress(comp, max_output_size=c["uncompressed_size"] * 2)
            if len(data) != c["uncompressed_size"]:
                return ("FAIL", f"{f['name']}: bad chunk {c['chunk_id']:x}")
            fh.write(data)
            got += len(data)
    if mode == "full":
        os.rename(out + ".part", out)
    actual = os.path.getsize(out)
    if actual != want:
        return ("FAIL", f"{f['name']}: got {actual}, want {want}")
    return ("ok", f"{f['name']} [{mode}]")

def main():
    exp, outdir, bundles_url = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = 4
    if "--workers" in sys.argv:
        workers = int(sys.argv[sys.argv.index("--workers") + 1])
    d = json.load(open(exp))
    files = d["files"] if isinstance(d, dict) else d
    todo = []
    for f in files:
        out = os.path.join(outdir, f["name"])
        try:
            ok = os.path.getsize(out) == f["size"]
        except OSError:
            ok = False
        if not ok:
            todo.append((f, outdir, bundles_url))
    print(f"short/missing: {len(todo)}/{len(files)}", flush=True)
    ok = bad = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_guarded, t): t for t in todo}
        import concurrent.futures as cf
        for fut in cf.as_completed(futs):
            st, msg = fut.result()
            if st == "ok":
                ok += 1
                if msg:
                    print("fixed:", msg, flush=True)
            else:
                bad += 1
                print("FAIL:", msg, flush=True)
    print(f"done ok={ok} bad={bad}")


def _guarded(t):
    try:
        return complete_one(t)
    except Exception as e:
        return ("FAIL", f"{t[0]['name']}: {e}")

main()
