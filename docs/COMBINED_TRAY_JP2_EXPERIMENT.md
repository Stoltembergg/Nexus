# Combined tray / JP2 experiment (x86-64, opt-in)

This isolated stage is `build/tray-jp2-experiment`. It combines the existing
title/count diagnostic AppKit, the existing experimental JP2 Onyx2D and its
Mach-O OpenJPEG wrapper, and a newly built Mach-O status wrapper bound to the
corrected native DBusMenu library in this stage. The host wrapper's absolute
path is compiled in, so moving the tree requires rebuilding it. It loads the
host's `libopenjp2.so`; this is not a packaged or production build. The JP2
decoder's narrow input restrictions and limitations are in
`ICNS_JP2_EXPERIMENT.md`. SMCOUNT records may disclose activity; see
`STATUS_MENU_COUNT_DIAGNOSTIC.md` before enabling them.

The following command is provided for review only. **Do not run it until an
explicitly authorized restart/test.** It retains the specified normal runner,
flags, default guest runtime fallback paths, and region/locale; it assumes the
normal guest home (`/Users/<user>`), not an alternate `RIOT_GUEST_HOME` or custom
DYLD paths. `run.sh` itself invokes the normal configuration step and runner;
this experiment did not execute it or modify the installed runtime. It may
reuse an already-running Darling namespace, and existing processes cannot be
retroactively changed. Do not stop any existing namespace to force loading.

The paths below use `$REPO` for the repository root and `$HOME` for the user's
home directory. Replace them with the real values before running the command.

```sh
REPO="$PWD"
env RCLOL_GAMEMODE=0 RCLOL_REGION=BR RCLOL_LOCALE=pt_BR RCLOL_CLEAN_ON_EXIT=0 \
  DYLD_FRAMEWORK_PATH="/Volumes/SystemRoot$REPO/build/tray-jp2-experiment:/Users/gabriel/RuntimeFrameworks" \
  DYLD_LIBRARY_PATH="/Volumes/SystemRoot$REPO/build/tray-jp2-experiment:/Users/gabriel/RuntimeLibraries" \
  DARLING_STATUS_NOTIFIER_LIBRARY="/Volumes/SystemRoot$REPO/build/tray-jp2-experiment/libDarlingStatusNotifier.dylib" \
  DARLING_STATUS_MENU_COUNT_TRACE=1 \
  "$REPO/scripts/run.sh"
```

Note that the `/Users/<user>` paths above are guest-side paths inside the
macOS emulation, not host paths. The guest home directory is configurable
through `RIOT_GUEST_HOME`; the runtime prints the effective value.

Rollback is simply to omit these four experiment environment variables and use
the normal command with its four RCLOL settings; `env` scopes the experiment to
the launched process and descendants. This does not remove the override from
processes already started with it; their lifecycle needs separate authorization.
No shutdown or deletion is required for rollback. If those DYLD variables were
already intentionally configured in the caller's environment, retain their normal
values instead of assuming they were unset.

Focused validation: `experimental/dbusmenu-properties/run-tests.sh` passed its
native and private wire tests. `dbus-run-session -- python3
experimental/dbusmenu-properties/combined-check.py` passed the neutral guest
watcher/menu transition, a diagnostic AppKit probe with staged AppKit confirmed
by dyld and SMCOUNT enabled, and the synthetic RGB/RGBA/malformed ICNS probe
with staged Onyx2D and OpenJPEG confirmed by dyld. Each invocation uses its own
bus and freshly reserved prefix, and requires identity-checked shutdown of only
that prefix; root-owned prefix directories are retained. A first invocation with
an overbroad AppKit assertion on the ICNS-only executable failed; its owned
namespace was also cleaned up. The final check separates the AppKit and ICNS
probes. No real desktop, Riot or client menu was tested: the DBusMenu fix remains
a hypothesis for the real client and is not proof of panel rendering.
