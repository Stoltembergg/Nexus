#!/usr/bin/env python3
"""Make AIR boolean extension and unused local pointer-cast regressions."""
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
            line = next(line for line in text.splitlines() if line.startswith('  %14 ='))
            operations = [
                '  %fixture_local = alloca [4 x float], align 16',
                '  %fixture_dead_cast = bitcast ptr %fixture_local to ptr',
                '  %fixture_condition = icmp ult i32 %0, 3',
                '  %fixture_byte = zext i1 %fixture_condition to i8',
                '  %fixture_short = zext i1 %fixture_condition to i16',
                '  %fixture_int = zext i1 %fixture_condition to i32',
                '  %fixture_long = zext i1 %fixture_condition to i64',
                '  %fixture_widen = zext i8 %fixture_byte to i32',
                '  %fixture_value = uitofp i32 %fixture_widen to float',
                '  %fixture_color = insertelement <4 x float> <float 0.0, float 0.0, float 0.0, float 1.0>, float %fixture_value, i32 0',
                '  %14 = fadd <4 x float> %fixture_color, zeroinitializer',
            ]
            text = text.replace(line, '\n'.join(operations))
            (folder/'modified.ll').write_text(text)
            subprocess.run(['llvm-as', str(folder/'modified.ll'), '-o', str(folder/'modified.bc')], check=True)
            payload = (folder/'modified.bc').read_bytes()
        struct.pack_into('<Q', prefix, function['size_position'], len(payload))
        struct.pack_into('<Q', prefix, function['offset_position'], len(bitcode)); bitcode.extend(payload)
    struct.pack_into('<Q', prefix, 16, len(prefix)+len(bitcode)); struct.pack_into('<Q', prefix, 80, len(bitcode))
    (out/'boolean-and-dead-cast.bin').write_bytes(prefix+bitcode)
print('Created boolean extension and dead local pointer cast regression')
