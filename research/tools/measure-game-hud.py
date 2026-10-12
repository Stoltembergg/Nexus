#!/usr/bin/env python3
"""Sample the game FPS HUD, confirming active play without renderer diagnostics."""
import argparse,json,re,statistics,subprocess,time
from pathlib import Path
import requests,urllib3
urllib3.disable_warnings()
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--samples',type=int,default=10)
p.add_argument('--interval',type=float,default=3)
p.add_argument('--min-clock',type=float,default=45)
p.add_argument('--display-capture',action='store_true',help='Capture the active Wayland display and validate its visible match clock')
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
def clock():
 try:return requests.get('https://127.0.0.1:2999/liveclientdata/gamestats',verify=False,timeout=3).json().get('gameTime')
 except (requests.RequestException,ValueError):return None
previous=None;deadline=time.monotonic()+180
while time.monotonic()<deadline:
 now=clock()
 if now is not None and now>=a.min_clock and previous is not None and now-previous>=1:break
 previous=now;time.sleep(3)
else:raise SystemExit('No active match clock; no valid measurement')
tree=subprocess.check_output(['xwininfo','-root','-tree'],text=True)
m=re.search(r'(0x[0-9a-f]+) "League of Legends \(TM\) Client".*?1920x1080',tree)
if not m:raise SystemExit('Expected a 1920x1080 game drawable')
game_pid=None
for entry in Path('/proc').iterdir():
 if not entry.name.isdigit():continue
 try:
  if (entry/'cmdline').read_bytes().split(b'\0',1)[0].endswith(b'/LeagueofLegends'):game_pid=int(entry.name);break
 except OSError:pass
samples=[];print('Sampling active game HUD into',a.out,flush=True)
for i in range(a.samples):
 start=time.monotonic();game_time=clock();xwd=a.out/'game.xwd'
 if a.display_capture:
  active=json.loads(subprocess.check_output(['hyprctl','activewindow','-j'],text=True))
  if active.get('class')!='LeagueofLegends':raise SystemExit('Game is not the active window; refusing a stale HUD measurement')
  xwd=a.out/'display.png'
  subprocess.run(['grim',str(xwd)],check=True)
 else:
  subprocess.run(['xwd','-silent','-id',m[1],'-out',str(xwd)],check=True)
 hud=a.out/f'hud-{i}.png';ocr=a.out/f'hud-{i}-ocr.png'
 subprocess.run(['magick',str(xwd),'-crop','220x40+1700+25','-resize','300%',str(hud)],check=True)
 subprocess.run(['magick',str(hud),'-colorspace','Gray','-threshold','65%',str(ocr)],check=True)
 text=subprocess.check_output(['tesseract',str(ocr),'stdout','--psm','6'],stderr=subprocess.DEVNULL,text=True).strip()
 match=re.search(r'F?PS\s*[:;]?\s*(\d+)',text,re.I)
 freqs=[]
 for policy in Path('/sys/devices/system/cpu/cpufreq').glob('policy*'):
  try:freqs.append(int((policy/'scaling_cur_freq').read_text()))
  except OSError:pass
 sample={'elapsed_s':round(start,3),'clock':game_time,'fps':int(match[1]) if match else None,'hud':text,'cpu_median_khz':statistics.median(freqs) if freqs else None}
 try:
  task=Path(f'/proc/{game_pid}/task/{game_pid}/stat').read_text()
  cpu=int(task[task.rindex(')')+2:].split()[36])
  sample['main_cpu']=cpu
  sample['main_cpu_khz']=int(Path(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq').read_text())
 except (OSError,ValueError):pass
 try:sample['gpu_sclk_hz']=int(next(Path('/sys/class/drm/card1/device/hwmon').glob('hwmon*/freq1_input')).read_text())
 except (OSError,ValueError,StopIteration):pass
 if a.display_capture:
  visible=a.out/'visible-clock.png'
  subprocess.run(['magick',str(xwd),'-crop','80x24+1830+0','-resize','500%',str(visible)],check=True)
  visible_text=subprocess.check_output(['tesseract',str(visible),'stdout','--psm','7'],stderr=subprocess.DEVNULL,text=True).strip()
  timer=re.search(r'(\d{1,3}):(\d{2})',visible_text)
  visible_seconds=int(timer[1])*60+int(timer[2]) if timer else None
  sample['visible_clock_text']=visible_text;sample['visible_clock_s']=visible_seconds
  if visible_seconds is None or game_time is None or abs(visible_seconds-game_time)>3:
   raise SystemExit('Visible clock does not match live clock; refusing a stale capture: '+repr(sample))
 samples.append(sample);print(json.dumps(sample),flush=True)
 time.sleep(max(0,a.interval-(time.monotonic()-start)))
subprocess.run(['magick',str(xwd),str(a.out/'game.png')],check=True);xwd.unlink()
valid=[x['fps'] for x in samples if x['fps'] is not None]
wall=samples[-1]['elapsed_s']-samples[0]['elapsed_s'];advancing=all(x['clock'] is not None for x in samples) and wall*.8<=samples[-1]['clock']-samples[0]['clock']<=wall*1.2
result={'samples':samples,'clock_advances_in_real_time':advancing,'fps_min':min(valid) if valid else None,'fps_mean':statistics.mean(valid) if valid else None,'fps_max':max(valid) if valid else None,'note':'FPS values are smoothed game HUD samples, not independent frame-time percentiles.'}
(a.out/'hud-samples.json').write_text(json.dumps(result,indent=2)+'\n')
print('HUD summary',json.dumps({k:v for k,v in result.items() if k!='samples'}),flush=True)
if not advancing or len(valid)!=a.samples:raise SystemExit('Incomplete/invalid HUD measurement; inspect captures')
