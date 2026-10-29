# Experimental reopen probe (opt-in)

## Isolated preparation (no guest)

`prepare.py` takes a **nonexistent** output directory outside the Nexus and
Cocotron trees. It archives the committed `AppKit` from a Cocotron git checkout
(not its working tree or a scratch stage), applies the status-notifier and
reopen patches in order, and records the revision and limitations in a manifest.
It requires Python 3, git, tar and patch. Specify `--source` if the default
`build/darling-src/src/external/cocotron` checkout is unavailable. Failed
preparation leaves partial output for inspection; use a different path to retry.

```
python3 experimental/reopen-probe/prepare.py /tmp/reopen-isolated
python3 -m unittest discover -s tests -p test_reopen_isolation.py
```

Optionally add `--compile --sdk /path/to/sdk --flags-file /path/to/flags.make`.
This attempts to compile the real experimental native library, its Mach-O
wrapper, and the existing standalone neutral probe, requiring cc, pkg-config
with gio-2.0, clang/lld, the SDK, Darling elfcalls headers and existing AppKit
build flags. All outputs stay under the new directory. The probe links against
the supplied SDK, **not** the patched AppKit source: this command does not build
AppKit, install anything, start a guest, or change the session.
The wrapper embeds the isolated native library's absolute path. Existing
`run.py` is for the separate standalone probe, not this preparation.

### Isolated AppKit relink

With a complete, up-to-date Makefile build and its matching installed framework:

```
python3 experimental/reopen-probe/build-appkit.py /tmp/reopen-appkit \
  --framework /usr/local/libexec/darling/System/Library/Frameworks/AppKit.framework
```

This copies the actual build's AppKit working tree, applies both patches, uses
dependency files to recompile patched sources and consumers of changed existing
headers (including the status-item ivars), and relinks with remaining existing
objects read-only. It rejects missing or stale dependencies and mismatched
framework binaries. The framework and resources are copied, then the isolated
binary is replaced; resource contents and dispatch markers are checked before
writing the success manifest. `llvm-nm` is required for method-symbol checks.
Partial output is retained on failure and is not
marked successful. Build inputs include the local working tree and toolchain,
not solely the git revision; this is not a hermetic rebuild. The link emits
existing duplicate-category warnings. Presence checks are not runtime proof.
No probe is linked to this framework or run, and transport-to-guest delivery,
framework loading and window restoration remain unproven.

This standalone, neutral guest process directly schedules Cocotron's private
`NSApplication _reopen` on the main run loop. Its delegate records
`applicationShouldHandleReopen:hasVisibleWindows:` for return values NO and YES;
it checks one main-thread callback per call. It creates no windows and does not
modify production code or attach to an existing process. The reported `visible`
value is an observation, not an assertion that it reflects actual windows.
It does not establish delivery of real desktop reopen events or the effects of
the return value on hidden/visible windows.

Requires the existing Nexus Cocotron build, SDK and clang/lld, plus a working
Darling guest and display. From the repository root, explicitly run:

```
python3 experimental/reopen-probe/build.py
python3 experimental/reopen-probe/run.py
```

Build outputs go to `build/reopen-probe/`. The run creates a fresh private prefix
via the existing `ProbePrefix` helper, never the current session's prefix. Its
fail-closed cleanup stops only a verified owned server and retains the prefix;
if startup or ownership verification fails, cleanup reports the path and fails
instead of touching another session. On timeout the process is not killed and
the private prefix is retained without attempting shutdown. No installation or session restart is
performed. `REOPEN_PASS` and exit 0 indicate the limited callback checks passed;
errors, timeouts, unavailable selectors, or cleanup failures are not successes.

Previous experimental run: both callbacks were observed on the main thread,
with `visible=1` and answers NO and YES, but Darling timed out after reporting
`REOPEN_PASS`, and the runner's attempted kill failed with `PermissionError`.
This is partial evidence, not an overall successful run. The private prefix was
retained; do not assume it is safe to remove or stop without independent
ownership verification.

## Native transport experiment

Independently, `python3 experimental/reopen-probe/build-transport.py OUTPUT_DIRECTORY`
copies the real native transport sources and applies two exact, single-match
edits to the menu producer and one append-only enum edit. It fails closed if the
expected source changes. Reopen, identified by existing ID/label action logic,
queues kind 8 with its originating ID only when enabled and visible (including
ancestors). Quit continues to invoke the existing helper; ordinary clicks keep
kind 5. This is a proposal, not a production change.

Run `python3 -m unittest discover -s tests -p test_reopen_transport.py`. The test
starts a private D-Bus, builds the real native producer variant, and uses a
harmless temporary helper for quit. No guest or real session is started. Only
transport through `DarlingStatusNotifierPoll` is proven: guest dispatch and
actual window restoration have not been tested or implemented by this transport
experiment. The standalone AppKit probe above is a separate, limited observation
and does not prove transport-to-guest delivery.

## Guest patch variant

`cocotron-reopen.patch` is a separate opt-in AppKit patch, applied with
`patch -p1` after `patches/experimental/cocotron-status-notifier.patch`,
optionally after the complete count-diagnostic chain. It does not alter the
production build. Pair it explicitly with the experimental transport above;
the existing `DARLING_STATUS_NOTIFIER_LIBRARY` opt-in and a live, enabled
status item are required. Event kind 8 invokes private `[NSApp _reopen]` via
the existing main-run-loop polling timer; its menu ID is not used. Other events
retain their existing behavior. This depends on Cocotron's private selector.

Run `python3 -m unittest discover -s tests -p test_reopen_guest_patch.py` for
clean git-derived patch application and static ABI/dispatch checks. These do
not execute guest code: transport-to-guest delivery, main-thread execution in
a real guest, and real client/window restoration remain unproven.
