#!/usr/bin/env python3
"""Manage Darling's local code-signing trust store.

This is intentionally a Darling-local store, not Apple's trust cache. Entries
map a 20-byte cdhash to a small flags word and are signed with an Ed25519 key
created next to the store. The store must never be presented as Apple-issued.
"""
import argparse
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

MAGIC = 0x44544331  # "DTC1"
VERSION = 1
ISSUER = b"darling-local"
ISSUER_LEN = 32
HEADER = struct.Struct("<IIQ32sI")
ENTRY = struct.Struct("<20sI")
SIG_LEN = struct.Struct("<I")
DEFAULT_FLAGS = 1


def fail(message):
    raise SystemExit(f"dc-trustcache: {message}")


def key_paths(store, key=None, pub=None):
    return (store,
            Path(key) if key else store.with_suffix(store.suffix + ".key"),
            Path(pub) if pub else store.with_suffix(store.suffix + ".pub"))


def run(args):
    try:
        return subprocess.run(args, check=True, capture_output=True)
    except FileNotFoundError:
        fail("openssl not found")
    except subprocess.CalledProcessError as error:
        fail(error.stderr.decode(errors="replace").strip() or "openssl failed")


def ensure_key(store, key, pub):
    key.parent.mkdir(parents=True, exist_ok=True)
    if not key.exists():
        run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)])
        os.chmod(key, 0o600)
    if not pub.exists():
        run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(pub)])
        os.chmod(pub, 0o644)
    if not key.is_file() or not pub.is_file():
        fail(f"cannot create trust-store key pair {key} / {pub}")


def sign_payload(payload, key):
    with tempfile.NamedTemporaryFile(prefix="dc-trustcache-", delete=False) as tmp:
        tmp.write(payload)
        message = Path(tmp.name)
    try:
        signature = run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key),
                         "-in", str(message)]).stdout
    finally:
        message.unlink(missing_ok=True)
    if len(signature) != 64:
        fail("unexpected Ed25519 signature length")
    return signature


def verify_payload(payload, signature, pub):
    with tempfile.NamedTemporaryFile(prefix="dc-trustcache-", delete=False) as tmp:
        tmp.write(payload)
        message = Path(tmp.name)
    with tempfile.NamedTemporaryFile(prefix="dc-trustcache-", delete=False) as tmp:
        tmp.write(signature)
        sigfile = Path(tmp.name)
    try:
        run(["openssl", "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(pub),
             "-in", str(message), "-sigfile", str(sigfile)])
        return True
    except SystemExit:
        return False
    finally:
        message.unlink(missing_ok=True)
        sigfile.unlink(missing_ok=True)


def read_store(store, pub):
    try:
        data = store.read_bytes()
    except FileNotFoundError:
        return None
    if len(data) < HEADER.size + SIG_LEN.size:
        fail("trust store is truncated")
    header = HEADER.unpack_from(data)
    magic, version, generation, issuer, count = header
    if magic != MAGIC or version != VERSION:
        fail("bad trust-store magic or version")
    if issuer.rstrip(b"\0") != ISSUER:
        fail("trust store is not issued by darling-local")
    entries_end = HEADER.size + count * ENTRY.size
    if entries_end + SIG_LEN.size > len(data):
        fail("trust-store entry table runs past the file")
    entries = {}
    for index in range(count):
        cdhash, flags = ENTRY.unpack_from(data, HEADER.size + index * ENTRY.size)
        entries[cdhash] = flags
    siglen = SIG_LEN.unpack_from(data, entries_end)[0]
    if siglen != 64 or entries_end + SIG_LEN.size + siglen != len(data):
        fail("bad trust-store signature length")
    payload = data[:entries_end]
    signature = data[entries_end + SIG_LEN.size:]
    if not verify_payload(payload, signature, pub):
        fail("trust-store signature does not verify")
    return generation, entries


def write_store(store, key, pub, generation, entries):
    ensure_key(store, key, pub)
    table = b"".join(ENTRY.pack(cdhash, flags) for cdhash, flags in sorted(entries.items()))
    payload = HEADER.pack(MAGIC, VERSION, generation, ISSUER.ljust(ISSUER_LEN, b"\0"),
                          len(entries)) + table
    signature = sign_payload(payload, key)
    data = payload + SIG_LEN.pack(len(signature)) + signature
    store.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".dc-trustcache-", dir=store.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, store)
    finally:
        Path(temporary).unlink(missing_ok=True)


def require_privilege():
    if os.geteuid() != 0:
        fail("adding/removing trust entries requires root (or an administrator)")


def parse_cdhash(value):
    value = value.replace(":", "").strip()
    if len(value) != 40:
        fail("cdhash must be 40 hexadecimal characters")
    try:
        return bytes.fromhex(value)
    except ValueError:
        fail("cdhash must be hexadecimal")


def command_verify(args):
    store, key, pub = key_paths(args.store, args.key, args.pub)
    result = read_store(store, pub)
    if result is None:
        fail(f"trust store not found: {store}")
    generation, entries = result
    print(f"generation={generation} entries={len(entries)} issuer=darling-local")
    return 0


def command_list(args):
    store, key, pub = key_paths(args.store, args.key, args.pub)
    result = read_store(store, pub)
    if result is None:
        fail(f"trust store not found: {store}")
    generation, entries = result
    print(f"generation={generation} entries={len(entries)} issuer=darling-local")
    for cdhash, flags in sorted(entries.items()):
        print(f"{cdhash.hex()} flags=0x{flags:08x}")
    return 0


def command_add(args):
    require_privilege()
    store, key, pub = key_paths(args.store, args.key, args.pub)
    result = read_store(store, pub) if store.exists() else None
    generation = 1 if result is None else result[0] + 1
    entries = {} if result is None else dict(result[1])
    cdhash = parse_cdhash(args.cdhash)
    entries[cdhash] = args.flags
    write_store(store, key, pub, generation, entries)
    print(f"added {cdhash.hex()} flags=0x{args.flags:08x} generation={generation}")
    return 0


def command_remove(args):
    require_privilege()
    store, key, pub = key_paths(args.store, args.key, args.pub)
    result = read_store(store, pub)
    if result is None:
        fail(f"trust store not found: {store}")
    generation, entries = result
    cdhash = parse_cdhash(args.cdhash)
    if cdhash not in entries:
        fail(f"entry not found: {cdhash.hex()}")
    del entries[cdhash]
    write_store(store, key, pub, generation + 1, entries)
    print(f"removed {cdhash.hex()} generation={generation + 1}")
    return 0


def command_init(args):
    require_privilege()
    store, key, pub = key_paths(args.store, args.key, args.pub)
    if store.exists():
        fail(f"trust store already exists: {store}")
    write_store(store, key, pub, 1, {})
    print(f"initialized {store} (issuer=darling-local)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, function in (("init", command_init), ("verify", command_verify), ("list", command_list)):
        cmd = sub.add_parser(name)
        cmd.add_argument("store", type=Path)
        cmd.add_argument("--key", type=Path)
        cmd.add_argument("--pub", type=Path)
        cmd.set_defaults(function=function)

    add = sub.add_parser("add")
    add.add_argument("store", type=Path)
    add.add_argument("cdhash")
    add.add_argument("--flags", type=lambda value: int(value, 0), default=DEFAULT_FLAGS)
    add.add_argument("--key", type=Path)
    add.add_argument("--pub", type=Path)
    add.set_defaults(function=command_add)

    remove = sub.add_parser("remove")
    remove.add_argument("store", type=Path)
    remove.add_argument("cdhash")
    remove.add_argument("--key", type=Path)
    remove.add_argument("--pub", type=Path)
    remove.set_defaults(function=command_remove)

    args = parser.parse_args(argv)
    return args.function(args)


if __name__ == "__main__":
    sys.exit(main())
