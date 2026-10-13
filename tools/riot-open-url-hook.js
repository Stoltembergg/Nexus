/* Legacy inspector hook, excluded from normal launches. Offline mocks only in manual testing.
 * Forward Riot's supported external links to the existing host URL spool. */
(() => {
  const electron = process.mainModule.require('electron');
  if (!electron.app.getName().toLowerCase().includes('riot')) return false;
  if (global.__darlingHostUrlHook) return true;
  const fs = process.mainModule.require('fs');
  const original = electron.shell.openExternal.bind(electron.shell);
  let sequence = 0;
  electron.shell.openExternal = (url, options) => {
    let parsed;
    try { parsed = new URL(url); } catch { return original(url, options); }
    if (!['http:', 'https:', 'mailto:'].includes(parsed.protocol)) return original(url, options);
    if (typeof url !== 'string' || url.length > 4096 || /[\x00-\x1f]/.test(url))
      return Promise.reject(new Error('Invalid external URL'));
    return new Promise((resolve, reject) => {
      try {
        const directory = '/private/tmp/rclol-open';
        fs.mkdirSync(directory, {recursive: true});
        const file = `${directory}/electron-${process.pid}-${Date.now()}-${++sequence}.url`;
        fs.writeFileSync(file + '.part', url, {encoding: 'utf8', mode: 0o600});
        fs.renameSync(file + '.part', file);
        resolve();
      } catch { reject(new Error('Host URL handoff failed')); }
    });
  };
  global.__darlingHostUrlHook = true;
  return true;
})()
