#!/usr/bin/env python3
"""Compare GPU high/auto/high using the native stationary Baron workload.
Run in a desktop terminal as the normal user. sudo authenticates only GPU
policy writes; the original policy is restored in finally. Requires a prepared,
recording-enabled practice match. Graphics and power limits stay unchanged.
"""
import json, os, signal, subprocess, time
from pathlib import Path
import requests, urllib3

root=Path(__file__).resolve().parent.parent
os.chdir(root)
device=Path('/sys/class/drm/card1/device/power_dpm_force_performance_level')
initial=device.read_text().strip()
if initial not in ('high','auto'):raise SystemExit('Expected GPU high/auto; no policy change made')
urllib3.disable_warnings()
def clock():
 return requests.get('https://127.0.0.1:2999/liveclientdata/gamestats',verify=False,timeout=3).json()
game=clock()
player=requests.get('https://127.0.0.1:2999/liveclientdata/activeplayer',verify=False,timeout=3).json()
if game.get('gameMode')!='PRACTICETOOL' or player.get('level')!=18:
 raise SystemExit('Requires a prepared level-18 practice match; no policy change made')
if (Path.home()/'.darling/tmp/metal-async-encode').exists():
 raise SystemExit('Disable deferred encoding first; no policy change made')
# Authentication belongs in the user's terminal, before focusing the game.
subprocess.run(['sudo','-v'],check=True)
subprocess.run(['hyprctl','eval','hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['xdotool','search','--class','^LeagueofLegends$','windowraise'],check=True,stdout=subprocess.DEVNULL)
if json.loads(subprocess.check_output(['hyprctl','activewindow','-j'])).get('class')!='LeagueofLegends':
 raise SystemExit('Game not focused; no policy change made')
out=root/('logs/apu-balance-'+time.strftime('%Y%m%d-%H%M%S'));out.mkdir()
env=os.environ.copy();env.pop('ELECTRON_RUN_AS_NODE',None)
def mode(value):
 subprocess.run(['sudo','-n','tee',str(device)],input=value+'\n',text=True,check=True,stdout=subprocess.DEVNULL)
def state():
 d={'monotonic_ns':time.monotonic_ns(),'gpu_policy':device.read_text().strip()}
 for name,path in [('cpu1_khz','/sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq'),('gpu_clocks','/sys/class/drm/card1/device/pp_dpm_sclk'),('platform_profile','/sys/firmware/acpi/platform_profile')]:
  try:d[name]=Path(path).read_text().strip()
  except OSError:pass
 return d
def interrupt(signum,frame):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,interrupt)
results=[]
try:
 for label,value in [('high-before','high'),('auto','auto'),('high-after','high')]:
  subprocess.run(['sudo','-n','-v'],check=True)
  mode(value);time.sleep(5)
  subprocess.run(['timeout','-k','2','15','darling','shell','sh','-c','touch /tmp/metal-frame-interval-repeat'],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  before=state();before['gameTime']=clock()['gameTime']
  with (out/(label+'.log')).open('w') as log:
   result=subprocess.run(['python3','-I','tools/baron-workload.py','--stationary','--require-baron','--seconds','25','--window-out',str(out/(label+'-window.json'))],stdout=log,stderr=subprocess.STDOUT,timeout=110)
  after=state();after['gameTime']=clock()['gameTime']
  log=(out/(label+'.log')).read_text();start=log.find('{')
  if result.returncode or start<0 or after['gameTime']<=before['gameTime']:
   raise RuntimeError('Invalid workload/capture: '+label+'; see '+str(out))
  stats=json.loads(log[start:]);row={'label':label,'before':before,'after':after,'frames':stats}
  results.append(row);(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
  print(label,json.dumps(stats),flush=True)
finally:
 mode(initial)
print('Restored GPU policy:',initial,'Results:',out,flush=True)
