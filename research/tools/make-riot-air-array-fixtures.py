#!/usr/bin/env python3
"""Make GPU triangle variants that exercise AIR constant tables and local arrays."""
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
vertex = next(f for f in functions if f['name'] == 'vertexShader')
red = '<float 1.0, float 0.0, float 0.0, float 1.0>'
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    (folder/'vertex.bc').write_bytes(vertex['bytes'])
    subprocess.run(['llvm-dis', str(folder/'vertex.bc'), '-o', str(folder/'vertex.ll')], check=True)
    ir = (folder/'vertex.ll').read_text()
    for mode in ('global-table', 'local-array', 'combined-arrays', 'constant-gep'):
        text = ir
        operations = ['  %array_index = and i32 %0, 1']
        if mode != 'local-array':
            table = f'@fixture_table = internal addrspace(2) constant {{ [2 x <4 x float>] }} {{ [2 x <4 x float>] [<4 x float> {red}, <4 x float> {red}] }}, align 16\n'
            text = text.replace('; Function Attrs:', table+'\n; Function Attrs:', 1)
            if mode == 'constant-gep':
                operations.append('  %global_color = load volatile <4 x float>, ptr addrspace(2) getelementptr ({ [2 x <4 x float>] }, ptr addrspace(2) @fixture_table, i32 0, i32 0, i32 1), align 16')
            else:
                operations += ['  %global_ptr = getelementptr { [2 x <4 x float>] }, ptr addrspace(2) @fixture_table, i32 0, i32 0, i32 %array_index',
                               '  %global_color = load volatile <4 x float>, ptr addrspace(2) %global_ptr, align 16']
        if mode in ('local-array', 'combined-arrays'):
            operations += ['  %local_table = alloca [2 x <4 x float>], align 16',
                           '  %local_zero = getelementptr [2 x <4 x float>], ptr %local_table, i32 0, i32 0',
                           '  %local_one = getelementptr [2 x <4 x float>], ptr %local_table, i32 0, i32 1',
                           f'  store volatile <4 x float> {red}, ptr %local_zero, align 16',
                           f'  store volatile <4 x float> {red}, ptr %local_one, align 16',
                           '  %local_ptr = getelementptr [2 x <4 x float>], ptr %local_table, i32 0, i32 %array_index',
                           '  %local_color = load volatile <4 x float>, ptr %local_ptr, align 16']
        if mode == 'combined-arrays':
            operations += ['  %combined_color = fadd <4 x float> %global_color, %local_color',
                           '  %14 = fmul <4 x float> %combined_color, splat (float 0.5)']
        else:
            operations.append('  %14 = fadd <4 x float> %'+('local_color' if mode == 'local-array' else 'global_color')+', zeroinitializer')
        line = next(line for line in text.splitlines() if line.startswith('  %14 ='))
        text = text.replace(line, '\n'.join(operations))
        (folder/'modified.ll').write_text(text)
        subprocess.run(['llvm-as', str(folder/'modified.ll'), '-o', str(folder/'modified.bc')], check=True)
        prefix = bytearray(original[:bc_offset]); bitcode = bytearray()
        for function in functions:
            payload = (folder/'modified.bc').read_bytes() if function['name'] == 'vertexShader' else function['bytes']
            struct.pack_into('<Q', prefix, function['size_position'], len(payload))
            struct.pack_into('<Q', prefix, function['offset_position'], len(bitcode))
            bitcode.extend(payload)
        struct.pack_into('<Q', prefix, 16, len(prefix)+len(bitcode))
        struct.pack_into('<Q', prefix, 80, len(bitcode))
        (out/(mode+'.bin')).write_bytes(prefix+bitcode)
print('Created four AIR array regression libraries')
