#!/usr/bin/env python3
"""Make a packed AIR struct that preserves float3 allocation padding."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
root = Path(__file__).resolve().parent.parent
source = root / 'build/darling-src/src/external/metal/deps/indium/test/triangle/AAPLShaders.metallib'
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
original = source.read_bytes()
func_offset = struct.unpack_from('<Q', original, 24)[0]
bc_offset = struct.unpack_from('<Q', original, 72)[0]
count = struct.unpack_from('<I', original, func_offset)[0]
position = func_offset + 4
functions = []
for index in range(count):
    end = position + struct.unpack_from('<I', original, position)[0]
    position += 4
    info = {}
    while original[position:position+4] != b'ENDT':
        tag = original[position:position+4]
        length = struct.unpack_from('<H', original, position+4)[0]
        data_position = position + 6
        data = original[data_position:data_position+length]
        if tag == b'NAME': info['name'] = data.rstrip(b'\0').decode()
        elif tag == b'MDSZ': info.update(size=struct.unpack('<Q', data)[0], size_position=data_position)
        elif tag == b'OFFT': info.update(offset=struct.unpack('<QQQ', data)[2], offset_position=data_position+16)
        position += length + 6
    position = end
    info['bytes'] = original[bc_offset+info['offset']:bc_offset+info['offset']+info['size']]
    functions.append(info)
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary); prefix = bytearray(original[:bc_offset]); bitcode = bytearray()
    for function in functions:
        payload = function['bytes']
        if function['name'] == 'vertexShader':
            (folder/'input.bc').write_bytes(payload)
            subprocess.run(['llvm-dis', str(folder/'input.bc'), '-o', str(folder/'input.ll')], check=True)
            text = (folder/'input.ll').read_text()
            text = text.replace('%struct.AAPLVertex = type { <2 x float>, <4 x float> }', '%struct.AAPLVertex = type <{ <3 x float>, <4 x float> }>')
            text = text.replace('  %6 = load <2 x float>, ptr addrspace(2) %5, align 16', '  %fixture_position = load <3 x float>, ptr addrspace(2) %5, align 16\n  %6 = shufflevector <3 x float> %fixture_position, <3 x float> undef, <2 x i32> <i32 0, i32 1>')
            (folder/'modified.ll').write_text(text)
            subprocess.run(['llvm-as', str(folder/'modified.ll'), '-o', str(folder/'modified.bc')], check=True)
            payload = (folder/'modified.bc').read_bytes()
        struct.pack_into('<Q', prefix, function['size_position'], len(payload))
        struct.pack_into('<Q', prefix, function['offset_position'], len(bitcode)); bitcode.extend(payload)
    struct.pack_into('<Q', prefix, 16, len(prefix)+len(bitcode)); struct.pack_into('<Q', prefix, 80, len(bitcode))
    (out/'packed-vec3.bin').write_bytes(prefix+bitcode)
print('Created packed float3 regression: color at byte 16, not byte 12')
