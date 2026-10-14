#!/usr/bin/env python3
"""Per-thread summary of a sample-match.py capture: CPU, runqueue wait, wakeups and blocking system calls.

Usage: sample-report.py build/logs/host-sample-<stamp>.jsonl [first_second last_second]"""
import json,sys,collections
rows=[json.loads(l) for l in open(sys.argv[1])]
head=rows[0]; rows=rows[1:]; pid=str(head['game'])
print('seconds',len(rows),'start',rows[0]['time'],'end',rows[-1]['time'],'observer_cpu_s',rows[-1]['observer_cpu_s'])
lo=int(sys.argv[2]) if len(sys.argv)>2 else 0; hi=int(sys.argv[3]) if len(sys.argv)>3 else len(rows)
rows=rows[lo:hi]; T=sum(r['elapsed_s'] for r in rows)
fds={}
for r in rows: fds.update(r.get('game_fds',{}))
for side in ('game','server'):
    agg={}
    for r in rows:
        for tid,t in r[side].items():
            a=agg.setdefault(tid,{'name':t['name'],'run':0,'queue':0,'slices':0,'sys':collections.Counter()})
            a['run']+=t.get('run_ns',0);a['queue']+=t.get('queue_ns',0);a['slices']+=t.get('slices',0);a['sys'].update(t['syscall'])
    print('==',side,'threads',len(agg),'total cpu %% of one core: %.1f'%(sum(a['run'] for a in agg.values())/1e7/T))
    for tid,a in sorted(agg.items(),key=lambda kv:-kv[1]['run'])[:14]:
        n=sum(a['sys'].values()) or 1
        top=', '.join('%s %.1f%%'%(k,100*v/n) for k,v in a['sys'].most_common(6))
        print('%s%s %-16s run %5.1f%% queue %4.1f%% slices/s %6.0f | %s'%('*' if tid==pid else ' ',tid,a['name'],a['run']/1e7/T,a['queue']/1e7/T,a['slices']/T,top))
print('gpu busy mean',sum(r['gpu_busy'][0] for r in rows)/len(rows))
m=collections.Counter()
for r in rows: m.update(r['game'].get(pid,{}).get('syscall',{}))
for k,v in m.most_common(12):
    fd=k.split('fd=')[1] if 'fd=' in k else None
    print('main',k,'%.2f%%'%(100*v/sum(m.values())),fds.get(fd,'') if fd else '')
