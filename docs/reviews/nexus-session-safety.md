# Nexus-LoL session-safety review

Review baseline: upstream PR [#147](https://github.com/lucannez64/darling-lol/pull/147),
head `6b8cf67ca42c6db4daa38dce54f70ed9a124eca1`. This is a source review, not a
claim that a live game, account safety or Riot approval has been validated.

## Findings before integration

The PR supplies useful signal forwarding, namespace attribution and an
attached-session guard. It must not be imported wholesale into this branch:

1. `run_supervised()` calls cleanup after an owned loader exits without a final
   game/window safety gate. A loader exit alone does not prove that the game,
   champion selection or a download is finished.
2. The window probe only uses the X11 EWMH root list. Niri can omit that list;
   iNiR's stash also deliberately moves a live window to another workspace.
3. `stop_processes()` rechecks liveness but not a saved process start identity
   before each signal. PID reuse must not target a different process.
4. `owns_runtime = not runtime_alive(...)` is an observation, not an exclusive
   ownership lease. Concurrent launchers need a lock/ownership protocol before
   any automatic shutdown can be considered safe.
5. Namespace membership is a useful boundary, but cannot replace session state,
   explicit ownership and the active-game guard. Unknown state must preserve
   processes; missing windows alone must not authorize automatic shutdown.

## First implemented step

`tools/client_window_state.py` provides a shared, read-only tri-state inventory:

- `present`: a Riot/League window exists anywhere in the inventory;
- `absent`: a valid, complete-enough inventory contains none;
- `unknown`: command failure, timeout, malformed inventory or missing identity.

On Niri it queries `niri msg --json windows`, never filters by focus/workspace,
and never falls back to X11 after a Niri failure. Otherwise it checks EWMH
managed windows. Existing minimized X11 windows count as present, too. This
does not inspect Riot APIs or publish window titles.

```sh
python3 tools/client_window_state.py
```

The command prints only backend and aggregate status. Exit 1 means unknown;
it is not permission to terminate anything.

The existing opt-in stale-client recovery now uses this inventory and rechecks
the game/window guard before every signal, including escalation to SIGKILL.
Unreadable owned process command lines prevent recovery. Existing prefix,
age and process-start-identity checks remain in place. No default cleanup,
idle shutdown, client launch or production runtime replacement is introduced.

Checks and signals are not atomic. These guards reduce races but do not prove
that every possible concurrent startup is safe. Recovery stays opt-in and
must not be invoked while queued, choosing champions or downloading work that
must be preserved. Prefer restoring a minimized window over restarting it.

## Supervisor acceptance criteria for a later change

- Start disabled, with explicit ownership and opt-in activation.
- Preserve a session on an ordinary secondary-loader exit.
- Preserve games and clients on every workspace, including the iNiR stash.
- Preserve a session when compositor/process state cannot be established.
- Never infer permission to stop a download/champion selection from no windows.
- Revalidate saved start identities before signals; evaluate pidfds on Linux.
- Test concurrent starts, PID reuse, different prefixes, native Niri errors,
  disappearing windows and a game starting before escalation.
- Do not enable live/account testing as part of CI or installation.

All tests for this step use fake compositor inventories, fake process trees and
mocked signals. Account restrictions are outside the supervisor's control.
