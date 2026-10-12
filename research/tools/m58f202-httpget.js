// Measure a guest Node HTTP client against the Riot UX static server.
const http = require('http');
const url = process.argv[2];
const started = Date.now();
let bytes = 0;
const request = http.get(url, response => {
  response.on('data', chunk => { bytes += chunk.length; });
  response.on('end', () => {
    const ms = Date.now() - started;
    console.log(JSON.stringify({status: response.statusCode, bytes, ms,
      MiBps: +(bytes / 1048576 / (ms / 1000)).toFixed(2)}));
  });
});
request.on('error', error => { console.error(error); process.exitCode = 1; });
request.setTimeout(30000, () => {
  console.log(JSON.stringify({timeout: true, bytes, ms: Date.now() - started}));
  request.destroy();
});
