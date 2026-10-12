import os, re, glob, sys

APPPORT = 0xA815   # 43029, the app local HTTP listener
DBG = 0x240D       # 9229, --inspect

def conns(path):
    out = []
    try:
        lines = open(path).read().splitlines()[1:]
    except OSError:
        return out
    for ln in lines:
        f = ln.split()
        if len(f) < 10:
            continue
        def dec(a):
            ip, port = a.split(':')
            return ip, int(port, 16)
        lip, lport = dec(f[1])
        rip, rport = dec(f[2])
        out.append({"local": (lip, lport), "rem": (rip, rport),
                    "st": f[3], "inode": f[9]})
    return out

c = conns("/proc/net/tcp") + conns("/proc/net/tcp6")
rel = [x for x in c if x["local"][1] in (APPPORT, DBG) or x["rem"][1] in (APPPORT, DBG)]
inodes = set(x["inode"] for x in rel)

owner = {}
for d in glob.glob("/proc/[0-9]*"):
    pid = int(d.split('/')[-1])
    try:
        fds = os.listdir(d + "/fd")
    except OSError:
        continue
    for fd in fds:
        try:
            l = os.readlink("%s/fd/%s" % (d, fd))
        except OSError:
            continue
        m = re.match(r"socket:\[(\d+)\]", l)
        if m and m.group(1) in inodes:
            try:
                comm = open(d + "/comm").read().strip()
            except OSError:
                comm = "?"
            owner[m.group(1)] = (pid, comm, fd)

STATES = {"01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV", "04": "FIN_WAIT1",
          "05": "FIN_WAIT2", "06": "TIME_WAIT", "07": "CLOSE", "08": "CLOSE_WAIT",
          "09": "LAST_ACK", "0A": "LISTEN", "0B": "CLOSING"}
print("=== connections involving 43029 (app HTTP) / 9229 (devtools) ===")
for x in sorted(rel, key=lambda y: y["local"][1]):
    o = owner.get(x["inode"], ("?", "?", "?"))
    print("  fd=%-6s %-9s L=%s:%-6d R=%s:%-6d inode=%s owner=%s(%s) %s" % (
        o[2], STATES.get(x["st"], x["st"]),
        x["local"][0], x["local"][1], x["rem"][0], x["rem"][1],
        x["inode"], o[1], o[0], ""))

print("=== network service / utility process state ===")
found = False
for d in glob.glob("/proc/[0-9]*"):
    pid = int(d.split('/')[-1])
    try:
        cmd = open(open(d + "/cmdline", "rb").name if False else d + "/cmdline", "rb").read()
    except OSError:
        cmd = b""
    s = cmd.replace(b"\x00", b" ").decode("utf-8", "replace")
    comm = ""
    try:
        comm = open(d + "/comm").read().strip()
    except OSError:
        pass
    if "NetworkService" in s or comm == "CrUtilityMain":
        found = True
        try:
            st = open(d + "/stat").read().split()[2]
        except OSError:
            st = "?"
        m = re.search(r"--utility-sub-type=([\w.\-]+)", s)
        print("  pid=%d state=%s comm=%s sub=%s" % (pid, st, comm, m.group(1) if m else "?"))
if not found:
    print("  (no network service / utility process found)")
