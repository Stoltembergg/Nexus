#!/usr/bin/env python3
# darling-lol M58f: mine the B1 trap core (SIGTRAP, coredumpctl pid 106956) for
# the failing CHECK's file/line. The core has guest stacks but not the
# Framework's text/data pages, so: (1) dump the trap-thread stack around the
# rbp chain, (2) collect qwords in the Framework mapping ranges, (3) convert to
# static vmaddr, (4) read the string from the on-disk Framework binary.
# If /tmp/opencode/m58f/b1.core is gone, re-dump first:
#   coredumpctl dump 106956 --output=/tmp/opencode/m58f/b1.core
# Mapping bases below are from THAT core's NT_FILE (gdb: info proc mappings);
# re-check them if you mine a different trap.
import struct, sys

CORE = '/tmp/opencode/m58f/b1.core'
FW   = '@DPREFIX@/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/Frameworks/Electron Framework.framework/Versions/A/Electron Framework'
fw = open(FW, 'rb').read()

core = open(CORE, 'rb').read()

# --- parse ELF program headers ---
assert core[:4] == b'\x7fELF'
e_phoff, = struct.unpack_from('<Q', core, 0x20)
e_phentsize, e_phnum = struct.unpack_from('<HH', core, 0x36)
loads, nt_file = [], []
ph = e_phoff
for _ in range(e_phnum):
    p_type, p_flags = struct.unpack_from('<II', core, ph)
    if p_type == 1:  # PT_LOAD
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from('<QQQQQ', core, ph + 8)
        loads.append((p_vaddr, p_vaddr + p_filesz, p_offset))
    ph += e_phentsize

def core_read(addr, n):
    for lo, hi, off in loads:
        if lo <= addr and addr + n <= hi:
            return core[off + (addr - lo): off + (addr - lo) + n]
    return None

# --- Framework mappings (from gdb info proc mappings) ---
# map1: 0x7fee0e284000..0x7fee16a66000 fileoff 0x4000 ; static = rt-start+0x4000
# map2: 0x7fee16a66000..0x7fee170a2000 fileoff 0x87e6000 ; static = rt-start+0x87e6000
# map3 (__DATA): 0x7fee171b4000..0x7fee17539000 ; static = rt-start+0x8e22000
FW_MAPS = (
    (0x7fee0e284000, 0x7fee16a66000, 0x4000),
    (0x7fee16a66000, 0x7fee170a2000, 0x87e6000),
    (0x7fee171b4000, 0x7fee17539000, 0x8e22000),
)
def fw_static(rt):
    for lo, hi, base in FW_MAPS:
        if lo <= rt < hi:
            return (rt - lo) + base
    return None

def fw_string(va, maxlen=96):
    if va < 0x4000 or va + 1 >= len(fw):
        return None
    end = fw.find(b'\x00', va, va + maxlen)
    if end < 0:
        end = va + maxlen
    raw = fw[va:end]
    if not raw:
        return None
    try:
        s = raw.decode('ascii')
    except UnicodeDecodeError:
        return None
    if len(s) >= 3 and all(32 <= ord(c) < 127 or c in '\t' for c in s):
        return s
    return None

# --- trap thread stack ---
rbp0 = 0x7fedd07f6980
lo, hi = 0x7fedd07f6000, 0x7fedd07f8000   # generous window around the frames
stack = core_read(lo, hi - lo)
assert stack, "stack pages not in core"

hits = {}
for off in range(0, len(stack) - 8, 8):
    q, = struct.unpack_from('<Q', stack, off)
    va = fw_static(q)
    if va is None:
        continue
    s = fw_string(va)
    if s:
        hits[lo + off] = (va, s)

print(f"string-pointer hits in stack window 0x{lo:x}-0x{hi:x}: {len(hits)}")
frames = {
    'rbp0': 0x7fedd07f6980, 'rbp1': 0x7fedd07f69d0, 'rbp2': 0x7fedd07f6b90,
    'rbp3': 0x7fedd07f6c30, 'rbp4': 0x7fedd07f6d70, 'rbp5': 0x7fedd07f6ea0,
}
rsp0 = 0x7fedd07f68c0
for addr in sorted(hits):
    va, s = hits[addr]
    tag = ''
    for name, fa in frames.items():
        if fa <= addr < fa + 0x40:
            tag = f' [{name}+{addr-fa:#x}]'
            break
    if addr < rbp0:
        tag += ' [below rbp0: trap/callee frame]'
    print(f"  rt 0x{addr:x} -> fw+{va:#x}: {s!r}{tag}")

print("\n--- raw stack 0x7fedd07f68b0..0x7fedd07f6a40 (trap + first frames) ---")
for a in range(0x7fedd07f68b0, 0x7fedd07f6a40, 8):
    v, = struct.unpack_from('<Q', core_read(a, 8), 0)
    ann = ''
    va = fw_static(v)
    if va is not None:
        s = fw_string(va)
        ann = f' -> fw+{va:#x}' + (f' {s!r}' if s else '')
    elif 0 < v < 0x100000:
        ann = f' (int {v})'
    print(f"  0x{a:x}: 0x{v:016x}{ann}")
