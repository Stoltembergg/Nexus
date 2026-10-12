#!/usr/bin/env python3
"""Exercise the isolated AppKit/X11 build with Linux uinput events."""
import json, os, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from uinput_click import Mouse, hover, EV_KEY, EV_REL, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA, REL_X, REL_WHEEL, REL_HWHEEL
root=Path(__file__).resolve().parent.parent
# Remove only a stale instance of this disposable probe from a failed run.
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  if proc.joinpath('cmdline').read_bytes().split(b'\0')[0] == b'/Volumes/SystemRoot/tmp/mouse-check/riot-mouse-input-check':os.kill(int(proc.name),9)
 except (OSError,ProcessLookupError):pass
log=Path('/tmp/mouse-check/validation.log')
env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
output=log.open('w')
process=subprocess.Popen(['darling','shell','env','DYLD_FRAMEWORK_PATH=/Volumes/SystemRoot/tmp/mouse-check/frameworks:@GUEST_HOME@/RuntimeFrameworks','DYLD_LIBRARY_PATH=@GUEST_HOME@/RuntimeLibraries','RCLOL_INPUT_TRACE=1','/Volumes/SystemRoot/tmp/mouse-check/riot-mouse-input-check'],stdout=output,stderr=subprocess.STDOUT,env=env)
def clients():return json.loads(subprocess.check_output(['hyprctl','clients','-j']))
def focus(title): subprocess.run(['hyprctl','eval',f'hl.dispatch(hl.dsp.focus({{window="title:^({title})$"}}))'],check=True,stdout=subprocess.DEVNULL);time.sleep(.3)
def cursor():
 s=subprocess.check_output(['hyprctl','cursorpos'],text=True)
 return tuple(map(int,re.findall(r'-?\d+',s)[:2]))
end=time.monotonic()+20
while time.monotonic()<end:
 if 'READY' in log.read_text():break
 time.sleep(.2)
else:raise RuntimeError('Probe did not become ready')
w=next(w for w in clients() if w['title']=='Darling Mouse Check')
focus('Darling Mouse Check');hover(w['at'][0]+200,w['at'][1]+150)
m=Mouse()
try:
 for b in (BTN_MIDDLE,BTN_SIDE,BTN_EXTRA):m.click(button=b)
 m.emit(EV_KEY,BTN_MIDDLE,1);m.syn();time.sleep(.1)
 m.emit(EV_REL,REL_X,20);m.syn();time.sleep(.1)
 m.emit(EV_KEY,BTN_MIDDLE,0);m.syn()
 for axis in (REL_WHEEL,REL_HWHEEL):
  for v in (1,-1):m.emit(EV_REL,axis,v);m.syn();time.sleep(.2)
 tree=subprocess.check_output(['xwininfo','-root','-tree'],text=True)
 xid=re.search(r'(0x[0-9a-f]+) "Darling Mouse Check"',tree).group(1)
 # Mark only the disposable probe fullscreen. Keep its small rectangle to
 # prove confinement independently of the physical monitor's own edges.
 subprocess.run(['xprop','-id',xid,'-f','_NET_WM_STATE','32a','-set','_NET_WM_STATE','_NET_WM_STATE_FULLSCREEN'],check=True)
 time.sleep(.5)
 m.emit(EV_REL,REL_X,1200);m.syn();time.sleep(.3)
 confined=cursor();x,y=w['at'];width,height=w['size']
 assert x<=confined[0]<x+width and y<=confined[1]<y+height,('escape',confined,w)
 print('CONFINEMENT inside_window=',confined,flush=True)
 focus('Riot Client')
 m.emit(EV_REL,REL_X,500);m.syn();time.sleep(.3)
 released=cursor()
 assert released[0]>=x+width,('focus did not release',released)
 print('FOCUS_OUT released=',released,flush=True)
 focus('Darling Mouse Check')
 time.sleep(.3)
 regained=cursor()
 assert x<=regained[0]<x+width,('focus did not regain confinement',regained)
 print('FOCUS_IN reacquired=',regained,flush=True)
 subprocess.run(['xprop','-id',xid,'-remove','_NET_WM_STATE'],check=True)
 time.sleep(.3);m.emit(EV_REL,REL_X,500);m.syn();time.sleep(.3)
 assert cursor()[0]>=x+width,'Windowed mode did not release confinement'
 print('WINDOWED released=pass',flush=True)
finally:m.close()
process.wait(timeout=45);output.close()
s=log.read_text()
for b in (2,3,4):
 for action in ('down','up'):assert f'DISPATCH {action} {b}' in s
assert 'DISPATCH drag 2' in s
for axes in ('0 3','0 -3','3 0','-3 0'):assert 'DISPATCH scroll '+axes in s
assert 'DONE' in s and process.returncode==0
print('PASS middle, side buttons, drag, CoreGraphics bridge, 3x scroll, confinement lifecycle')
