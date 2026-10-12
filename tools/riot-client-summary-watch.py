#!/usr/bin/env python3
"""Observe the one player-summary stoi input identified by the crash stack."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import time
needle = '/LeagueClient.app/Contents/MacOS/LeagueClient'
deadline = time.monotonic() + 240
pid = None
while time.monotonic() < deadline and pid is None:
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid == os.getuid() and needle in (p / 'maps').read_text():
                pid = int(p.name)
                break
        except OSError:
            pass
    if pid is None:
        time.sleep(.2)
if pid is None:
    raise SystemExit('LeagueClient did not start')
print(json.dumps({'observedPid': pid}), flush=True)
script = r'''
set pagination off
set confirm off
set print thread-events off
handle SIGPIPE SIGUSR1 SIGUSR2 SIGALRM SIGCHLD SIG32 SIG33 SIG34 SIG35 SIG36 SIG37 SIG38 SIG39 SIG40 SIG41 SIG42 SIG43 SIG44 SIG45 SIG46 SIG47 SIG48 SIG49 SIG50 SIG51 SIG52 SIG53 SIG54 SIG55 SIG56 SIG57 SIG58 SIG59 SIG60 SIG61 SIG62 SIG63 SIG64 nostop noprint pass
attach TARGET_PID
python
import gdb, json
from pathlib import Path
class SummaryBreakpoint(gdb.Breakpoint):
    def stop(self):
        inferior = gdb.selected_inferior()
        address = int(gdb.parse_and_eval('$rdi'))
        raw = bytes(inferior.read_memory(address, 24))
        is_long = bool(raw[0] & 1)
        size = int.from_bytes(raw[8:16], 'little') if is_long else raw[0] >> 1
        record = {'pid': TARGET_PID, 'callSite': '0x100861c94', 'size': size}
        if size <= 64:
            data = bytes(inferior.read_memory(int.from_bytes(raw[16:24], 'little'), size)) if is_long else raw[1:1+size]
            record['value'] = data.decode('utf-8', 'replace')
        Path('/tmp/league-summary-stoi.json').write_text(json.dumps(record))
        print(json.dumps(record))
        self.enabled = False
        return True
SummaryBreakpoint('*0x100861c94')
gdb.execute('continue')
end
detach
quit
'''.replace('TARGET_PID', str(pid))
with tempfile.NamedTemporaryFile('w', suffix='.gdb', delete=False) as f:
    f.write(script)
    name = f.name
try:
    result = subprocess.run(['gdb', '-nx', '-batch', '-x', name], capture_output=True, text=True, timeout=240)
    print(result.stdout[-2000:], flush=True)
    print(result.stderr[-1000:], flush=True)
finally:
    Path(name).unlink(missing_ok=True)
