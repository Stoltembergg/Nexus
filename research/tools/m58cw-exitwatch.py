import os, glob, time, re

def rd(p):
    try:
        return open(p).read()
    except OSError:
        return ""

def comm(pid):
    return rd("/proc/%d/comm" % pid).strip()

def fields(pid):
    f = rd("/proc/%d/stat" % pid)
    if not f:
        return None
    i = f.rfind(')')
    return f[i + 2:].split()

def browser():
    for d in glob.glob("/proc/[0-9]*"):
        if comm(int(d.split('/')[-1])) == "CrBrowserMain":
            return int(d.split('/')[-1])
    return None

bp = None
seen = {}
t0 = time.time()
while time.time() - t0 < 75:
    if bp is None:
        bp = browser()
    if bp is None:
        time.sleep(0.15)
        continue
    # discover utilities (children of browser)
    for d in glob.glob("/proc/[0-9]*"):
        pid = int(d.split('/')[-1])
        if comm(pid) != "CrUtilityMain" and pid not in seen:
            continue
        st = fields(pid)
        if st is None:
            continue
        if len(st) < 2 or int(st[1]) != bp:
            continue
        sub = ""
        cm = rd("/proc/%d/cmdline" % pid).replace("\x00", " ")
        m = re.search(r"--utility-sub-type=([\w.\-]+)", cm)
        if m:
            sub = m.group(1)
        key = (st[0], sub)
        if seen.get(pid) != key:
            seen[pid] = key
            # field N -> rest[N-3]: wchan=35->32, exit_signal=38->35, exit_code=52->49
            wchan = st[32] if len(st) > 32 else "?"
            xsig = st[35] if len(st) > 35 else "?"
            xcod = st[49] if len(st) > 49 else "?"
            print("t=%6.2fs pid=%d state=%s sub=%s wchan=%s exit_sig=%s exit_code=%s"
                  % (time.time() - t0, pid, st[0], sub or "-", wchan, xsig, xcod))
    time.sleep(0.15)
print("done; utilities seen:", sorted(seen.keys()))
