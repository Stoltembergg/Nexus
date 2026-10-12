#!/usr/bin/env python3
"""Summarize bounded presenting-command-buffer intervals, not scanout timings."""
import argparse,csv,json,statistics
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
rows=[{k:int(v) for k,v in row.items()} for row in csv.DictReader(a.capture.open())]
if len(rows)<2:raise SystemExit('Need at least two presentation samples; capture is empty or incomplete')
is_present = 'queued_ns' in rows[0]
start_key = 'queued_ns' if is_present else 'commit_ns'
rows.sort(key=lambda r:r[start_key])
if len(rows)<2:raise SystemExit('Need at least two presenting command buffers')
def summary(values):
 s=sorted(values)
 def percentile(q):
  x=(len(s)-1)*q;lo=int(x);hi=min(lo+1,len(s)-1);return round(s[lo]+(s[hi]-s[lo])*(x-lo),3)
 return dict(count=len(s),mean_ms=round(statistics.mean(s),3),p50_ms=percentile(.5),p95_ms=percentile(.95),p99_ms=percentile(.99),max_ms=round(s[-1],3),over_16_67_ms=sum(v>1000/60 for v in s),over_25_ms=sum(v>25 for v in s),over_50_ms=sum(v>50 for v in s))
intervals=[(b[start_key]-a[start_key])/1e6 for a,b in zip(rows,rows[1:])]
result={'note':'Intervals between presenting Metal command-buffer commits; GPU completion includes queueing and callback delivery. These are not compositor scanout times. Confirm one presenting command buffer per game frame and active clock independently.', 'duration_s':round((rows[-1][start_key]-rows[0][start_key])/1e9,3),'intervals':summary(intervals),'events_per_s':round(1000/statistics.mean(intervals),3)}
if is_present:
 for label,end,start in [('main_queue_delay','render_start_ns','queued_ns'),('render_cpu_time','render_done_ns','render_start_ns'),('flush_cpu_time','flush_done_ns','render_done_ns'),('present_handoff_time','flush_done_ns','queued_ns')]:
  values=[(r[end]-r[start])/1e6 for r in rows if r[end] and r[start]]
  result[label]=summary(values) if values else None
 result['incomplete_rows']=sum(not r['flush_done_ns'] for r in rows)
 # Request cadence can hide bursts of delayed main-queue presentation work.
 # Sort completion timestamps independently: these measure CPU handoffs to
 # the window system, not physical scanout or distinct displayed frames.
 completed=sorted(r['flush_done_ns'] for r in rows if r['flush_done_ns'])
 gaps=[(b-a)/1e6 for a,b in zip(completed,completed[1:])]
 result['flush_completion_intervals']=summary(gaps) if gaps else None
 result['flush_gaps_over_25ms_followed_by_under_5ms']=sum(a>25 and b<5 for a,b in zip(gaps,gaps[1:]))
 result['flush_gaps_over_50ms_followed_by_under_5ms']=sum(a>50 and b<5 for a,b in zip(gaps,gaps[1:]))

else:
 for k in ('submitted_ns','presented_ns','completed_ns'):
  values=[(r[k]-r[start_key])/1e6 for r in rows if r[k]]
  result[k.replace('_ns','_from_commit')]=summary(values) if values else None
 result['incomplete_rows']=sum(not r['completed_ns'] for r in rows)
worst=sorted(range(1,len(rows)),key=lambda i:intervals[i-1],reverse=True)[:20]
result['longest_intervals']=[dict(index=i,elapsed_s=round((rows[i][start_key]-rows[0][start_key])/1e9,3),interval_ms=round(intervals[i-1],3)) for i in worst]
if is_present:
 result['note']='Intervals between game drawable presentation requests; queue/render/flush timings describe CPU work. These are not compositor scanout times. Confirm active clock independently.'
s=json.dumps(result,indent=2)+'\n'
if a.out:a.out.write_text(s)
print(s)
