// Load with NODE_OPTIONS=--require=@GUEST_HOME@/riot-stream-hwm.js.
// Under Darling, each async fs stream read costs about 70 ms in the Riot UX
// browser process. Express's 64 KiB default takes about 12 s for renderer.js.
const fs = require('fs');
const original = fs.createReadStream;
fs.createReadStream = function riotAssetReadStream(path, options) {
  if (typeof path === 'string' && path.includes('/app.asar/dist/renderer/')) {
    options = {...options, highWaterMark: 1024 * 1024};
  }
  return original.call(this, path, options);
};
globalThis.__riotStreamHwmLoaded = true;
