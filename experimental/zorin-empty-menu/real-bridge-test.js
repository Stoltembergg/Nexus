import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const dir = GLib.path_get_dirname(GLib.filename_from_uri(import.meta.url)[0]);
// The extension's source is third-party and is not vendored here. The
// ZORIN_DBUSMENU_JS environment variable points at the installed file.
const extension = GLib.getenv('ZORIN_DBUSMENU_JS') ||
    '/usr/share/gnome-shell/extensions/zorin-appindicator@zorinos.com/dbusMenu.js';
const source = new TextDecoder().decode(Gio.File.new_for_path(extension).load_contents(null)[1]);
const body = source.slice(source.indexOf('export class PropertyStore'), source.indexOf('// PART TWO:'))
    .replace(/^export /gm, '');
class IdlePromise {
    constructor() { this.waiting = true; this.promise = new Promise(resolve => GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => { this.waiting = false; resolve(); return GLib.SOURCE_REMOVE; })); }
    pending() { return this.waiting; }
    then(resolve, reject) { return this.promise.then(resolve, reject); }
}
const Util = {CancellableChild: class { constructor() { return new Gio.Cancellable(); } }, Logger: {warn: print, critical: print}};
const [Client, Item] = new Function('GLib', 'Gio', 'GObject', 'Signals', 'DBusProxy', 'Util', 'PromiseUtils', body + '\nreturn [DBusClient, DbusMenuItem];')(
    GLib, Gio, {registerClass: (_info, cls) => cls}, {EventEmitter: class { emit() {} }}, class { emit() {} }, Util, {IdlePromise});
const wait = ms => new Promise(resolve => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { resolve(); return GLib.SOURCE_REMOVE; }));
const assert = (ok, message) => { if (!ok) throw new Error(message); };
function call(proxy, method, args) {
    return new Promise((resolve, reject) => proxy.call(method, args, Gio.DBusCallFlags.NONE, -1, null, (p, r) => {
        try { resolve(p.call_finish(r).deep_unpack()); } catch (e) { reject(e); }
    }));
}
async function run(library, mode) {
    const proc = Gio.Subprocess.new(['python3', `${dir}/bridge_fixture.py`, library, mode], Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE);
    const input = new Gio.DataInputStream({base_stream: proc.get_stdout_pipe()});
    const read = () => new TextDecoder().decode(input.read_line(null)[0]);
    const send = s => proc.get_stdin_pipe().write_all(new TextEncoder().encode(`${s}\n`), null);
    try {
        const name = read();
        const proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES, null, name, '/Menu', 'com.canonical.dbusmenu', null);
        const c = new Client();
        c._items = new Map(); c._items.set(0, new Item(c, 0, {}, []));
        c._active = false; c._flagItemsUpdateRequired = false; c._flagLayoutUpdateRequired = false;
        c._propertiesRequestedFor = new Set(); c._cancellable = new Gio.Cancellable();
        c.GetLayoutAsync = (id, depth, props) => call(proxy, 'GetLayout', new GLib.Variant('(iias)', [id, depth, props]));
        c.GetGroupPropertiesAsync = (ids, props) => call(proxy, 'GetGroupProperties', new GLib.Variant('(aias)', [ids, props]));
        let signals = [];
        proxy.connect('g-signal', (_p, sender, signal, params) => { signals.push(signal); c._onSignal(sender, signal, params); });
        await c._layoutUpdateUpdateAsync(new Gio.Cancellable());
        await wait(200);
        const snapshot = () => c.getRoot().getChildren().map(x => [x.getId(), x.propertyGet('label'), x.propertyGetBool('visible'), x.propertyGetBool('enabled')]);
        const initial = snapshot();
        assert(JSON.stringify(initial) === JSON.stringify([1,2,3,4].map(i => [i, '', mode !== 'hidden', true])), `initial ${JSON.stringify(initial)}`);
        send('update'); assert(read() === 'updated', 'fixture update');
        await wait(200);
        const inactive = snapshot();
        assert(JSON.stringify(inactive) === JSON.stringify(initial), 'inactive cache must remain unchanged');
        assert(c._flagLayoutUpdateRequired && c._flagItemsUpdateRequired === (mode !== 'control'), `flags ${JSON.stringify(signals)}`);
        assert(signals.includes('LayoutUpdated'), `missing layout ${signals}`);
        if (mode !== 'control') assert(signals.includes('ItemsPropertiesUpdated'), `missing properties ${signals}`);
        else assert(!signals.includes('ItemsPropertiesUpdated'), `unexpected properties ${signals}`);
        const flagsInactive = [c._flagLayoutUpdateRequired, c._flagItemsUpdateRequired];
        // Forced importer activation; no Shell popup or visibility decision is exercised.
        c.active = true;
        await wait(300);
        const opened = snapshot();
        const labels = mode === 'control' ? ['', '', '', ''] : ['One','Two','Three',''];
        assert(JSON.stringify(opened) === JSON.stringify([1,2,3,4].map((i) => [i, labels[i-1], mode !== 'hidden', true])), `opened ${JSON.stringify(opened)}`);
        assert(!c._flagItemsUpdateRequired && !c._flagLayoutUpdateRequired, 'flags cleared');
        print(JSON.stringify({mode, signals, initial, inactive, flagsInactive, opened, flagsAfterOpen: [c._flagLayoutUpdateRequired, c._flagItemsUpdateRequired]}));
    } finally { send('quit'); proc.wait(null); }
}
const loop = new GLib.MainLoop(null, false);
let failure;
(async () => { for (let i = 0; i < ARGV.length; i += 2) await run(ARGV[i], ARGV[i+1]); })().catch(e => { failure = e; }).finally(() => loop.quit());
loop.run();
if (failure) throw failure;
