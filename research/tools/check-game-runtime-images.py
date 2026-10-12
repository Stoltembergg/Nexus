#!/usr/bin/env python3
"""Verify game mappings refer to current runtime files without reading process memory."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pid',type=int);a=p.parse_args()
if a.pid is None:
 for process in Path('/proc').iterdir():
  if not process.name.isdigit():continue
  try:
   if (process/'cmdline').read_bytes().split(b'\0',1)[0].endswith(b'/LeagueofLegends'):a.pid=int(process.name);break
  except OSError:pass
if a.pid is None:raise SystemExit('No running game')
images={}
for line in Path(f'/proc/{a.pid}/maps').read_text().splitlines():
 fields=line.split(maxsplit=5)
 if len(fields)<6:continue
 path=fields[5]
 if '/RuntimeLibraries/' not in path and '/RuntimeFrameworks/' not in path:continue
 if path in images:continue
 try:current_inode=Path(path).stat().st_ino
 except OSError:current_inode=None
 mapped_inode=int(fields[4]);images[path]={'mapped_inode':mapped_inode,'current_inode':current_inode,'matches':mapped_inode==current_inode}
print(json.dumps({'pid':a.pid,'images':images},indent=2))
raise SystemExit(0 if all(value['matches'] for value in images.values()) else 1)
