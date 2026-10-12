import os, re, glob, time

def rd(p):
    try:
        return open(p).read()
    except OSError:
        return ""

def dec(a):
    ip, port = a.split(':')
    return ip, int(port, 16)

def tcp():
    out = []
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        for ln in open(path).read().splitlines()[1:]:
            f = ln.split()
            if len(f) < 10:
                continue
            lip, lport = dec(f[1])
            rip, rport = dec(f[2])
            out.append((lip, lport, rip, rport, f[3], f[9]))
    return out

def browser():
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if open(d + "/comm").read().strip() == "CrBrowserMain":
                return int(d.split('/')[-1])
        except OSError:
            pass
    return None

STATES = {'01': 'ESTAB', '02': 'SYN_SENT', '03': 'SYN_RECV', '06': 'TIME_WAIT',
          '08': 'CLOSE_WAIT', '0A': 'LISTEN'}
t0 = time.time()
bp = None
listen_ports = set()
while time.time() - t0 < 80:
    if bp is None:
        bp = browser()
    conns = tcp()
    if bp:
        # browser fd -> listen ports (non-devtools)
        ino2conn = {c[5]: c for c in conns}
        for fd in os.listdir("/proc/%d/fd" % bp):
            try:
                l = os.readlink("/proc/%d/fd/%s" % (bp, fd))
            except OSError:
                continue
            m = re.match(r'socket:\[(\d+)\]', l)
            if m and m.group(1) in ino2conn:
                c = ino2conn[m.group(1)]
                if c[4] == '0A' and c[1] not in (9229,):
                    listen_ports.add(c[1])
    interesting = [c for c in conns if c[1] in listen_ports or c[3] in listen_ports]
    util = []
    for d in glob.glob("/proc/[0-9]*"):
        if rd(d + "/comm").strip() == "CrUtilityMain":
            f = rd(d + "/stat")
            util.append("%s:%s" % (d.split('/')[-1], f[f.rfind(')') + 2:].split()[0] if f else '?'))
    active = [c for c in interesting if c[4] != '0A']
    print("t=%4.0fs listen=%s netsvc=%s" % (time.time() - t0, sorted(listen_ports), util or ["none"]))
    if active:
        for c in active:
            print("      %s:%-6d -> %s:%-6d %s" % (c[0], c[1], c[2], c[3], STATES.get(c[4], c[4])))
    elif listen_ports:
        print("      (no client connection on the static-server port yet)")
    time.sleep(3)
print("done")
