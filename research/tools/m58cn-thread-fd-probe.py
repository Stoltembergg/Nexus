import os, re, sys, time

def read(p, dflt=""):
    try:
        return open(p).read().strip()
    except OSError:
        return dflt

def readlink(p, dflt=""):
    try:
        return os.readlink(p)
    except OSError:
        return dflt

def parse_net(path, kind):
    """return {inode: description}"""
    out = {}
    try:
        lines = open(path).read().splitlines()[1:]
    except OSError:
        return out
    for ln in lines:
        f = ln.split()
        if kind == "tcp":
            if len(f) < 10:
                continue
            inode = f[9]
            out[inode] = "tcp %s -> %s st=%s" % (f[1], f[2], f[3])
        elif kind == "unix":
            if len(f) < 7:
                continue
            inode = f[6]
            path = f[7] if len(f) > 7 else "(anon)"
            out[inode] = "unix %s type=%s" % (path, f[4])
    return out

def classify(link, tcp, unix):
    m = re.match(r"socket:\[(\d+)\]", link)
    if not m:
        return link
    ino = m.group(1)
    if ino in tcp:
        return tcp[ino]
    if ino in unix:
        return unix[ino]
    return "socket:[%s] (?)" % ino

tcp = parse_net("/proc/net/tcp", "tcp")
tcp6 = parse_net("/proc/net/tcp6", "tcp")
unix = parse_net("/proc/net/unix", "unix")
for k, v in tcp6.items():
    tcp.setdefault(k, v)

def show(pid):
    comm = read("/proc/%d/comm" % pid)
    state = "?"
    try:
        state = open("/proc/%d/stat" % pid).read().split()[2]
    except OSError:
        pass
    wchan = read("/proc/%d/wchan" % pid)
    sc = read("/proc/%d/task/%d/syscall" % (pid, pid))
    print("### %s host=%d state=%s wchan=%s" % (comm, pid, state, wchan))
    if sc:
        parts = sc.split()
        print("  main syscall nr=%s args=%s" % (parts[0], " ".join(parts[1:7])))
    else:
        print("  main syscall: (unreadable)")
    # fd table of the process, restricted to sockets
    try:
        fds = sorted(int(x) for x in os.listdir("/proc/%d/fd" % pid))
    except OSError:
        fds = []
    for fd in fds:
        link = readlink("/proc/%d/fd/%d" % (pid, fd))
        if link.startswith("socket:"):
            print("  fd=%-3d %s" % (fd, classify(link, tcp, unix)))

pids = []
for c in ("CrBrowserMain", "CrRendererMain", "CrGpuMain", "CrUtilityMain"):
    try:
        out = os.popen("pgrep -x %s" % c).read().split()
    except Exception:
        out = []
    for p in out:
        pids.append((c, int(p)))
for c, p in pids:
    show(p)
