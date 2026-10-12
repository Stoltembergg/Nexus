#!/usr/bin/env python3
"""Type only generated dummy text into our own temporary Riot DOM field."""
import argparse,json,subprocess,time,urllib.request,websocket
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--lowercase',action='store_true',help='avoid synthetic Shift transitions')
args=parser.parse_args()
with urllib.request.urlopen('http://127.0.0.1:9229/json/list',timeout=3) as r:target=json.load(r)[0]
ws=websocket.create_connection(target['webSocketDebuggerUrl'],timeout=20)
sequence=0
def evaluate(expression):
 global sequence
 sequence+=1
 script='(async()=>{const c=process.mainModule.require("electron").webContents.getAllWebContents().find(c=>c.getURL().startsWith("http"));if(!c.debugger.isAttached())c.debugger.attach("1.1");return c.debugger.sendCommand("Runtime.evaluate",{expression:'+json.dumps(expression)+',returnByValue:true})})()'
 ws.send(json.dumps({'id':sequence,'method':'Runtime.evaluate','params':{'expression':script,'awaitPromise':True,'returnByValue':True}}))
 while True:
  result=json.loads(ws.recv())
  if result.get('id')==sequence:return result.get('result',{}).get('result',{}).get('value',{}).get('result',{}).get('value')
text='abcXYZ0123'*20
if args.lowercase:text=text.lower()
setup=r'''(()=>{const id="darling-owned-typing-probe";document.getElementById(id)?.remove();const e=document.createElement("textarea");e.id=id;e.style="position:fixed;left:550px;top:100px;width:220px;height:60px;z-index:2147483647";const previous=document.activeElement;document.body.append(e);const guard=event=>{event.stopImmediatePropagation();if(event.target!==e)event.preventDefault()};const types=["keydown","keypress","keyup","input"];types.forEach(type=>document.addEventListener(type,guard,true));window.__darlingOwnedTypingCleanup=()=>{types.forEach(type=>document.removeEventListener(type,guard,true));e.remove();delete window.__darlingOwnedTypingCleanup;previous?.focus()};setTimeout(()=>window.__darlingOwnedTypingCleanup?.(),35000);e.focus();return document.activeElement===e})()'''
try:
 if evaluate(setup) is not True:raise RuntimeError('Own synthetic field could not focus')
 # Own X11 top-level only, no coordinates, names, field values, or clipboard.
 windows=subprocess.check_output(['xdotool','search','--onlyvisible','--class','Riot'],text=True).split()
 choices=[]
 for window in windows:
  fields=dict(l.split('=',1) for l in subprocess.check_output(['xdotool','getwindowgeometry','--shell',window],text=True).splitlines())
  choices.append((int(fields['WIDTH'])*int(fields['HEIGHT']),window))
 window=max(choices)[1]
 subprocess.run(['xdotool','windowfocus',window],check=True)
 if evaluate('document.activeElement?.id==="darling-owned-typing-probe"') is not True:raise RuntimeError('Synthetic field lost focus before typing')
 start=time.monotonic()
 # Stop synthetic typing if the user switches native windows.
 active=json.loads(subprocess.check_output(['hyprctl','activewindow','-j']))
 if active.get('class')!='Riot Client':raise RuntimeError('Riot is not the native foreground window')
 address=active['address']
 writer=subprocess.Popen(['xdotool','type','--clearmodifiers','--delay','100',text])
 try:
  while writer.poll() is None:
   if time.monotonic()-start>30:raise RuntimeError('Synthetic typing timed out')
   active=json.loads(subprocess.check_output(['hyprctl','activewindow','-j']))
   if active.get('address')!=address:raise RuntimeError('Native focus changed during synthetic typing')
   time.sleep(.05)
  if writer.returncode:raise RuntimeError('Synthetic typing failed')
 finally:
  if writer.poll() is None:
   writer.terminate()
   writer.wait(timeout=3)
 result=evaluate('(()=>{const e=document.getElementById("darling-owned-typing-probe");return {length:e?.value.length,match:e?.value==='+json.dumps(text)+'}})()')
 print(json.dumps({'synthetic_input':result,'elapsed_seconds':round(time.monotonic()-start,2)}))
 if not result or not result.get('match'):raise SystemExit(1)
finally:
 try:evaluate('window.__darlingOwnedTypingCleanup?.()')
 finally:ws.close()
