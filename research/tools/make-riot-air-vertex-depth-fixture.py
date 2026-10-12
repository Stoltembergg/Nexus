#!/usr/bin/env python3
"""Make unsigned vertex-fetch and combined depth descriptor regressions."""
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
        (folder/'input.bc').write_bytes(function['bytes'])
        subprocess.run(['llvm-dis', str(folder/'input.bc'), '-o', str(folder/'input.ll')], check=True)
        text = (folder/'input.ll').read_text()
        if function['name'] == 'vertexShader':
            text = text.replace(' %2) local_unnamed_addr', ' %2, <4 x i32> %fixture_attr) local_unnamed_addr')
            text = text.replace('!12 = !{!13, !14, !16}', '!12 = !{!13, !14, !16, !100}')
            text += '\n!100 = !{i32 3, !"air.vertex_input", !"air.location_index", i32 7, i32 1, !"air.arg_type_name", !"uint4", !"air.arg_name", !"fixtureAttr"}\n'
            text = text.replace('  %16 = insertvalue', '  %fixture_r = extractelement <4 x i32> %fixture_attr, i32 0\n  %fixture_ok = icmp eq i32 %fixture_r, 255\n  %fixture_color = select i1 %fixture_ok, <4 x float> %14, <4 x float> zeroinitializer\n  %16 = insertvalue')
            text = text.replace('%15, <4 x float> %14, 1', '%15, <4 x float> %fixture_color, 1')
        else:
            text = text.replace('returned %1)', 'returned %1, ptr addrspace(1) %fixture_depth)')
            text = text.replace('!11 = !{!12, !13}', '!11 = !{!12, !13, !100}')
            text = text.replace('returned %1', '%1')
            text = text.replace('  ret <4 x float> %1', '  %fixture_sample = call <4 x float> @air.read_texture_2d.v4f32(ptr addrspace(1) %fixture_depth, <2 x i32> <i32 8, i32 4>, i32 0)\n  %fixture_d = extractelement <4 x float> %fixture_sample, i32 0\n  %fixture_ok = fcmp oeq float %fixture_d, 0.75\n  %fixture_result = select i1 %fixture_ok, <4 x float> %1, <4 x float> zeroinitializer\n  ret <4 x float> %fixture_result')
            text += '\ndeclare <4 x float> @air.read_texture_2d.v4f32(ptr addrspace(1), <2 x i32>, i32)\n'

            text += '\n!100 = !{i32 2, !"air.texture", !"air.location_index", i32 0, i32 1, !"air.sample", !"air.arg_type_name", !"depth2d<float, sample>", !"air.arg_name", !"fixtureDepth"}\n'
        (folder/'modified.ll').write_text(text)
        subprocess.run(['llvm-as', str(folder/'modified.ll'), '-o', str(folder/'modified.bc')], check=True)
        payload = (folder/'modified.bc').read_bytes()
        struct.pack_into('<Q', prefix, function['size_position'], len(payload))
        struct.pack_into('<Q', prefix, function['offset_position'], len(bitcode)); bitcode.extend(payload)
    struct.pack_into('<Q', prefix, 16, len(prefix)+len(bitcode)); struct.pack_into('<Q', prefix, 80, len(bitcode))
    (out/'unsigned-vertex-depth-descriptor.bin').write_bytes(prefix+bitcode)
print('Created unsigned vertex fetch and depth descriptor regression')
