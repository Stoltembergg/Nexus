const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(__dirname + '/riot-open-url-hook.js', 'utf8');
function fixture({fail = false, name = 'Riot Client'} = {}) {
  const writes = [], original = [];
  const electron = {app: {getName: () => name}, shell: {openExternal: async (...args) => {original.push(args);}}};
  const filesystem = {
    mkdirSync: p => assert.equal(p, '/private/tmp/rclol-open'),
    writeFileSync: (p, url, options) => {if (fail) throw Error('fixture failure'); writes.push({p, url, options});},
    renameSync: (from, to) => {assert.equal(from, to + '.part'); assert.ok(to.endsWith('.url'));},
  };
  const modules = {electron, fs: filesystem};
  const context = {global: {}, process: {pid: 123, mainModule: {require: name => modules[name]}}, URL, Promise};
  const installed = vm.runInNewContext(source, context);
  return {electron, writes, original, context, installed};
}
(async () => {
  const f = fixture(); assert.equal(f.installed, true);
  for (const url of ['https://example.invalid/download/', 'http://example.invalid/', 'mailto:test@example.invalid'])
    await f.electron.shell.openExternal(url);
  assert.equal(f.writes.length, 3); assert.equal(f.original.length, 0);
  assert.ok(f.writes.every(w => w.options.mode === 0o600));
  assert.equal(new Set(f.writes.map(w => w.p)).size, 3);
  await f.electron.shell.openExternal('file:///fixture/example');
  assert.equal(f.original.length, 1);
  await assert.rejects(f.electron.shell.openExternal('https://example.invalid/\n'), /Invalid external URL/);
  await assert.rejects(f.electron.shell.openExternal('https://example.invalid/' + 'a'.repeat(4096)), /Invalid external URL/);
  const broken = fixture({fail: true});
  await assert.rejects(broken.electron.shell.openExternal('https://example.invalid/'), /Host URL handoff failed/);
  const saved = f.electron.shell.openExternal;
  assert.equal(vm.runInNewContext(source, f.context), true); assert.equal(f.electron.shell.openExternal, saved);
  const unrelated = fixture({name: 'Other App'}); assert.equal(unrelated.installed, false);
  console.log('RIOT_OPEN_URL allowed_schemes=3 fallback=1 invalid_rejected=1 failure_reported=1 idempotent=1 scoped=1');
})().catch(error => {console.error(error); process.exitCode = 1;});
