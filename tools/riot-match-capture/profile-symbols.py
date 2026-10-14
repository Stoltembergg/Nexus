#!/usr/bin/env python3
"""Hottest functions of one thread inside the given Mach-O modules (llvm-nm), from <prefix>.offsets.json.

Usage: profile-symbols.py build/logs/host-profile-<stamp> <tid> Metal libobjc.A.dylib ..."""
import json,sys,subprocess,bisect,collections
prefix=sys.argv[1]; tid=sys.argv[2]; want=sys.argv[3:]
data=json.load(open(prefix+'.offsets.json'))[tid]
total=sum(v for _,_,v in data)
for w in want:
    path=next(n for n,_,_ in data if n.endswith(w))
    out=subprocess.run(['llvm-nm','-n','--defined-only',path],capture_output=True,text=True).stdout
    syms=[]
    for l in out.splitlines():
        a=l.split(None,2)
        if len(a)==3 and a[1] in 'tT': syms.append((int(a[0],16),a[2]))
    syms.sort(); addrs=[s[0] for s in syms]
    base=syms[0][0]&~0xffffffff if syms else 0
    c=collections.Counter(); n=0
    for name,o,v in data:
        if name!=path: continue
        n+=v; i=bisect.bisect_right(addrs,o+base)-1
        c[syms[i][1] if i>=0 else '?']+=v
    print('\n==',w,'%.1f%% of thread, %d symbols'%(100*n/total,len(syms)))
    for s,v in c.most_common(14): print('   %5.2f%%  %s'%(100*v/total,s[:100]))
