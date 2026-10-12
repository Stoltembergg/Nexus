#!/usr/bin/env bash
# darling-lol M58o: control experiment — is the browser main-process loop
# delay specific to the Riot UX, or general Electron-on-Darling?
#
# Runs a minimal Electron app (no window, then with a window loading a
# 10 MB HTTP asset from its own in-process server) under the stock
# Electron.app and measures the main-process loop with
# tools/m58n-browser-loop-latency.py.
#
# Result (2026-09-23): stock Electron is NORMAL in both cases
#   setTimeout1000 -> 1025 ms (no window) / 1065 ms (window + 10 MB asset)
#   fs_read        ->   87 ms / 173 ms
# while the Riot UX main process is 1.9-13 s. So the defect is specific to
# the Riot Client UX app, not Electron, the window, the HTTP server, the
# asset size, or any guest primitive.
set -u
ELECTRON=@DPREFIX@/Applications/Electron.app/Contents/MacOS/Electron
PROBE="$(cd "$(dirname "$0")" && pwd)/m58n-browser-loop-latency.py"
work=/tmp/opencode/m58o; rm -rf "$work"; mkdir -p "$work/elmin" "$work/elwin"

cat > "$work/elmin/package.json" <<'EOF'
{ "name": "elmin", "version": "1.0.0", "main": "main.js" }
EOF
cat > "$work/elmin/main.js" <<'EOF'
const { app } = require('electron');
app.disableHardwareAcceleration();
app.whenReady().then(() => { console.log('ELMIN ready'); setInterval(() => {}, 60000); });
EOF

cat > "$work/elwin/package.json" <<'EOF'
{ "name": "elwin", "version": "1.0.0", "main": "main.js" }
EOF
cat > "$work/elwin/main.js" <<'EOF'
const { app, BrowserWindow } = require('electron');
const http = require('http');
app.disableHardwareAcceleration();
app.whenReady().then(() => {
  const big = Buffer.alloc(10 * 1024 * 1024, 65);
  const srv = http.createServer((q, s) => {
    if (q.url === '/big') { s.writeHead(200, { 'Content-Length': big.length }); s.end(big); }
    else { const b = Buffer.from('<html><body><script src="/big"></script>hello</body></html>');
           s.writeHead(200, { 'Content-Type': 'text/html', 'Content-Length': b.length }); s.end(b); }
  });
  srv.listen(0, '127.0.0.1', () => {
    const p = srv.address().port;
    const w = new BrowserWindow({ show: false, width: 800, height: 600 });
    w.loadURL('http://127.0.0.1:' + p + '/');
    console.log('ELWIN listening ' + p);
  });
  setInterval(() => {}, 60000);
});
EOF

for app in elmin elwin; do
  echo "===== stock Electron: $app ====="
  /tmp/opencode/cleandarling.sh >/dev/null 2>&1
  setsid darling "$ELECTRON" "/Volumes/SystemRoot$work/$app" --inspect=9229 \
      > "$work/$app.log" 2>&1 &
  sleep 72
  timeout 90 python3 "$PROBE" 2>&1 | head -3
  pkill -9 -x mldr 2>/dev/null; pkill -9 -x darlingserver 2>/dev/null
  pkill -9 -x launchd 2>/dev/null; pkill -9 -x darling 2>/dev/null
done
/tmp/opencode/cleandarling.sh >/dev/null 2>&1
echo "done"
