#!/usr/bin/env python3
"""Make a shader pair with sparse AIR locations and an unused vertex output."""
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
    folder = Path(temporary)
    payloads = {}
    for function in functions:
        (folder/'input.bc').write_bytes(function['bytes'])
        subprocess.run(['llvm-dis', str(folder/'input.bc'), '-o', str(folder/'input.ll')], check=True)
        text = (folder/'input.ll').read_text()
        text = text.replace('generated(5colorDv4_f)', 'user(locn7)')
        if function['name'] == 'vertexShader':
            text = text.replace('%struct.RasterizerData = type { <4 x float>, <4 x float> }',
                                '%struct.RasterizerData = type { <4 x float>, <4 x float>, <4 x float> }')
            text = text.replace('%16 = insertvalue %struct.RasterizerData %15, <4 x float> %14, 1',
                                '%fixture_green = insertvalue %struct.RasterizerData %15, <4 x float> <float 0.0, float 1.0, float 0.0, float 1.0>, 1\n  %16 = insertvalue %struct.RasterizerData %fixture_green, <4 x float> %14, 2')
            text = text.replace('!9 = !{!10, !11}', '!9 = !{!10, !100, !11}')
            text += '\n!100 = !{!"air.vertex_output", !"user(locn1)", !"air.arg_type_name", !"float4", !"air.arg_name", !"unusedGreen"}\n'
        (folder/'modified.ll').write_text(text)
        subprocess.run(['llvm-as', str(folder/'modified.ll'), '-o', str(folder/'modified.bc')], check=True)
        payloads[function['name']] = (folder/'modified.bc').read_bytes()
    prefix = bytearray(original[:bc_offset]); bitcode = bytearray()
    for function in functions:
        payload = payloads[function['name']]
        struct.pack_into('<Q', prefix, function['size_position'], len(payload))
        struct.pack_into('<Q', prefix, function['offset_position'], len(bitcode))
        bitcode.extend(payload)
    struct.pack_into('<Q', prefix, 16, len(prefix)+len(bitcode))
    struct.pack_into('<Q', prefix, 80, len(bitcode))
    (out/'sparse-varyings.bin').write_bytes(prefix+bitcode)
print('Created sparse AIR varying regression: unused green locn1, red locn7')
