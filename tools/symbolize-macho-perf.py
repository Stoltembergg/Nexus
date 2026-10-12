#!/usr/bin/env python3
"""Resolve captured Mach-O stacks using load segments and symbol tables.
No process memory, environment, or application argument reads.
"""
import argparse,bisect,collections,json,re,struct,subprocess
from pathlib import Path
class MachO:
 def __init__(self,path):
  b=Path(path).read_bytes();base=0
  if b[:4]==b'\xca\xfe\xba\xbe':
   for i in range(struct.unpack_from('>I',b,4)[0]):
    cpu,sub,off,size,align=struct.unpack_from('>IIIII',b,8+20*i)
    if cpu==0x1000007:base=off;break
  if b[base:base+4]!=b'\xcf\xfa\xed\xfe':raise ValueError('not x86_64 Mach-O')
  n=struct.unpack_from('<I',b,base+16)[0];pos=base+32;syms=None;starts=None;text_vm=0;self.segments=[]
  for _ in range(n):
   cmd,size=struct.unpack_from('<II',b,pos)
   if cmd==0x19:
    name,vm,vmsz,fo,fs=struct.unpack_from('<16sQQQQ',b,pos+8);self.segments.append((base+fo,base+fo+fs,vm))
    if name.rstrip(b"\0")==b"__TEXT":text_vm=vm
   elif cmd==2:syms=struct.unpack_from('<IIII',b,pos+8)
   elif cmd==0x26:starts=struct.unpack_from('<II',b,pos+8)
   pos+=size
  vals=[]
  if syms:
   so,count,stro,strsize=syms
   for i in range(count):
    ix,typ,sect,desc,value=struct.unpack_from('<IBBHQ',b,base+so+16*i)
    if typ&0xe0 or typ&0x0e!=0x0e or not value:continue
    end=b.find(b'\0',base+stro+ix);name=b[base+stro+ix:end].decode(errors='replace')
    if name:vals.append((value,name))
  vals.sort();self.addresses=[x[0] for x in vals];self.names=[x[1] for x in vals]
  self.base=base;self.functions=[]
  if starts:
   off,size=starts;pc=text_vm;delta=shift=0
   for byte in b[base+off:base+off+size]:
    delta|=(byte&127)<<shift
    if byte&128:shift+=7;continue
    if delta==0:break
    pc+=delta;self.functions.append(pc);delta=shift=0
 def resolve(self,offset):
  vm=next((vm+offset-lo for lo,hi,vm in self.segments if lo<=offset<hi),None)
  if vm is None:return None
  i=bisect.bisect_right(self.addresses,vm)-1
  j=bisect.bisect_right(self.functions,vm)-1
  function=self.functions[j] if j>=0 else None
  if i<0 or (function is not None and self.addresses[i]<function) or vm-self.addresses[i]>16384:
   return 'unsymbolized function '+hex(function if function is not None else vm),0
  return self.names[i],vm-self.addresses[i]
p=argparse.ArgumentParser();p.add_argument('--leaf-only', action='store_true', help='resolve sampled instruction pointers without DWARF unwinding; preserves Mach-O samples whose unwind fails');p.add_argument('data',type=Path);p.add_argument('maps',type=Path);p.add_argument('--kallsyms',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--image-override', action='append', default=[], metavar='BASENAME=PATH');p.add_argument('--time-ranges', type=Path, help='JSON list of [start,end] monotonic seconds; keep samples in these intervals');a=p.parse_args()
time_ranges=json.loads(a.time_ranges.read_text()) if a.time_ranges else None
if time_ranges is not None:
 if any(len(r)!=2 or r[0]>r[1] for r in time_ranges):p.error('invalid time ranges')
 time_ranges=sorted(time_ranges)
 range_starts=[r[0] for r in time_ranges]
 if any(left[1]>right[0] for left,right in zip(time_ranges,time_ranges[1:])):p.error('time ranges must not overlap')
image_overrides=dict(value.split('=',1) for value in a.image_override)
def load_maps(path):
 result=[]
 for line in path.read_text().splitlines():
  m=re.match(r'([0-9a-f]+)-([0-9a-f]+) \S+ ([0-9a-f]+) \S+ \S+\s+(.*)',line)
  if m:result.append((int(m[1],16),int(m[2],16),int(m[3],16),m[4]))
 return result
segments_by_pid={}
if a.maps.is_dir():
 roles=json.loads((a.maps/'roles.json').read_text())
 for role,role_pid in roles.items():segments_by_pid[role_pid]=load_maps(a.maps/(role+'-maps.txt'))
 segments=[]
else:segments=load_maps(a.maps)
images={};demangles={}
def resolve(addr,path,name):
 if name not in ['[unknown]'] and not name.startswith('0x'):return name
 if path.endswith(' (deleted)') or path.startswith('['):return name+'@'+hex(addr)
 if path not in images:
  try:images[path]=MachO(image_overrides.get(Path(path).name,path))
  except (OSError,ValueError,struct.error):images[path]=None
 image=images[path]
 if image:
  mapped=next((off+addr-lo for lo,hi,off,fp in segments_by_pid.get(pid,segments) if lo<=addr<hi and fp==path),None)
  if mapped is not None:
   result=image.resolve(mapped)
   if result:
    symbol,delta=result
    if symbol not in demangles:
     raw=symbol[1:] if symbol.startswith('_') else symbol
     demangles[symbol]=subprocess.run(['c++filt','--',raw],capture_output=True,text=True).stdout.strip()
    return demangles[symbol]
 return Path(path).name+'@'+hex(addr)
cmd=['perf','script','-i',str(a.data),'-F','pid,tid,time,period,event,ip,sym,dso']
if a.leaf_only:cmd.append('-G')
if a.kallsyms:cmd+=['--kallsyms',str(a.kallsyms)]
proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,text=True);stats=collections.defaultdict(lambda:{'samples':0,'total_weight':0,'leaf':collections.Counter(),'inclusive':collections.Counter(),'dso':collections.Counter(),'chains':collections.Counter(),'callers':collections.defaultdict(collections.Counter),'driver_callers':collections.Counter(),'strcmp_origins':collections.Counter(),'amdgpu_callers':collections.Counter(),'rpc_callers':collections.Counter()});pid=tid=None;weight=0;stack=[];first_time=float("inf");last_time=0.
def finish():
 if not stack:return
 if time_ranges is not None:
  i=bisect.bisect_right(range_starts,sample_time)-1
  if i<0 or sample_time>=time_ranges[i][1]:return
 k=str(pid)+'/'+str(tid);s=stats[k];s['samples']+=1;s['total_weight']+=weight
 frames=[(Path(path).name,resolve(addr,path,name)) for addr,path,name in stack]
 s['leaf'][frames[0]]+=weight;s['dso'][frames[0][0]]+=weight
 for f in set(frames):s['inclusive'][f]+=weight
 s['chains'][tuple(frames[:12])]+=weight
 if 'libvulkan_radeon' in frames[0][0]:
  caller=next((f for f in frames[1:] if f[0] in ['libindium.dylib','Metal','OpenGL','QuartzCore']),('unknown','no runtime caller'))
  s['driver_callers'][caller]+=weight
 if frames[0][0]=='[amdgpu]':
  caller=next((f for f in frames[1:] if f[0]=='libindium.dylib'),('unknown','no Indium caller'))
  s['amdgpu_callers'][caller]+=weight
 if any('dserver_rpc_' in f[1] for f in frames):
  caller=next((f for f in frames if 'dserver_rpc_' in f[1] and 'hooks' not in f[1]),('unknown','RPC hook only'))
  s['rpc_callers'][caller]+=weight
 if 'strcmp' in frames[0][1]:
  origin='RTTI' if any(f[0]=='libc++abi.dylib' for f in frames[1:]) else 'other'
  s['strcmp_origins'][origin]+=weight
 if any(x in frames[0][1] for x in ['strcmp','type_info','linux_syscall','FunctionResources','createDescriptorSets','pthread_mutex','objc_msgSend']):
  s['callers'][frames[0]][tuple(frames[1:7])]+=weight
for line in proc.stdout:
 m=re.match(r'\s*(\d+)/(\d+)\s+[\d.]+:\s+(\d+)\s+',line)
 if m:
  timestamp=float(line.split()[1].rstrip(":"));first_time=min(first_time,timestamp);last_time=max(last_time,timestamp)
  finish();pid,tid=int(m[1]),int(m[2]);weight=int(m[3]);sample_time=timestamp;stack=[]
  if a.leaf_only:
   leaf=re.match(r'.*?:\s+([0-9a-f]+)\s+(.*)\s+\((/.*|\[.*\])\)\s*$',line[m.end():])
   if leaf:stack=[(int(leaf[1],16),leaf[3],leaf[2])]
  continue
 m=re.match(r'\s+([0-9a-f]+)\s+(.*)\s+\((/.*|\[.*\])\)\s*$',line)
 if m:stack.append((int(m[1],16),m[3],m[2]))
finish();assert proc.wait()==0
out={}
for k,s in stats.items():
 N=s['total_weight'];out[k]={'samples':s['samples'],'total_weight':N}
 for kind in ['leaf','inclusive','dso']:
  out[k][kind]=[{'symbol':name,'weight':count,'pct':round(count/N*100,2)} for name,count in s[kind].most_common(50)]
 out[k]['chains']=[{'frames':list(chain),'weight':count,'pct':round(count/N*100,2)} for chain,count in s['chains'].most_common(20)]
 out[k]['driver_callers']=[{'caller':name,'pct_total':round(count/N*100,2)} for name,count in s['driver_callers'].most_common(15)]
 out[k]['amdgpu_callers']=[{'caller':name,'pct_total':round(count/N*100,2)} for name,count in s['amdgpu_callers'].most_common(15)]
 out[k]['rpc_callers']=[{'caller':name,'pct_total':round(count/N*100,2)} for name,count in s['rpc_callers'].most_common(15)]
 out[k]['strcmp_origins']={name:round(count/N*100,2) for name,count in s['strcmp_origins'].items()}
 for leaf,callers in s['callers'].items():
  out[k].setdefault('leaf_callers',[]).append({'leaf':leaf,'callers':[{'frames':chain,'pct_of_leaf':round(count/s['leaf'][leaf]*100,2),'pct_total':round(count/N*100,2)} for chain,count in callers.most_common(12)]})
a.out.with_suffix('.meta.json').write_text(json.dumps({'sample_window_s':last_time-first_time,'first_time':first_time,'last_time':last_time},indent=2))
a.out.write_text(json.dumps(out,indent=2));print('Resolved',sum(s['samples'] for s in stats.values()),'samples in',len(stats),'threads:',a.out)
