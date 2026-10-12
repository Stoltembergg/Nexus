import os, re, glob, json, urllib.request

PORTS = {39061: "app-port", 43029: "http2", 9229: "devtools"}

def dec(a):
    ip, port = a.split(':')
    return ip, int(port, 16)

def conns():
    out = []
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = open(path).read().splitlines()[1:]
        except OSError:
            continue
        for ln in lines:
            f = ln.split()
            if len(f) < 10:
                continue
            lip, lport = dec(f[1])
            rip, rport = dec(f[2])
            out.append((lip, lport, rip, rport, f[3], f[9]))
    return out

def main():
    c = conns()
    rel = [x for x in c if x[1] in PORTS or x[3] in PORTS]
    inodes = set(x[5] for x in rel)
    owner = {}
    for d in glob.glob('/proc/[0-9]*'):
        try:
            for fd in os.listdir(d + '/fd'):
                try:
                    l = os.readlink('%s/fd/%s' % (d, fd))
                except OSError:
                    continue
                m = re.match(r'socket:\[(\d+)\]', l)
                if m and m.group(1) in inodes:
                    try:
                        comm = open(d + '/comm').read().strip()
                    except OSError:
                        comm = '?'
                    owner[m.group(1)] = (d.split('/')[-1], comm, fd)
        except OSError:
            continue
    ST = {'01': 'ESTAB', '02': 'SYN_SENT', '03': 'SYN_RECV', '08': 'CLOSE_WAIT', '0A': 'LISTEN', '06': 'TIME_WAIT'}
    print("  connections on app/devtools ports:")
    for x in sorted(rel, key=lambda y: (y[1], y[3])):
        o = owner.get(x[5], ('?', '?', '?'))
        print("    L=%s:%-6d R=%s:%-6d %-10s pid=%s(%s)" % (
            x[0], x[1], x[2], x[3], ST.get(x[4], x[4]), o[0], o[1]))
    print("  utility/network-service processes:")
    for d in glob.glob('/proc/[0-9]*'):
        comm = ''
        try:
            comm = open(d + '/comm').read().strip()
        except OSError:
            pass
        if comm != 'CrUtilityMain':
            continue
        try:
            st = open(d + '/stat').read().split()[2]
        except OSError:
            st = '?'
        print("    pid=%s state=%s" % (d.split('/')[-1], st))
    # CDP page state
    try:
        d = json.load(urllib.request.urlopen("http://127.0.0.1:9229/json/list", timeout=4))
        u = next(t["webSocketDebuggerUrl"] for t in d if t.get("webSocketDebuggerUrl"))
        import websocket
        ws = websocket.create_connection(u, timeout=8)
        js = ("(async()=>{const{BrowserWindow}=process.mainModule.require('electron');"
              "const w=BrowserWindow.getAllWindows()[0];"
              "try{return JSON.stringify({loading:w.webContents.isLoading(),vis:w.isVisible(),"
              "url:w.webContents.getURL().slice(0,60),"
              "js:await Promise.race([w.webContents.executeJavaScript('document.readyState')"
              ".then(v=>v),new Promise(z=>setTimeout(()=>z('TIMEOUT'),4000))])})}catch(e){return 'ERR:'+e}})()")
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": js, "returnByValue": True, "awaitPromise": True}}))
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                print("  CDP:", m.get("result", {}).get("result", {}).get("value", m.get("result")))
                break
    except Exception as e:
        print("  CDP: ERROR", e)

main()
