#!/usr/bin/env python3
"""Decode fixed-size records emitted by m57-ipcz-trace.c."""
import argparse
import collections
import struct

HEADER = struct.Struct("<IIQQQ128s")

# Markers whose value is a packed little-endian string chunk (8 bytes each),
# emitted by gfx::HasExtension so Chromium's queried extension name survives.
GFX_NAME_CHUNKS = 6
GFX_NAME_PREFIX = "GFX_HAS_NAME_"

# EGL context-attribute names for the array captured at eglCreateContextFn.
EGL_ATTR_NAMES = {
    0x3038: "EGL_NONE",
    0x3098: "EGL_CONTEXT_CLIENT_VERSION/MAJOR_VERSION",
    0x30FB: "EGL_CONTEXT_MINOR_VERSION",
    0x30FD: "EGL_CONTEXT_OPENGL_PROFILE_MASK",
    0x30BF: "EGL_CONTEXT_OPENGL_ROBUST_ACCESS_EXT",
    0x3138: "EGL_CONTEXT_OPENGL_RESET_NOTIFICATION_STRATEGY_EXT",
    0x3100: "EGL_CONTEXT_PRIORITY_LEVEL_IMG",
    0x31B0: "EGL_CONTEXT_OPENGL_DEBUG",
    0x31B1: "EGL_CONTEXT_OPENGL_FORWARD_COMPATIBLE",
    0x31B2: "EGL_CONTEXT_OPENGL_ROBUST_ACCESS",
    0x31B3: "EGL_CONTEXT_OPENGL_NO_ERROR_KHR",
    0x31BD: "EGL_CONTEXT_OPENGL_RESET_NOTIFICATION_STRATEGY",
    0x31BE: "EGL_NO_RESET_NOTIFICATION(_EXT)",
    0x31BF: "EGL_LOSE_CONTEXT_ON_RESET(_EXT)",
    0x32C0: "EGL_PROTECTED_CONTENT_EXT",
    0x33AC: "EGL_CONTEXT_WEBGL_COMPATIBILITY_ANGLE",
    0x33AD: "EGL_CONTEXT_BIND_GENERATES_RESOURCE_CHROMIUM",
    0x33AF: "EGL_DISPLAY_TEXTURE_SHARE_GROUP_ANGLE",
    0x3452: "EGL_CONTEXT_CLIENT_ARRAYS_ENABLED_ANGLE",
    0x3453: "EGL_ROBUST_RESOURCE_INITIALIZATION_ANGLE",
    0x3459: "EGL_EXTENSIONS_ENABLED_ANGLE",
    0x3481: "EGL_CONTEXT_VIRTUALIZATION_GROUP_ANGLE",
}


def marker_text(prefix):
    return prefix.split(bytes([0]), 1)[0].decode(errors="replace")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="/tmp/m57-ipcz.bin")
    parser.add_argument("--all", action="store_true", help="show every record")
    args = parser.parse_args()
    data = open(args.path, "rb").read()
    if len(data) % HEADER.size:
        raise SystemExit(f"truncated trace: {len(data)} bytes is not a multiple of {HEADER.size}")

    counts = collections.Counter()
    records = []
    ordinal_hits = []
    establish_ordinal = struct.pack("<I", 0x553B54CD)

    # Chromium-side EGL/ANGLE view (M57s/M57t).
    gfx_pending = {}          # pid -> {"len": int, "chunks": {i: bytes}}
    img_pending = {}          # pid -> {"len": int, "chunks": {i: bytes}}
    egl_events = []           # (pid, seq, kind, label, value)

    for offset in range(0, len(data), HEADER.size):
        magic, pid, seq, size, handles, raw = HEADER.unpack_from(data, offset)
        if magic != 0x5A435049:
            raise SystemExit(f"bad magic at offset {offset:#x}: {magic:#x}")
        prefix = raw[: min(size, len(raw))]
        records.append((pid, seq, size, handles, prefix))
        if size == 0xFFFFFFFFFFFFFFFF:
            name = marker_text(prefix)
            if name == "GFX_HAS_NAME_LEN":
                gfx_pending.setdefault(pid, {})["len"] = handles
            elif name.startswith(GFX_NAME_PREFIX):
                idx = int(name.rsplit("_", 1)[1])
                gfx_pending.setdefault(pid, {}).setdefault("chunks", {})[idx] = struct.pack(
                    "<Q", handles & 0xFFFFFFFFFFFFFFFF
                )
            elif name == "GFX_HAS_RESULT":
                state = gfx_pending.pop(pid, {})
                blob = b"".join(
                    state.get("chunks", {}).get(i, b"") for i in range(GFX_NAME_CHUNKS)
                )
                ext = blob[: state.get("len", 0)].decode(errors="replace")
                egl_events.append((pid, seq, "query", ext, handles))
            elif name.startswith("GL_CTX_"):
                egl_events.append((pid, seq, "ctx", name, handles))
            elif name.startswith("EGL_EXT_"):
                egl_events.append((pid, seq, "ext", name, handles))
            elif (name.startswith("EGL_CREATE_") or name.startswith("EGL_CTX_ATTR")
                  or name.startswith("EGL_MAKE_CURRENT_") or name.startswith("EGL_MC_")
                  or name == "SET_CURRENT_CONTEXT" or name == "SCC_THREAD"
                  or name == "SET_CTX_HELPER" or name == "SCH_THREAD"
                  or name == "THREAD_MAKE_CURRENT" or name == "TMC_CONTEXT"
                  or name == "TMC_THREAD" or name == "TMC_RESULT"
                  or name == "SCC_LIBEGL_DISPATCH" or name.startswith("SCC_HOOK_")):
                egl_events.append((pid, seq, "create", name, handles))
            elif name in ("GLA_GI_FN_IMG_LEN", "GLA_GI_FN_NEAR_LEN"):
                img_pending[pid] = {"len": handles, "chunks": {}, "prefix": name[:-4]}
            elif name in ("GLA_GI_FN_IMG_END", "GLA_GI_FN_NEAR_END"):
                state = img_pending.pop(pid, {})
                blob = b"".join(
                    state.get("chunks", {}).get(i, b"") for i in range(16)
                )
                img = blob[: state.get("len", 0)].decode(errors="replace")
                egl_events.append(
                    (pid, seq, "gla", state.get("prefix", "GLA_GI_FN_IMG") + "_PATH", img)
                )
            elif ((name.startswith("GLA_GI_FN_IMG_") or name.startswith("GLA_GI_FN_NEAR_"))
                  and name[-1].isdigit()):
                idx = int(name.rsplit("_", 1)[1])
                img_pending.setdefault(pid, {"len": 0, "chunks": {}})[
                    "chunks"
                ][idx] = struct.pack("<Q", handles & 0xFFFFFFFFFFFFFFFF)
            elif name.startswith("GLA_GI_"):
                egl_events.append((pid, seq, "gla", name, handles))
            else:
                print(f"marker={name} pid={pid} seq={seq} value={handles}")
            continue
        key = prefix[:16].hex(" ")
        counts[(pid, size, handles, key)] += 1
        at = prefix.find(establish_ordinal)
        if at >= 0:
            ordinal_hits.append((pid, seq, size, handles, at))

    print(f"records={len(records)} pids={sorted({r[0] for r in records})}")
    for pid, seq, size, handles, at in ordinal_hits:
        print(
            f"EstablishGpuChannel ordinal=0x553b54cd pid={pid} seq={seq} "
            f"bytes={size} handles={handles} offset={at}"
        )

    if egl_events:
        print()
        print("=== Chromium EGL/ANGLE extension + attribute view (M57s/M57t) ===")
        for pid, seq, kind, label, value in egl_events:
            if kind == "gla":
                if label.endswith("_PATH"):
                    print(f"  [pid {pid} seq {seq}] {label} = {value!r}")
                elif (label.startswith("GLA_GI_REAL_") or label == "GLA_GI_ANGLE_CTX"
                      or label == "GLA_GI_THREAD"):
                    print(f"  [pid {pid} seq {seq}] {label} = {value:#x}")
                else:
                    print(f"  [pid {pid} seq {seq}] {label} = {value & 0xFFFFFFFF}")
            elif kind == "query":
                print(f"  [pid {pid} seq {seq}] extension {label!r} present={value & 0xFF}")
            elif label == "GL_CTX_A14" or label in ("GL_CTX_INIT_RESULT", "GFX_HAS_RESULT"):
                print(f"  [pid {pid} seq {seq}] {label} = {value} ({value & 0xFF})")
            elif label.startswith("EGL_EXT_DUMP_"):
                b = struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)
                flags = " ".join(f"{x:02x}" for x in b)
                print(f"  [pid {pid} seq {seq}] {label} = {value:#018x}  bytes {flags}")
            elif label.startswith("EGL_CTX_ATTR_") and label != "EGL_CTX_ATTR_COUNT":
                attr = value & 0xFFFFFFFF
                val = (value >> 32) & 0xFFFFFFFF
                an = EGL_ATTR_NAMES.get(attr)
                suffix = f"  # {an}" if an else ""
                print(f"  [pid {pid} seq {seq}]   attr 0x{attr:04x} = {val}{suffix}")
            elif label == "EGL_CREATE_RESULT":
                state = "OK" if value else "NULL (failed)"
                print(f"  [pid {pid} seq {seq}] {label} = {value:#x}  {state}")
            else:
                print(f"  [pid {pid} seq {seq}] {label} = {value:#x}")

    if args.all:
        for pid, seq, size, handles, raw in records:
            print(f"pid={pid} seq={seq} bytes={size} handles={handles} data={raw.hex(' ')}")
    else:
        for (pid, size, handles, prefix), count in counts.most_common():
            print(f"count={count} pid={pid} bytes={size} handles={handles} prefix={prefix}")


if __name__ == "__main__":
    main()
