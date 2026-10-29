# Experimental reopen probe (opt-in)

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
