#!/usr/bin/env python3
"""Attribute main-thread syscall elapsed time and scheduler intervals."""
import argparse, subprocess, re, json, collections, array, bisect
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();d=a.directory
pid=json.loads((d/'roles.json').read_text())['LeagueofLegends']
names={0:'read',1:'write',7:'poll',9:'mmap',10:'mprotect',11:'munmap',16:'ioctl',23:'select',39:'getpid',46:'sendmsg',47:'recvmsg',202:'futex',228:'clock_gettime',96:'gettimeofday',234:'tgkill',309:'getcpu',14:'rt_sigprocmask',24:'sched_yield',35:'nanosleep',230:'clock_nanosleep'}
proc=subprocess.Popen(['perf','script','--ns','-i',str(d/'waits.data')],stdout=subprocess.PIPE,text=True)
start=end=None;pending=None;pending_off=0.;pending_offstart=None;stats=collections.defaultdict(lambda:{'count':0,'elapsed':0.0,'off_cpu':0.0,'durations':array.array('d')});intervals=[];off=None;wake=None;states=collections.Counter();switches=0;entered=collections.Counter();ioctls=collections.Counter();recv_fds=collections.Counter();recv_details=collections.defaultdict(lambda: {"count":0,"elapsed_s":0.,"errors":collections.Counter()})
for line in proc.stdout:
 m=re.search(r'\[\d+\]\s+([\d.]+):\s+([^:]+:[^:]+):\s+(.*)',line)
 if not m:continue
 t=float(m[1]);event=m[2].strip();s=m[3];start=t if start is None else start;end=t
 if event=='raw_syscalls:sys_enter':
  n=int(re.search(r'NR (\d+)',s)[1]);pending=(n,t,None);pending_off=0.;pending_offstart=None;entered[n]+=1
  args=re.search(r'\(([^)]+)\)',s)
  if args:
   words=args[1].split(', ')
   if n==16:ioctls[int(words[1],16)]+=1
   if n==47:
    fd=int(words[0],16);recv_fds[fd]+=1;pending=(n,t,fd)
 elif event=='raw_syscalls:sys_exit':
  n=int(re.search(r'NR (\d+)',s)[1])
  if pending and pending[0]==n:
   x=stats[n];dt=max(0,t-pending[1]);x['count']+=1;x['elapsed']+=dt;x['off_cpu']+=pending_off;x['durations'].append(dt)
   if n==47:
    r=recv_details[pending[2]];r['count']+=1;r['elapsed_s']+=dt;retval=int(re.search(r'= (-?\d+)',s)[1]);
    if retval<0:r['errors'][retval]+=1
  pending=None
 elif event=='sched:sched_switch':
  prev=int(re.search(r'prev_pid=(\d+)',s)[1]);nxt=int(re.search(r'next_pid=(\d+)',s)[1])
  if prev==pid:
   if pending:pending_offstart=t
   off=t;wake=None;state=re.search(r'prev_state=(\S+)',s)[1];states[state]+=1;switches+=1
   if state.startswith('R'):wake=t
  if nxt==pid and off is not None:
   if pending and pending_offstart is not None:pending_off+=t-pending_offstart;pending_offstart=None
   ready=t if wake is None else min(t,wake);intervals.append((off,t,ready));off=wake=None
 elif event=='sched:sched_wakeup' and off is not None and wake is None:
  wake=t
rc=proc.wait();assert rc==0
wall=end-start;sleep=sum(c-a for a,b,c in intervals);ready=sum(b-c for a,b,c in intervals)
rows=[]
for n,x in stats.items():
 v=sorted(x.pop('durations'));N=len(v)
 rows.append({'id':n,'name':names.get(n,str(n)),'count':N,'per_second':round(N/wall),'elapsed_s':round(x['elapsed'],6),'off_cpu_s':round(x['off_cpu'],6),'on_cpu_s':round(x['elapsed']-x['off_cpu'],6),'avg_us':round(x['elapsed']/N*1e6,2),'p50_us':round(v[N//2]*1e6,2),'p95_us':round(v[int(N*.95)]*1e6,2)})
result={'wall_s':wall,'main_off_cpu_s':sleep+ready,'blocked_s':sleep,'runnable_wait_s':ready,'switches':switches,'switch_states':dict(states),'syscalls':sorted(rows,key=lambda x:x['elapsed_s'],reverse=True),'ioctl_requests':{hex(k):v for k,v in ioctls.most_common()},'recv_fds':dict(recv_fds),'recv_details':dict(recv_details),'note':'Syscall durations include blocking and tracing overhead; CPU sampling without tracing is needed for unbiased attribution.'}
(d/'wait-summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
