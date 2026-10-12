#!/usr/bin/env python3
"""Make a fragment shader writing a sparse color attachment at slot two."""
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
        if function['name'] == 'fragmentShader':
            (folder/'input.bc').write_bytes(payload)
            subprocess.run(['llvm-dis', str(folder/'input.bc'), '-o', str(folder/'input.ll')], check=True)
            text = (folder/'input.ll').read_text()
            marker = '!"air.render_target", i32 0'
            if marker not in text: raise SystemExit('Missing fragment target metadata')
            text = text.replace(marker, '!"air.render_target", i32 2')
            (folder/'modified.ll').write_text(text)
            subprocess.run(['llvm-as', str(folder/'modified.ll'), '-o', str(folder/'modified.bc')], check=True)
            payload = (folder/'modified.bc').read_bytes()
        struct.pack_into('<Q', prefix, function['size_position'], len(payload))
        struct.pack_into('<Q', prefix, function['offset_position'], len(bitcode)); bitcode.extend(payload)
    struct.pack_into('<Q', prefix, 16, len(prefix)+len(bitcode)); struct.pack_into('<Q', prefix, 80, len(bitcode))
    (out/'sparse-color-slot2.bin').write_bytes(prefix+bitcode)
print('Created sparse fragment-output slot two regression')
