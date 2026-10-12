// Isolate Darwin libuv TCP throughput from Electron's GUI and compositor.
const net = require('net');
const size = 16 * 1024 * 1024;
const chunk = Buffer.alloc(64 * 1024, 0x41);
let sent = 0;
let received = 0;
const started = Date.now();
const timer = setTimeout(() => {
  console.log(JSON.stringify({stalled: true, sent, received, ms: Date.now() - started}));
  process.exit(2);
}, 30000);
const server = net.createServer(socket => {
  const pump = () => {
    while (sent < size) {
      const n = Math.min(chunk.length, size - sent);
      const writable = socket.write(chunk.subarray(0, n));
      sent += n;
      if (!writable) {
        socket.once('drain', pump);
        return;
      }
    }
    socket.end();
  };
  pump();
});
server.listen(0, '127.0.0.1', () => {
  const client = net.connect(server.address().port, '127.0.0.1');
  client.on('data', data => { received += data.length; });
  client.on('end', () => {
    clearTimeout(timer);
    const ms = Date.now() - started;
    console.log(JSON.stringify({sent, received, ms,
      MiBps: +(received / 1048576 / (ms / 1000)).toFixed(2)}));
    server.close();
  });
  client.on('error', error => { console.error(error); process.exit(1); });
});
