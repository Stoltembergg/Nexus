#!/usr/bin/env python3
"""Per-module share of each thread's user time in a profile-match.py capture; writes <prefix>.offsets.json.

Usage: profile-report.py build/logs/host-profile-<stamp> [skip_seconds=120] [threads=3]"""
import json,sys,bisect,collections,os
prefix=sys.argv[1]; skip=float(sys.argv[2]) if len(sys.argv)>2 else 120
maps=[json.loads(l) for l in open(prefix+'.maps.jsonl')]
def parse(text):
    regs=[]
    for line in text.splitlines():
        a=line.split(None,5)
        lo,hi=[int(x,16) for x in a[0].split('-')]
        regs.append((lo,hi,int(a[2],16),a[5] if len(a)==6 else '[anon]',a[1]))
    regs.sort(); return regs
snaps=[(m['mono_ns'],parse(m['maps'])) for m in maps]
starts=[s[0] for s in snaps]
thr=[json.loads(l) for l in open(prefix+'.threads.jsonl')]
t0=thr[0]['mono_ns']+int(skip*1e9); t1=thr[-1]['mono_ns']
first=next(r for r in thr if r['mono_ns']>=t0); last=thr[-1]
pid=min(first['threads'],key=int)
def look(t,ip):
    regs=snaps[max(0,bisect.bisect_right(starts,t)-1)][1]
    i=bisect.bisect_right(regs,(ip,1<<62))-1
    if i>=0 and regs[i][0]<=ip<regs[i][1]:
        r=regs[i]; return r[3],ip-r[0]+r[2]
    return '[unmapped]',ip
mod=collections.defaultdict(collections.Counter); off=collections.defaultdict(collections.Counter)
for line in open(prefix+'.samples'):
    tid,t,ip=line.split(); t=int(t)
    if t<t0: continue
    name,o=look(t,int(ip,16))
    mod[tid][name]+=1
    off[tid][(name,o)]+=1
dur=(last['mono_ns']-first['mono_ns'])/1e9
print('window s %.0f'%dur)
order=sorted(mod,key=lambda t:-sum(mod[t].values()))[:int(sys.argv[3]) if len(sys.argv)>3 else 3]
for tid in order:
    per=0.001 if tid==pid else 0.004
    a=first['threads'].get(tid);b=last['threads'].get(tid)
    n=sum(mod[tid].values())
    print('\n== tid',tid,b[0] if b else '?','samples',n,'= user %.1f%% of wall'%(100*n*per/dur))
    if a and b: print('   /proc: utime %.1f%% stime %.1f%% run %.1f%%'%((b[1]-a[1])/dur,(b[2]-a[2])/dur,(b[3]-a[3])/1e7/dur))
    for name,c in mod[tid].most_common(22): print('   %5.1f%%  %s'%(100*c/n,name if len(name)<110 else '...'+name[-105:]))
json.dump({tid:[[k[0],k[1],v] for k,v in off[tid].most_common(40000)] for tid in order},open(prefix+'.offsets.json','w'))
