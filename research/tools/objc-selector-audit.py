#!/usr/bin/env python3
"""Compare the Objective-C selectors a set of Mach-O images send against the methods
Darling's frameworks implement (roots are colon separated, e.g. the system install plus the
RuntimeFrameworks/RuntimeLibraries overrides). Name-level only: it cannot tell whether an
implemented method behaves correctly.

usage: objc-selector-audit.py <root>[:<root>...] <report-dir> <image>...
"""
import mmap
import os
import struct
import sys

FAT_MAGIC = 0xCAFEBABE
MH_MAGIC_64 = 0xFEEDFACF
CPU_X86_64 = 0x01000007


class Image:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        self.base = 0
        magic = struct.unpack_from('>I', self.m, 0)[0]
        if magic == FAT_MAGIC:
            count = struct.unpack_from('>I', self.m, 4)[0]
            found = None
            for i in range(count):
                cputype, _, offset, size, _ = struct.unpack_from('>iiIII', self.m, 8 + 20 * i)
                if cputype & 0xFFFFFFFF == CPU_X86_64:
                    found = offset
            if found is None:
                raise ValueError('no x86_64 slice')
            self.base = found
        if struct.unpack_from('<I', self.m, self.base)[0] != MH_MAGIC_64:
            raise ValueError('not a 64-bit Mach-O')
        self.segments = []   # (vmaddr, vmsize, fileoff, filesize)
        self.sections = {}   # name -> (addr, size, offset)
        ncmds = struct.unpack_from('<I', self.m, self.base + 16)[0]
        off = self.base + 32
        for _ in range(ncmds):
            cmd, size = struct.unpack_from('<II', self.m, off)
            if cmd == 0x19:  # LC_SEGMENT_64
                segname = self.m[off + 8:off + 24].split(b'\0')[0]
                vmaddr, vmsize, fileoff, filesize, _, _, nsects, _ = struct.unpack_from('<QQQQiiII', self.m, off + 24)
                self.segments.append((vmaddr, vmsize, fileoff, filesize))
                so = off + 72
                for _ in range(nsects):
                    sectname = self.m[so:so + 16].split(b'\0')[0].decode()
                    addr, ssize, soffset = struct.unpack_from('<QQI', self.m, so + 32)
                    self.sections[sectname] = (addr, ssize, soffset)
                    so += 80
            off += size

    def offset(self, vmaddr):
        for vmaddr0, vmsize, fileoff, filesize in self.segments:
            if vmaddr0 <= vmaddr < vmaddr0 + filesize:
                return self.base + fileoff + (vmaddr - vmaddr0)
        return None

    def u64(self, vmaddr):
        off = self.offset(vmaddr)
        if off is None:
            return 0
        return struct.unpack_from('<Q', self.m, off)[0]

    def cstring(self, vmaddr):
        off = self.offset(vmaddr)
        if off is None:
            return None
        end = self.m.find(b'\0', off)
        return self.m[off:end].decode('utf8', 'replace')

    def pointers(self, section):
        if section not in self.sections:
            return []
        addr, size, _ = self.sections[section]
        return [self.u64(addr + 8 * i) for i in range(size // 8)]

    def selector_refs(self):
        names = set()
        for pointer in self.pointers('__objc_selrefs'):
            name = self.cstring(pointer)
            if name:
                names.add(name)
        return names

    def method_names(self, list_addr):
        names = set()
        if not list_addr:
            return names
        off = self.offset(list_addr)
        if off is None:
            return names
        entsize_flags, count = struct.unpack_from('<II', self.m, off)
        if entsize_flags & 0x80000000:   # relative method lists are not produced for x86_64 here
            return names
        entsize = entsize_flags & 0xFFFC
        if entsize < 24 or count > 100000:
            return names
        for i in range(count):
            name_ptr = struct.unpack_from('<Q', self.m, off + 8 + entsize * i)[0]
            name = self.cstring(name_ptr)
            if name:
                names.add(name)
        return names

    def class_methods(self, class_addr):
        names = set()
        data = self.u64(class_addr + 32) & ~7
        if data:
            names |= self.method_names(self.u64(data + 32))   # class_ro_t.baseMethods
        return names

    def implemented(self):
        names = set()
        for cls in self.pointers('__objc_classlist'):
            if not cls:
                continue
            names |= self.class_methods(cls)
            meta = self.u64(cls)   # isa
            if meta:
                names |= self.class_methods(meta)
        for cat in self.pointers('__objc_catlist'):
            if not cat:
                continue
            names |= self.method_names(self.u64(cat + 16))
            names |= self.method_names(self.u64(cat + 24))
        return names

    def class_names(self):
        names = set()
        for cls in self.pointers('__objc_classlist'):
            if not cls:
                continue
            data = self.u64(cls + 32) & ~7
            name = self.cstring(self.u64(data + 24)) if data else None
            if name:
                names.add(name)
        return names


def scan(root):
    for directory, _, files in os.walk(root):
        for name in files:
            path = os.path.join(directory, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            try:
                if os.path.getsize(path) < 4096:
                    continue
                with open(path, 'rb') as f:
                    head = f.read(4)
                if head not in (b'\xca\xfe\xba\xbe', b'\xcf\xfa\xed\xfe'):
                    continue
            except OSError:
                continue
            yield path


def main():
    roots, report = sys.argv[1].split(':'), sys.argv[2]
    targets = sys.argv[3:]
    os.makedirs(report, exist_ok=True)

    darling = set()
    classes = set()
    images = 0
    for root in roots:
        for path in scan(root):
            try:
                image = Image(path)
                darling |= image.implemented()
                classes |= image.class_names()
                images += 1
            except (ValueError, struct.error, OSError):
                continue
    print('darling images parsed: %d, implemented selectors: %d, classes: %d' % (images, len(darling), len(classes)))

    own = set()
    used = {}
    for path in targets:
        image = Image(path)
        own |= image.implemented()
        for selector in image.selector_refs():
            used.setdefault(selector, []).append(os.path.basename(path))

    missing = sorted(s for s in used if s not in darling and s not in own)
    with open(os.path.join(report, 'missing-selectors.txt'), 'w') as out:
        for selector in missing:
            out.write('%s\t%s\n' % (selector, ','.join(sorted(set(used[selector])))))
    print('selectors used: %d, defined by the game images: %d, missing from Darling: %d' % (len(used), len(own), len(missing)))


main()
