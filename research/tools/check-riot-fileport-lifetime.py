#!/usr/bin/env python3
"""Check server ownership of descriptors from our synthetic fileport probe."""
from pathlib import Path
import os,subprocess,time
root=Path(__file__).resolve().parent.parent
prefix=Path(os.environ.get('DPREFIX',str(Path.home()/'.darling')))
pid=int((prefix/'.init.pid').read_text().strip())
process=Path('/proc')/str(pid)
if (process/'exe').readlink().name!='darlingserver':raise SystemExit('Unexpected Darling server identity')
def owned_count():
 count=0
 for fd in (process/'fd').iterdir():
  try:
   if 'riot-fileport-lifetime-' in str(fd.readlink()):count+=1
  except FileNotFoundError:pass
 return count
before=owned_count()
result=subprocess.run(['darling','shell','/Volumes/SystemRoot'+str(root/'build/riot-fileport-lifetime-check')],capture_output=True,text=True,timeout=30)
for line in result.stdout.splitlines():
 if line.startswith('FILEPORT_LIFETIME '):print(line)
after=owned_count()
# No-senders notification processing may complete immediately after the RPC.
deadline=time.monotonic()+2
while after>before and time.monotonic()<deadline:
 time.sleep(.02);after=owned_count()
growth=after-before
print(f'FILEPORT_SERVER owned_descriptor_growth={growth} pass={int(result.returncode==0 and growth==0)}')
raise SystemExit(0 if result.returncode==0 and growth==0 else 1)
