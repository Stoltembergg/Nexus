import Gio from 'gi://Gio';

function read(path) {
    return new TextDecoder().decode(Gio.File.new_for_path(path).load_contents(null)[1]);
}
function load(path) {
    const source = read(path);
    // Compile the entire file (without module declarations) for syntax checking.
    new Function(source.replace(/^import .*;\n/gm, '').replace(/^export /gm, ''));
    const start = source.indexOf('export const DBusClient =');
    const end = source.indexOf('\n// ////////////////////////////////////////////////////////////////////////\n// PART TWO', start);
    const body = source.slice(start, end).replace('export const DBusClient =', 'return');
    return new Function('GObject', 'DBusProxy', 'Util', 'Gio', 'PromiseUtils', body)(
        {registerClass: (_info, cls) => cls}, class {},
        {CancellableChild: class {}}, Gio, {});
}
function assert(value, message) { if (!value) throw new Error(message); }
function item(id, visible, type = 'standard') {
    return {id, visible, type, propertyGet: () => type,
        propertyGetBool: () => visible,
        propertySet(name, value) { if (name === 'visible') this.visible = value === null || value; },
    };
}
function client(Class, children) {
    const c = new Class();
    c._items = new Map(children.map(x => [x.id, x]));
    c._items.set(0, {hasChildren: () => children.length > 0,
        getChildrenIds: () => children.map(x => x.id)});
    c._active = false;
    c._requestLayoutUpdate = () => c.layouts++;
    c._doPropertiesUpdate = () => c.propertyRefreshes++;
    c.layouts = 0; c.propertyRefreshes = 0;
    return c;
}
const params = value => ({deep_unpack: () => value});
function hiddenToVisible(Class) {
    const child = item(1, false);
    const c = client(Class, [child]);
    c._onSignal(null, 'ItemsPropertiesUpdated', params([[[1, {visible: true}]], []]));
    return {child, c};
}
// The extension's source is third-party and is not vendored in this
// repository. The caller passes the installed original and a patched copy
// prepared in a temporary directory by run-test.py.
if (ARGV.length < 2)
    throw new Error('usage: test.js <original dbusMenu.js> <patched dbusMenu.js>');
const Original = load(ARGV[0]);
const Patched = load(ARGV[1]);
let {child, c} = hiddenToVisible(Original);
assert(!child.visible && c._flagItemsUpdateRequired, 'baseline must reproduce deadlock');
({child, c} = hiddenToVisible(Patched));
assert(child.visible && !c._flagItemsUpdateRequired, 'hidden item must become visible');
c = client(Patched, [item(1, false)]);
c._onSignal(null, 'LayoutUpdated');
assert(c.layouts === 1, 'hidden layout must refresh');
c = client(Patched, [item(1, true)]);
c._onSignal(null, 'LayoutUpdated');
c._onSignal(null, 'LayoutUpdated');
c._onSignal(null, 'ItemsPropertiesUpdated', params([[], []]));
assert(c.layouts === 0 && c._flagLayoutUpdateRequired && c._flagItemsUpdateRequired, 'normal menu defers');
c.active = true; c.active = true;
assert(c.layouts === 1 && c.propertyRefreshes === 0, 'activation coalesces with layout precedence');
c = client(Patched, [item(1, true)]);
c._onSignal(null, 'ItemsPropertiesUpdated', params([[], []]));
c.active = true; c.active = false; c.active = true;
assert(c.propertyRefreshes === 1 && !c._flagItemsUpdateRequired, 'property refresh once per activation');
c = client(Patched, [item(1, true, 'separator')]);
c._onSignal(null, 'LayoutUpdated');
assert(c.layouts === 1, 'separator-only popup is empty');
c = client(Patched, [item(1, false)]);
c._onSignal(null, 'ItemsPropertiesUpdated', params([[], [[1, ['visible']]]]));
assert(c._items.get(1).visible, 'removed visible defaults to true');
c = client(Patched, [item(1, false)]);
c._items.delete(1);
c._onSignal(null, 'LayoutUpdated');
assert(c.layouts === 0 && c._flagLayoutUpdateRequired, 'unknown cache conservatively defers');
c = client(Patched, []);
c._onSignal(null, 'LayoutUpdated');
assert(c.layouts === 1, 'empty root refreshes');
// Exercise the actual async layout cancellation/ownership logic without D-Bus.
c = client(Patched, []);
let requests = [];
c.GetLayoutAsync = (_id, _depth, _props, cancel) => new Promise((resolve, reject) => {
    cancel.reject = reject;
    requests.push(resolve);
});
c._updateLayoutState = () => {};
c._doLayoutUpdate = () => {};
c._gcItems = () => {};
const cancelled = {matches: () => true};
const first = {cancel() { this.reject(cancelled); }};
const second = {cancel() { this.reject(cancelled); }};
const p1 = c._layoutUpdateUpdateAsync(first).catch(e => e);
const p2 = c._layoutUpdateUpdateAsync(second);
assert(await p1 === cancelled && c._layoutUpdateCancellable === second,
    'superseded request cannot clear newer cancellable');
requests[1]([0, []]);
await p2;
assert(c._layoutUpdateCancellable === null, 'completed request clears its cancellable');
print('PASS baseline reproduction, patched visibility/layout, deferral, coalescing, cache and async cancellation');
