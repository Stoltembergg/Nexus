import os, glob, re, time

def rd(p):
    try:
        return open(p, 'rb').read()
    except OSError:
        return b""

def state(pid):
    try:
        f = open("/proc/%d/stat" % pid).read()
    except OSError:
        return "?"
    return f[f.rfind(')') + 2:].split()[0]

t0 = time.time()
seen = {}
while time.time() - t0 < 45:
    for d in glob.glob("/proc/[0-9]*"):
        pid = int(d.split('/')[-1])
        cmd = rd(d + "/cmdline").replace(b"\x00", b" ").decode('utf-8', 'replace')
        if "Riot Client Helper" not in cmd:
            continue
        if "--type=utility" not in cmd and "CrUtilityMain" not in rd(d + "/comm").decode('utf-8', 'replace'):
            continue
        st = state(pid)
        typ = ""
        m = re.search(r"--utility-sub-type=([\w.\-]+)", cmd)
        if m:
            typ = m.group(1)
        m2 = re.search(r"--type=(\w[\w-]*)", cmd)
        if m2:
            typ += " type=" + m2.group(1)
        key = (pid, typ, st)
        if key not in seen:
            seen[key] = time.time() - t0
            print("t=%5.1fs pid=%d state=%s %s" % (time.time() - t0, pid, st, typ))
    time.sleep(2)
print("done")
