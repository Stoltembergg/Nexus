#!/usr/bin/env python3
"""Native Ctrl+V and empty/nonempty datalist checks on isolated Riot/Xvfb."""
import json,os,re,subprocess,time,urllib.request
import websocket
seq=0
ws=None
def evaluate(expression):
 global seq
 seq+=1
 script='(async()=>{let c=process.mainModule.require("electron").webContents.getAllWebContents().find(c=>c.getURL().startsWith("http"));if(!c)return null;if(!c.debugger.isAttached())c.debugger.attach("1.1");return c.debugger.sendCommand("Runtime.evaluate",{expression:'+json.dumps(expression)+',returnByValue:true})})()'
 ws.send(json.dumps({'id':seq,'method':'Runtime.evaluate','params':{'expression':script,'awaitPromise':True,'returnByValue':True}}))
 while True:
  r=json.loads(ws.recv())
  if r.get('id')==seq:
   value=r.get('result',{}).get('result',{}).get('value')
   return value.get('result',{}).get('value') if isinstance(value,dict) else None
def run(*args):subprocess.run(['xdotool',*args],env=env,check=True)
def popup_ids():
 tree=subprocess.check_output(['xwininfo','-root','-tree'],env=env,text=True)
 return set(re.findall(r'^\s*(0x[0-9a-f]+) \(has no name\): \("Riot Client" "Riot Client"\)',tree,re.M))
env={**os.environ,'DISPLAY':':99'}
end=time.monotonic()+180
while time.monotonic()<end:
 try:
  if ws is None:
   info=json.load(urllib.request.urlopen('http://127.0.0.1:9229/json/list',timeout=2))
   ws=websocket.create_connection(info[0]['webSocketDebuggerUrl'],timeout=20)
  if evaluate('document.querySelector("input[name=username]")!==null'):break
 except (OSError,websocket.WebSocketException,ValueError):
  if ws:ws.close()
  ws=None
 time.sleep(2)
else:raise SystemExit('Riot unavailable')
tree=subprocess.check_output(['xwininfo','-root','-tree'],env=env,text=True)
window=re.findall(r'^\s*(0x[0-9a-f]+) "Riot Client":.*?1536x864',tree,re.M)[0]
try:
 evaluate('''(()=>{document.getElementById('darling-paste-test')?.remove();let x=document.createElement('input');x.id='darling-paste-test';x.autocomplete='off';x.style='position:fixed;left:60px;top:20px;width:220px;height:30px;z-index:2147483647';document.body.append(x);return true})()''')
 run('mousemove','--window',window,'120','35','click','1')
 assert evaluate('document.activeElement.id')=='darling-paste-test'
 run('key','--window',window,'ctrl+v')
 time.sleep(.3)
 result=evaluate('({length:document.getElementById("darling-paste-test").value.length,match:document.getElementById("darling-paste-test").value==="darling_paste"})')
 print('NATIVE_PASTE',json.dumps(result),flush=True)
 assert result=={'length':13,'match':True},'Ctrl+V did not paste isolated clipboard'
 run('key','--window',window,*(['BackSpace']*13))
 baseline=popup_ids()
 run('type','--window',window,'--delay','60','darling_probe')
 time.sleep(.3)
 empty=popup_ids()
 print('EMPTY_DATALIST baseline='+str(len(baseline))+' after_typing='+str(len(empty)),flush=True)
 assert empty==baseline,'Empty datalist created popup windows'
 run('key','--window',window,*(['BackSpace']*13))
 evaluate('''(()=>{let l=document.createElement('datalist');l.id='darling-test-list';let o=document.createElement('option');o.value='darling_choice';l.append(o);document.body.append(l);document.getElementById('darling-paste-test').setAttribute('list',l.id);return true})()''')
 run('type','--window',window,'d')
 time.sleep(.4)
 created=popup_ids()-baseline
 count=len(created)
 print('NONEMPTY_DATALIST popup_count='+str(count),flush=True)
 assert count>0,'Real suggestions no longer show'
 run('key','--window',window,'Escape','BackSpace')
 print('PASTE_POPUP_CHECK passed',flush=True)
finally:
 if ws:
  try:evaluate('document.getElementById("darling-paste-test")?.remove();document.getElementById("darling-test-list")?.remove()')
  except (OSError,websocket.WebSocketException):pass
  ws.close()
