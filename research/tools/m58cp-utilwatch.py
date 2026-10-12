import os, glob, re, time

def rd(p):
    try:
        return open(p, 'rb').read()
    except OSError:
        return b""

def browser():
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if open(d + "/comm").read().strip() == "CrBrowserMain":
                return int(d.split('/')[-1])
        except OSError:
            pass
    return None

def children(bp):
    out = []
    for d in glob.glob("/proc/[0-9]*"):
        pid = int(d.split('/')[-1])
        f = rd(d + "/stat").decode('utf-8', 'replace')
        if not f:
            continue
        i = f.rfind(')')
        rest = f[i+2:].split()
        if len(rest) < 2 or int(rest[1]) != bp:
            continue
        comm = f[f.find('(')+1:i]
        state = rest[0]
        typ = ""
        cmd = rd(d + "/cmdline").replace(b"\x00", b" ").decode('utf-8', 'replace')
        m = re.search(r"--utility-sub-type=([\w.\-]+)", cmd)
        if m:
            typ = m.group(1)
        # field 52 = exit_code -> rest[49]; field 38 = exit_signal -> rest[35]
        ex = rest[49] if len(rest) > 49 else "?"
        sig = rest[35] if len(rest) > 35 else "?"
        out.append((pid, comm, state, typ, ex, sig))
    return out

bp = browser()
print("browser host pid:", bp)
t0 = time.time()
last = {}
while time.time() - t0 < 50:
    if bp is None:
        bp = browser()
        if bp is not None:
            print("t=%5.1fs browser appeared pid=%d" % (time.time() - t0, bp))
    if bp is None:
        time.sleep(1)
        continue
    for row in children(bp):
        pid, comm, state, typ, ex, sig = row
        k = pid
        cur = (state, typ, ex, sig)
        if last.get(k) != cur:
            last[k] = cur
            print("t=%5.1fs pid=%d comm=%s state=%s sub=%s exit_code=%s exit_signal=%s"
                  % (time.time() - t0, pid, comm, state, typ or "-", ex, sig))
    time.sleep(1)
print("--- crashpad completed dumps ---")
for base in ("@HOST_HOME@/Library/Application Support/riot-client-ux/Crashpad/completed",
             "@DPREFIX@@GUEST_HOME@/Library/Application Support/riot-client-ux/Crashpad/completed"):
    if os.path.isdir(base):
        fs = sorted(os.listdir(base))
        print(base, len(fs))
        for f in fs[-6:]:
            print("   ", f)
