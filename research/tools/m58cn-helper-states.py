import os, re, glob

def rd(p):
    try:
        return open(p, 'rb').read()
    except OSError:
        return b""

def stat(pid):
    try:
        f = open("/proc/%d/stat" % pid).read()
    except OSError:
        return None
    # comm may contain spaces/parens; take after last ')'
    i = f.rfind(')')
    rest = f[i+2:].split()
    return {"state": rest[0], "ppid": int(rest[1])}

rows = []
for d in glob.glob("/proc/[0-9]*"):
    pid = int(d.split('/')[-1])
    cmd = rd(d + "/cmdline").replace(b"\x00", b" ").decode('utf-8', 'replace').strip()
    comm = rd(d + "/comm").decode('utf-8', 'replace').strip()
    if ("Riot Client Helper" not in cmd and not comm.startswith("Cr")
            and "Riot Client.app/Contents/MacOS/Riot Client" not in cmd):
        continue
    st = stat(pid)
    if st is None:
        continue
    typ = ""
    m = re.search(r"--type=([\w-]+)", cmd)
    if m:
        typ = m.group(1)
    m2 = re.search(r"--utility-sub-type=([\w.\-]+)", cmd)
    if m2:
        typ += " sub=" + m2.group(1)
    rows.append((pid, st["ppid"], st["state"], comm, typ))

print("pid        ppid       st  comm             type")
for pid, ppid, state, comm, typ in sorted(rows):
    print("%-10d %-10d %-3s %-16s %s" % (pid, ppid, state, comm, typ))
zom = [r for r in rows if r[2] == 'Z']
print("ZOMBIES: %d %s" % (len(zom), [(r[0], r[4]) for r in zom]))
