#!/usr/bin/env python3
"""Observe the next runtime launch; capture user CPU samples and loading milestones.
Start before profile-cycle.sh. Existing processes are ignored. Does not launch,
stop, or modify the game, read process memory, or print client credentials.
"""
import argparse, importlib.util, json, os, signal, subprocess, time
from pathlib import Path
import requests, urllib3
urllib3.disable_warnings()
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--timeout',type=float,default=600)
a=parser.parse_args();a.out.mkdir(parents=True,exist_ok=False)
def processes():
 result={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:name=(p/'cmdline').read_bytes().split(b'\0',1)[0].rsplit(b'/',1)[-1].decode(errors='replace')
  except OSError:continue
  if name in ('LeagueofLegends','LeagueClient','LeagueClientUx','RiotClientServices','darlingserver'):result[int(p.name)]=name
 return result
spec=importlib.util.spec_from_file_location('lcu',root/'tools/lcu-practice-game.py');lcu=importlib.util.module_from_spec(spec);spec.loader.exec_module(lcu)
client=lcu.Client(Path.home()/'.darling/Applications/League of Legends.app/Contents/LoL/lockfile')
ignored=set(processes());begin=time.monotonic();records={};milestones=[];children={};last_clock=None;clock_seen=None;ready=None;last_poll=0;last_phase=None
metadata={'note':'Observer timings include launch orchestration. Backend-ready is first Lobby/ChampSelect/Playable phase; game-ready is first advancing live match clock. CPU sampling adds observer overhead. Champion-select waiting is separate.','initial_ignored_pids':sorted(ignored)}
def event(kind,**extra):
 value={'event':kind,'elapsed_s':round(time.monotonic()-begin,3),**extra};milestones.append(value);print(json.dumps(value),flush=True)
def stop(pid):
 child,log=children.pop(pid)
 if child.poll() is None:child.send_signal(signal.SIGINT)
 try:code=child.wait(timeout=5)
 except subprocess.TimeoutExpired:child.terminate();code=child.wait(timeout=5)
 log.close();records[str(pid)]['perf_exit_code']=code;records[str(pid)]['capture_end_s']=round(time.monotonic()-begin,3)
try:
 while time.monotonic()-begin<a.timeout:
  found=processes()
  for pid,role in found.items():
   if pid in ignored or str(pid) in records:continue
   records[str(pid)]={'role':role,'first_seen_s':round(time.monotonic()-begin,3)}
   folder=a.out/(role+'-'+str(pid));folder.mkdir();records[str(pid)]['folder']=str(folder)
   (folder/'maps.txt').write_text(Path('/proc/'+str(pid)+'/maps').read_text())
   log=(folder/'perf-errors.txt').open('w')
   child=subprocess.Popen(['perf','record','-q','-e','cpu-clock:u','-F','199','-g','-p',str(pid),'-o',str(folder/'cpu.data')],stderr=log)
   children[pid]=(child,log);event('process-start',pid=pid,role=role)
  now=time.monotonic()
  if now-last_poll>=1 and any(x['role']=='LeagueClient' for x in records.values()):
   last_poll=now
   response=client.call('GET','/lol-gameflow/v1/gameflow-phase',timeout=.5)
   if not isinstance(response,Exception) and response.status_code==200:
    try:phase=response.json()
    except ValueError:phase=None
    if phase!=last_phase:event('client-phase',phase=phase);last_phase=phase
    if ready is None and phase in ('Lobby','ChampSelect','InProgress','Reconnect'):
     ready=now;event('client-backend-ready')
   if any(x['role']=='LeagueofLegends' for x in records.values()):
    try:clock=requests.get('https://127.0.0.1:2999/liveclientdata/gamestats',verify=False,timeout=.5).json().get('gameTime')
    except (requests.RequestException,ValueError):clock=None
    if clock is not None and last_clock is not None and clock>last_clock+.5:
     if clock_seen is None:clock_seen=now;event('match-clock-advancing',game_clock=clock)
    else:clock_seen=None
    last_clock=clock
  for pid in list(children):
   role=records[str(pid)]['role']
   if pid not in found or now-begin-records[str(pid)]['first_seen_s']>=120 or (ready is not None and role!='LeagueofLegends' and now-ready>=2):stop(pid)
  if clock_seen is not None and now-clock_seen>=3:
   event('match-ready',game_clock=last_clock);break
  time.sleep(.2)
 else:event('timeout')
finally:
 for pid in list(children):stop(pid)
 for pid,record in records.items():
  try:Path(record['folder'],'maps.txt').write_text(Path('/proc/'+pid+'/maps').read_text())
  except OSError:pass
 metadata.update(processes=records,milestones=milestones,duration_s=round(time.monotonic()-begin,3))
 (a.out/'summary.json').write_text(json.dumps(metadata,indent=2)+'\n')
