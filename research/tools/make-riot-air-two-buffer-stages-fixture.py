#!/usr/bin/env python3
"""Extend the depth-read regression with an independently offset fragment buffer."""
from pathlib import Path
import struct,subprocess,sys,tempfile
root=Path(__file__).resolve().parent.parent
source=root/'build/riot-shader-validation-m795/fixtures/unsigned-vertex-depth-descriptor.bin'
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
b=source.read_bytes();f=struct.unpack_from('<Q',b,24)[0];bc=struct.unpack_from('<Q',b,72)[0];pos=f+4;functions=[]
for _ in range(struct.unpack_from('<I',b,f)[0]):
 end=pos+struct.unpack_from('<I',b,pos)[0];pos+=4;d={}
 while b[pos:pos+4]!=b'ENDT':
  tag=b[pos:pos+4];n=struct.unpack_from('<H',b,pos+4)[0];at=pos+6;v=b[at:at+n]
  if tag==b'NAME':d['name']=v.rstrip(b'\0').decode()
  elif tag==b'MDSZ':d.update(size=struct.unpack('<Q',v)[0],size_at=at)
  elif tag==b'OFFT':d.update(offset=struct.unpack('<QQQ',v)[2],offset_at=at+16)
  pos+=6+n
 pos=end;functions.append(d)
with tempfile.TemporaryDirectory() as tmp:
 folder=Path(tmp);prefix=bytearray(b[:bc]);payloads=bytearray()
 for d in functions:
  payload=b[bc+d['offset']:bc+d['offset']+d['size']]
  if d['name']=='fragmentShader':
   (folder/'in.bc').write_bytes(payload);subprocess.run(['llvm-dis',str(folder/'in.bc'),'-o',str(folder/'in.ll')],check=True)
   s=(folder/'in.ll').read_text().replace('ptr addrspace(1) %fixture_depth)', 'ptr addrspace(1) %fixture_depth, ptr addrspace(2) %fixture_tint)')
   s=s.replace('  ret <4 x float> %fixture_result','  %fixture_scale = load <4 x float>, ptr addrspace(2) %fixture_tint, align 16\n  %fixture_scaled = fmul <4 x float> %fixture_result, %fixture_scale\n  ret <4 x float> %fixture_scaled')
   s=s.replace('memory(none)','memory(read)').replace('!11 = !{!12, !13, !14}', '!11 = !{!12, !13, !14, !101}')
   s+='\n!101 = !{i32 3, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read", !"air.arg_type_size", i32 16, !"air.arg_type_align_size", i32 16, !"air.arg_type_name", !"float4", !"air.arg_name", !"fixtureTint"}\n'
   (folder/'out.ll').write_text(s);subprocess.run(['llvm-as',str(folder/'out.ll'),'-o',str(folder/'out.bc')],check=True);payload=(folder/'out.bc').read_bytes()
  struct.pack_into('<Q',prefix,d['size_at'],len(payload));struct.pack_into('<Q',prefix,d['offset_at'],len(payloads));payloads.extend(payload)
 struct.pack_into('<Q',prefix,16,len(prefix)+len(payloads));struct.pack_into('<Q',prefix,80,len(payloads))
 (out/'two-buffer-stages.bin').write_bytes(prefix+payloads)
print('Created independent vertex and fragment buffer-offset regression')
