#!/usr/bin/env python3
"""Complete short LC files: re-fetch fully via bundle range requests.
Usage: complete_lc.py <export.json> <lc-dl-dir> <bundles-url> [--workers N]
Only rewrites files whose size != manifest size. Verifies final sizes.
"""
import json, os, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

def fetch_range(url, a, b):
    req = urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        code = r.status
        data = r.read()
    if code not in (200, 206):
        raise RuntimeError(f"HTTP {code} for {url}")
    return data

def complete_one(args):
    f, outdir, bundles_url = args
    out = os.path.join(outdir, f["name"])
    try:
        if os.path.getsize(out) == f["size"]:
            return ("ok", f["name"])
    except OSError:
        pass
    import zstandard
    dctx = zstandard.ZstdDecompressor()
    with open(out + ".part", "wb") as fh:
        for c in f["chunks"]:
            url = f"{bundles_url}/{c['bundle_id']:016X}.bundle"
            comp = fetch_range(url, c["bundle_offset"],
                               c["bundle_offset"] + c["compressed_size"] - 1)
            if len(comp) != c["compressed_size"]:
                raise RuntimeError(f"short chunk {c['chunk_id']:x}")
            data = dctx.decompress(comp, max_output_size=c["uncompressed_size"] * 2)
            if len(data) != c["uncompressed_size"]:
                raise RuntimeError(f"bad decompress {c['chunk_id']:x}")
            fh.write(data)
    os.rename(out + ".part", out)
    actual = os.path.getsize(out)
    if actual != f["size"]:
        return ("MISMATCH", f"{f['name']}: got {actual}, want {f['size']}")
    return ("ok", f["name"])

def main():
    exp, outdir, bundles_url = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == "--workers" else 8
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
    print(f"short/missing: {len(todo)}/{len(files)}, "
          f"bytes to fetch ~{sum(f['size'] for f,_,_ in todo)/1e9:.2f}GB", flush=True)
    ok = bad = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for st, msg in ex.map(complete_one, todo):
            if st == "ok":
                ok += 1
            else:
                bad += 1
                print("FAIL:", msg, flush=True)
    print(f"done ok={ok} bad={bad}")

main()
