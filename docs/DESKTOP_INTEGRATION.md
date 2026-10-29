# Native Linux desktop integration

## Status

The Linux transport and Mach-O/ELF wrapper have isolated protocol/lifecycle
tests. An **experimental, opt-in AppKit adapter** is preserved in
`patches/experimental/cocotron-status-notifier.patch`. This supplemental patch
applies **after** `patches/cocotron.patch` to its pinned cocotron checkout; it is
not part of the production manifest or runtime installer. It does not change
the installed Riot/League runtime or intercept client window closing.

The adapter compiles, and the owned guest probe passed with native item creation,
live menu export, stable menu IDs and main-thread action dispatch. Native DBusMenu
protocol tests pass both directly and through the wrapper. An opt-in real-session
check also passed on KDE: watcher registration, DBusMenu calls through the native
queue and AppKit timer, main-thread action, dynamic AboutToShow refresh, menu
updates and removal from the watcher. This uses D-Bus calls to simulate a panel
client; it does not by itself prove physical rendering or Riot restoration.
The Cocoa popup fallback still has incomplete positioning and `cancelTracking`
is only a stub. Do not install this adapter for everyday use yet.

Manual observation on this KDE session: the user confirmed the neutral green
icon, opening the menu, confirming the action and finishing the test after the
pixmap/theme-priority and `NewMenu` fixes. The final log records two main-thread
actions (`count=1`, `count=2`) and `finished=1 clicks=2 pass=0`. The user explicitly
confirmed clicking twice. Thus physical menu/action behavior is manually
confirmed, with no evidence of a duplicated click in this observation. The
strict exactly-one-action probe still reports failure for that run; it must not
be described as an automated manual-check pass. Earlier incomplete attempts
remain incomplete. A subsequent controlled Riot test confirmed its tray menu and
Settings action after the independent initializer fix described below. Closing
via the outer X still did not hide the client; restore is therefore not validated.
Other desktops remain untested.

The Linux host implementation is in `tools/darling-status-notifier.c`, with a
small C ABI in `tools/darling-status-notifier.h`. It uses GLib/GIO's GDBus API;
the guest must not link against Linux GIO or receive native thread callbacks.

## Build and test

Requires a C compiler and `pkg-config` with `gio-2.0` development files. Protocol
tests additionally need `dbus-run-session` and `gdbus`. Nothing is installed:

```sh
python3 tools/build-status-notifier.py
python3 tools/build-status-notifier-wrapper.py
python3 tools/build-status-notifier-appkit-check.py
python3 -m unittest discover -s tests -p 'test_status_notifier.py' -v
```

The protocol unittests start a private bus and a disposable fake panel. They never register items
on the user's session bus or inspect/operate a Riot process. Coverage includes:

- standard item properties and activation/context/scroll method signatures;
- title/theme-icon changes and bounded ARGB pixmaps;
- invalid UTF-8, malformed scroll directions, and invalid icon dimensions;
- registration when the watcher starts after the application;
- re-registration when the watcher/panel restarts;
- independent items and removal when their private bus connection closes;
- bounded event queues, preserving the most recent 128 events;
- an unavailable session bus returning an error rather than aborting the process.
- DBusMenu layouts, depth/property filtering, submenus, separators, checked
  items, hidden/disabled entries, group methods, stable snapshot IDs and removal;
- rejection of malformed/duplicate IDs, invalid parents, excessive depth, bad
  UTF-8, invalid flags/states and oversized snapshots without replacing a menu;
- click/open events, suppression of disabled ancestors, and asynchronous
  AboutToShow handling without calling guest code from native threads.

Four unittest cases drive these native integration scenarios, including the
same protocol through the wrapper and nonfatal missing/incompatible native
libraries. The wrapper compiles as Mach-O against the real `elfcalls.h`; its
host-side tests supply a loader shim without requiring Darling. The fixture under
`tests/fixtures/status-notifier-watcher.c` is only for the private test bus.

## Architecture and ownership

```text
NSStatusItem / NSStatusBarButton / NSMenu (guest, AppKit main thread)
                 |   experimental adapter + Mach-O/ELF wrapper
                 v
DarlingStatusNotifier C ABI (native Linux transport)
                 |   private GMainContext/thread and D-Bus connection per item
                 v
org.kde.StatusNotifierWatcher -> desktop panel
                 |
                 +-> bounded event queue -> guest main-thread polling
```

The ABI accepts copied UTF-8 strings and pixels, never Objective-C pointers,
selectors, credentials or arbitrary commands. Desktop events enter a bounded
queue; the guest adapter will dispatch actions on the AppKit main thread.
Create/update/destroy calls for one item must be serialized by its owner.
Creation performs a local session-bus handshake; updates synchronize with the
native worker. Host callbacks must never invoke guest code.

The native library has a private D-Bus connection per item, avoiding changes to
another subsystem's shared bus connection. Removing one item does not remove
another. The transport watches the panel's name and re-registers after panel
restart. A full session-bus restart is not yet recovered; it is a separate case
from the panel releasing/reacquiring its name.

## Controlled Riot check and default NSMenuItem initialization

A per-launch AppKit override registered the real Riot Client tray with its own
icon and menu. The user confirmed visibility but observed that commands were
gray. Diagnostics showed an NSApplication was present, automatic enabling was
off, and explicit menu targets/actions were present but disabled. Adding menu
tracking callbacks alone did not resolve this.

The compatibility issue is default `NSMenuItem` initialization: Cocotron had
`initWithTitle:action:keyEquivalent:` (which enables items) but inherited the
plain NSObject `init` (which leaves `_enabled` zero). A default-created item
configured afterward with setters was therefore disabled. The independent
`patches/experimental/cocotron-menu-item-init.patch` forwards `init` to the
designated initializer with empty title/key and NULL action. It applies after
the production cocotron patch, separately from the tray adapter. No client
binary or authentication state is modified.

The owned guest probe covers this construction path and reports:

```text
STATUS_MENU_DEFAULT_INIT enabled=1 empty_title=1 empty_key=1
STATUS_MENU_TRACKING will_open=1 did_close=1 validation=1 deduplicated=1 replacement=1
```

The tray adapter additionally forwards DBusMenu AboutToShow/opened/closed to
main-thread menuWillOpen/menuDidClose and begin/end tracking notifications. It
deduplicates AboutToShow plus opened and closes tracking on menu replacement or
status-item removal. A regression delegate enables commands only while open;
explicitly disabled items are still respected. Optional
`DARLING_STATUS_NOTIFIER_DEBUG=1` logs only validation metadata (application
presence, target/delegate class, action presence and enabled state), not menu
labels, credentials or client requests. This is diagnostic-only and stays off
for ordinary launches.

The real-client retest uses `build/status-notifier-menu-init-stage`, leaving the
installed framework intact. After this fix the real menu exported enabled
commands, and the user confirmed that **Configurações opened the actual client
settings**. The close/restore attempt did not validate restoration: the user
confirmed that clicking the outer X did not dismiss the window at all. The
service process remained the same and there was no observed crash. This is a
separate window-close investigation, not grounds to force-map or forcibly hide
the window. Quitting and game behavior remain unverified; do not describe this
check as a finished desktop integration.

The earlier Riot window decoration inspection established that its main window
is undecorated by the compositor; its visible X may be application-drawn. No
`WM_DELETE_WINDOW` was observed in that test, but that absence does not prove
that the click reached or failed to reach the application's control. Do not
infer close-veto behavior or force hiding from that observation.

An independent owned probe checks `NSWindow performClose:` without mapping a
window: a delegate veto is respected, an allowed close posts a close notification,
and both callbacks run on the main thread. It also sends mouse-down/up directly
to its own unmapped borderless AppKit window, checking that an application-owned
close view receives both events and closes the window with background dragging
both enabled and disabled. It passed with the installed AppKit overlay and with
the experimental staged overlay. The probe also models a draggable parent view
with an overlapping, non-draggable hit-test-passthrough view, verifying that an
owned close action receives down/up. This is a simplified independent model,
not code from or inspection of Electron. This tests AppKit dispatch only; it does not
simulate KDE/X11 input, Electron's view hierarchy or the Riot X, and does not
establish the cause.

```sh
python3 tools/build-window-close-semantics-check.py
```

Run `build/window-close-semantics-check` in Darling using the desired AppKit
override. Expected: `WINDOW_CLOSE_SEMANTICS veto=1 allowed=1 notification=1 main_thread=1`.
Also expected: `WINDOW_CLOSE_CONTROL down=1 up=1 close=1 background_drag_off_on=1`.
Also expected: `WINDOW_CLOSE_PASSTHROUGH overlay=1 draggable_parent=1 action=1`.
Local logs: `build/window-close-control-baseline.log` and
`build/window-close-control-experimental.log`. The next investigation should use
an owned window/input reproduction and, if needed, a user-guided click with
minimal scoped diagnostics, not injected client hooks or forced window mapping.

The initializer fix can be reproduced independently of the tray adapter:

```sh
python3 tools/build-menu-item-init-check.py
```

Run the resulting `build/menu-item-init-check` inside Darling with the patched
AppKit staged as a per-process framework override. It checks `init`, `new`,
`objc_alloc_init`, explicit disabling, separators and the designated initializer,
with no Riot process, tray backend, window, login or network request. Expected:

```text
MENU_ITEM_INIT init=1 new=1 objc_alloc_init=1 explicit_disable=1 separator=1 designated=1
```

## Host-side menu actions

Two entries of the exported tray menu cannot be implemented by the guest
application: ending every process of the game tree, and bringing the client
window back after it was closed. They are therefore owned by the project and
handled on the host, in `tools/darling-menu-actions.c` and
`tools/riot-menu-action.py`.

The menu gains a separator and two entries, **Sair** and **Riot Games**. They
appear only when the experimental transport is active, because the launcher
exports `DARLING_STATUS_MENU_ACTION_SCRIPT` for the session. Without that
variable the menu keeps exactly the entries of the client and every click is
forwarded unchanged. When the client already uses one of those labels, the
project does not add a second entry with the same name: the client's own entry
is handled by the host instead.

- **Sair** asks the session of this prefix to stop through `darling shutdown`.
  Every process of the game tree belongs to that session, so they all end
  with it. Nothing is killed by name, no process outside the prefix is
  touched, and the prefix is the one of the session that started the helper.
  A running match asks for confirmation first; when no confirmation dialog is
  available, the session is left running and the user is told why.
- **Riot Games** brings the client window back without restarting the
  session. The window is looked up in the desktop's managed list and in the
  whole window tree, and it is only touched when its loader socket proves it
  belongs to this prefix. When the window no longer exists the action says so
  and leaves the session alone: **it never restarts the session**.

The labels can be changed with `DARLING_STATUS_MENU_QUIT_LABEL` and
`DARLING_STATUS_MENU_REOPEN_LABEL`; the defaults are `Sair` and
`Riot Games`. `tests/test_menu_actions.py` covers the decision of the native
module and the behaviour of the helper offline, without a desktop, a client
process or the session bus.

Known limits: the reopen action maps and focuses an X11 window directly, so a
window that the client already destroyed cannot be recreated from the host;
the guest would have to create it again. The quit action ends the whole
session, which also ends the game, and it is not a replacement for the
client's own quit when that one works.

## Experimental guest adapter and DBusMenu

Current experimental files:

- `tools/status-notifier-native-wrapper.c`: nonfatal loader and POD forwarding;
- `tools/build-status-notifier-wrapper.py`: builds only, installs nothing;
- `tools/status-notifier-appkit-check.m`: owned guest lifecycle assertions;
- `tools/darling-dbus-menu.c`: Linux DBusMenu protocol and bounded snapshots;
- `tools/build-status-notifier-appkit-check.py`: compiles the guest probe;
- `patches/experimental/cocotron-status-notifier.patch`: preliminary AppKit
  button, lifetime, image and menu changes, not a production-ready patch.

`DARLING_STATUS_NOTIFIER_LIBRARY` must explicitly name the guest-visible Mach-O
wrapper for the backend to run. With it unset, no native library is loaded and
no polling timer is started. The wrapper's native-library path is compiled by
the build helper, not a hardcoded user ID. Desktop events still need panel-to-
guest physical-click/rendering tests. The adapter currently ignores scroll events.

`SetMenu` copies at most 1024 entries with 32 levels and 4096-byte UTF-8 labels.
The host exports `/Menu` and emits `LayoutUpdated` on changed snapshots, plus
`PropertiesChanged` when the SNI Menu path changes. Identical snapshots do not
bump the revision. Empty snapshots remove the SNI menu association. No guest
object or function pointer enters DBusMenu's native thread.

The guest keeps stable, monotonically allocated IDs for live NSMenuItem objects,
revalidates via `NSMenu update` before dispatch, and rejects removed/disabled/
hidden items and disabled/hidden ancestors. Actions use the application's real
target/action with the original item as sender. Removed IDs are never recycled.
Currently `NSMenu` state maps to checkmark/mixed-state properties; radio roles,
icons and shortcuts are not exported.

`AboutToShow` acknowledges immediately with `false`, enqueues a refresh request,
and relies on a subsequent `LayoutUpdated` signal. This avoids blocking the native
thread on AppKit but still needs testing against real panels to verify that a
dynamic first opening updates correctly. No claim of synchronous delegate
validation at panel-open time is made.

Observed guest marker:

```text
STATUS_APPKIT lifecycle=1 live_menu=1 retained_button=1
STATUS_MENU stable_ids=1 main_thread_action=1 disabled_hidden_removed=1
```

Logs for this local validation are in `build/status-notifier-appkit-check.log`
and `build/status-notifier-guest-bridge.log`. Frameworks were staged under
`build/status-notifier-stage`, not installed into the user's prefix.

Remaining before a production adapter:

1. Extend the manually confirmed KDE menu/action test to panel activation,
   menu replacement/removal while displaying an older layout, and other desktops.
2. Verify bus selection with alternate/private buses and already-running guest
   sessions. The desktop check proves that the probe endpoint appears on the
   real host bus; it does not prove private-bus isolation for Darling sessions.
3. Test actual image pixel ordering/alpha, custom Electron subview events,
   absent hosts, timer modes and reentrant menu delegates.
4. Complete or remove the preliminary Cocoa popup fallback and cancellation
   stub. Add appropriate menu notifications and additional menu properties.
5. Keep unsupported desktops recoverable: lack of a tray must never make the
   application inaccessible. Only then test real client close/restore behavior.

## Opt-in desktop protocol check (real KDE session)

Unlike the unittests, this creates a temporary neutral tray item on the actual
desktop. It opens no Riot process and replaces no installed framework. The
experimental adapter must already be applied to the configured source tree and
the AppKit framework built. Build the native library, wrapper and owned probe
with the commands above, then run:

```sh
python3 tools/status-notifier-desktop-check.py --desktop
```

The runner copies AppKit into `build/status-notifier-stage`, uses that override
only for the owned probe, verifies the probe's unique name and title on the host
session bus, and checks registration with the real KDE watcher. It calls DBusMenu
as a panel client would: fetch layout, AboutToShow, disabled-item event, allowed
event and finish. The guest pumps its normal run loop; it does not manually poll
the native event queue. A delegate changes a label at refresh, and the action
changes another label, both checked by the host. Exactly one allowed action must
execute on the AppKit main thread. Finally the connection and watcher entry must
disappear.

Expected marker:

```text
STATUS_DESKTOP_CHECK bus=1 kde_registration=1 dbus_to_guest=1 main_thread=1 about_to_show=1 menu_update=1 removal=1
```

Diagnostics are saved to `build/status-notifier-desktop-check.log`. The probe has
a 30-second guest deadline. On failure, the runner may kill only newly observed
`mldr` processes mapping the exact owned probe binary, after rechecking process
identity. It never shuts down a shared Darling session. It does not click the
panel, assert icon appearance, or test the preliminary Cocoa popup fallback.
`test_status_notifier_desktop_check.py` tests parsing and explicit opt-in safety
offline, without registering a tray item.

For a physical-click check, explicitly select manual mode:

```sh
python3 tools/status-notifier-desktop-check.py --desktop --manual
```

The probe remains for up to three minutes. Find the temporary icon with tooltip
“Teste de bandeja Darling” (possibly under the tray's hidden-items arrow), open
its menu with the right mouse button and select **Confirmar ação de teste** once.
Reopen it and check that the label is now **Ação confirmada** and that **Ação
desabilitada** is gray. Select **Finalizar teste** to remove the icon. This mode
sends no synthetic AboutToShow/Event calls; the panel and user drive the menu.
The guest checks that exactly one action ran on its main thread, and the runner
checks removal from the KDE watcher. A timeout is a failed/incomplete test, not
proof that the desktop integration is broken. Appearance and mouse behavior
still require the user's report; the success marker alone cannot verify pixels.

The neutral icon is a green square with a white center, generated by the owned
AppKit probe. It exports a 22x22 ARGB pixmap with an empty IconName, so a theme's
generic application icon cannot override it. SNI `NewMenu` is emitted when the
menu association appears or disappears; KDE also uses this signal to refresh
its importer, rather than relying solely on `PropertiesChanged`.

Start the manual check from a terminal **when ready to click**. To allow ten
minutes instead of three:

```sh
python3 tools/status-notifier-desktop-check.py --desktop --manual --manual-timeout 600
```

The allowed manual deadline is 30..900 seconds. A timeout or finishing without
the confirmation prints `STATUS_DESKTOP_MANUAL_INCOMPLETE` and exits with code 2,
not a success marker. The runner still checks that the temporary item disappears.

## Application/session integration (separate patch)

Build on `tools/desktop-entry.py` and the graphical launcher
(`scripts/riot-launcher-gui.py`, backed by `scripts/riot-launcher.sh`) rather
than adding another competing desktop installer. Project-shipped names/artwork
must follow the existing neutral branding and trademark policy.

- A desktop activation opens/restores the existing application, not a second
  prefix session or a forced `xdotool windowmap`.
- Closing a window is not quitting an application. Preserve the application's
  delegate/close preference instead of intercepting every `WM_DELETE_WINDOW`.
- A healthy application in the tray is not a stale hidden process. Keep recovery
  helpers and session supervisors from terminating it simply for lacking windows.
- Quit requests follow the application's own actions first. Forced shutdown
  remains a distinct administrative operation with explicit confirmation.
- A running game must not be stopped when its launcher window closes.

Acceptance matrix: open -> close -> tray -> activate -> restored window;
repeated desktop activation -> one session; panel restart -> icon returns;
remove/quit/crash -> no stale icon; absent tray host -> no inaccessible hidden
application; close launcher during a game -> game survives. Validate KDE first,
then other indicator-capable desktops; GNOME without an indicator extension
needs a documented fallback, not a claim of universal tray support.

## Contribution boundary

### Experimental close tracing

`patches/experimental/cocotron-close-trace.patch` is a standalone diagnostic
overlay, not part of the production patch manifest. Apply it only to a Cocotron
source tree already patched with `patches/cocotron.patch`; build and use a
separate test framework, not the installed runtime. With `RCLOL_CLOSE_TRACE=1`,
AppKit/X11 emits `RCLOSE` records for left-button transitions, hit/recipient
view classes, `performClose:` decisions and visibility
changes in window ordering and `setIsVisible:`. Document close decisions may be
asynchronous. Visibility records describe AppKit's visibility flag, not proof
that the window manager displayed a window; other visibility paths are not
instrumented.

The overlay logs no window IDs or identifiers (including Cocotron window
numbers or raw X window IDs); ordered per-process records and view classes can
be used for a single-window reproduction. It does not log coordinates, pointer state, titles,
menu labels, keyboard input, event payloads, actions, or credentials. View class
names can still reveal application structure; handle logs
accordingly. Do not enable `RCLOL_INPUT_TRACE` for this diagnostic: it is a
separate, broader existing trace with different privacy properties. With the
dedicated gate unset or not exactly `1`, this overlay emits no records.

### Experimental status-menu trace

Apply `patches/experimental/cocotron-status-menu-trace.patch` after the base,
status-notifier, menu-item-init and close-trace overlays. Apply
`patches/experimental/status-menu-native-trace.patch` to a disposable copy of
the host sources and build the native library from that copy. Neither belongs
in the production manifest. Enable with `DARLING_STATUS_MENU_TRACE=1` exactly;
other values and an unset variable emit no `SMTRACE` records.

Records contain only numeric menu IDs, fixed event kinds, acceptance/enqueue
or rejection reasons, and sendAction before/after flags for target presence,
action presence and handled status. Rejection reasons include disabled or
hidden submenu parents. Poll records are emitted only for menu events, never
for pointer coordinates. No labels, selectors, action names, titles, keyboard
data or credentials are recorded. Numeric IDs can correlate actions within one
session; treat trace logs as sensitive. This diagnostic does not enable the
separate broader `DARLING_STATUS_NOTIFIER_DEBUG` or `RCLOL_INPUT_TRACE`.

Before any relaunch, obtain the user's confirmation that no game or download is
active. The staged overlay does not change the currently running process.

### Experimental quit and restore breadcrumbs

`patches/experimental/cocotron-status-quit-restore-trace.patch` layers on the
status-menu trace and its prerequisites above, and is not in the production
manifest. With `DARLING_STATUS_MENU_TRACE=1` exactly, `SMQTRACE` records report
menu ID, target/action presence, whether the action is the quit action, AppKit
hidden state and visible-window count. Termination records report entry, the
documents-closed result, numeric delegate reply when present, the boolean reply
decision and exit. The exit breadcrumb flushes stderr. These records contain no
labels, selector names, classes, titles or coordinates. Counts describe AppKit
state, not necessarily what the window manager displays. This is diagnostic
only: no restore fallback or forced window visibility is introduced. Trace logs
remain sensitive because menu IDs can be correlated within a session.

Runtime testing requires fresh confirmation that no game or download is active
and explicit authorization for the Sair test; staging alone is not such a test.

### Bundle icons

The installed Riot Client, League of Legends, and nested LeagueClientUx bundles
each declare `CFBundleIconFile=Icon.icns`. AppKit must preserve an existing
extension when resolving that resource; appending `.icns` unconditionally turns
it into `Icon.icns.icns`. The X11 backend decodes bundle resources and publishes
`_NET_WM_ICON` only when it has image data. Its staged ICNS decoder handles the
Riot Client's PNG-backed `ic08` and the outer League bundle's four legacy
representations. The nested LeagueClientUx bundle's sole `ic08` payload is
JPEG 2000; without an OpenJPEG decoder it remains unsupported, so the staged
code leaves its window icon unset for KDE's generic fallback. No OpenJPEG
dependency or project-owned Darling icon is used to misidentify that client
window. An offscreen Cocotron probe decoded/rendered one Riot Client
representation and four legacy outer-League representations; it decoded none
for LeagueClientUx. In the subsequent authorized staged launch, AppKit, Onyx2D,
and X11 from the new stage were mapped, but the Riot Client window still had no
`_NET_WM_ICON`, despite its bundle resource resolving and decoding offscreen.
That live failure remains unexplained; do not claim the staged window-icon fix
is visually verified. No LeagueClientUx window appeared in that launch, and the
game window itself was not opened.

The experimental StatusNotifier adapter uses an item's own image first, then
`NSApp applicationIconImage`, and falls back to the generic theme icon only
when neither image exists. No client artwork is copied into the repository or
installed client bundles are modified.

The application menu carries one entry per client window class — `Darling
Launcher` (`darling-launcher.desktop`, `RiotClientServices`), `Riot Client`
(`nexus-riot-client.desktop`, `Riot Client`), `League of Legends`
(`nexus-league-client.desktop`, `LeagueClientUx`) and `League of Legends
(match)` (`nexus-league-game.desktop`, `LeagueofLegends`). All four start the
same graphical launcher
(`scripts/riot-launcher-gui.py`); they are window associations, not separate
game targets, and they never start a second prefix session. Each entry uses the
`StartupWMClass` that Darling's AppKit derives from
`-[NSProcessInfo processName]` (the basename of `argv[0]`), so the desktop can
group and decorate the window without any manual step.

The installer never overwrites an entry that belongs to another program: when
a file name is taken by somebody else it writes the entry under a `nexus-`
prefixed name, and it removes entries the project wrote earlier under other
names so the same window is not listed twice.

The icons are **original artwork created for this project**
(`assets/riot-client.svg`, `assets/league-client.svg`,
`assets/league-game.svg`, plus the existing `darling-lol.svg`/`.png`). No game
logo or client artwork is added to the repository or linked to the package, as
required by [compliance](COMPLIANCE.md). The product names in the entry names
and comments are nominative use: they describe the window the entry groups,
and the entries carry no brand artwork and imply no endorsement. A user who
wants other artwork places
an image named `nexus-riot-client`, `nexus-league-client` or
`nexus-league-game` (PNG or SVG) in `~/.local/share/icons/` or
`~/.config/nexus/icons/`; the installer then prefers that image over the
shipped one. See [setup](SETUP.md#graphical-launcher-desktop-entries-and-icons)
for the full procedure. StatusNotifier remains experimental and outside the
production manifest/runtime.

`tools/check-installed-bundle-icons.py` decodes bundle icons in place without
emitting or copying pixels; run it with `build/venv/bin/python3` and explicit
bundle paths. It only verifies image decoding through Pillow; it does not prove
Cocotron can decode the chunks. `tools/check-icns-chunks.py` reports ICNS chunk
formats and validates PNG framing without exposing pixels. The staged
`tools/icns-decoder-check.m` probe exercises Cocotron offscreen and reports only
representation/render counts. None of these checks establishes what KDE
displays. Runtime visual checks require a staged launch and fresh safety
confirmation; they must not start a match.

### KDE task-panel identity

The observed LeagueClientUx window has `WM_CLASS=LeagueClientUx`, but no
`_KDE_NET_WM_DESKTOP_FILE`, `_GTK_APPLICATION_ID`, or startup-notification
identity. The OpenCode desktop entry's `StartupWMClass` is `ai.opencode.desktop`,
and the Darling Launcher entry uses `RiotClientServices`; neither matches
LeagueClientUx. The user reports that Plasma groups this window under OpenCode,
but the available X11 metadata does not explain that association. Do not change
`StartupWMClass` or add a second visible launcher as a speculative workaround;
the task panel's reported application identity must be inspected before making
an association change.

This integration concerns host desktop APIs only. It does not change platform
identity, authentication, account state, telemetry or anti-cheat. No client files,
icons or account logs belong in the patch. See `CONTRIBUTING.md`,
`COMPLIANCE.md` and `INTEROPERABILITY.md` before submitting.
