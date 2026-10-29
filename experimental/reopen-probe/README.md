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
