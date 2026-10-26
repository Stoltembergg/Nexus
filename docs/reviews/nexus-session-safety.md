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
2. `managed_client_window()` in draft #4 still queries X11 EWMH directly. It
   does not use the shared tri-state helper, so Niri's native inventory and
   iNiR's stashed windows are not covered by that supervisor path.
3. The original `stop_processes()` implementation did not retain a saved
   process start identity before each signal. A follow-up on draft #4 now
   carries start ticks from candidate discovery through cleanup and rechecks
   identity/liveness before TERM and KILL. This rejects observed PID reuse, but
   procfs validation and `kill(2)` are not atomic; stronger closure needs
   pidfds. The follow-up does not add a final game/window guard before cleanup.
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
and never falls back to X11 after a Niri failure. On non-Niri Wayland, it uses
X11 EWMH through Xwayland only when `DISPLAY` is set; without Xwayland the result
is unknown. Failed, missing or malformed inventories remain unknown. This
supports the project's X11-backed Darling client path, not arbitrary native
Wayland applications. The Nix FHS environment supplies `xprop`. Existing
minimized X11 windows count as present, too. Malformed or unsupported WM_CLASS
encodings are unknown. This does not inspect Riot APIs or publish window titles.

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
- Carry saved start identities from process discovery and revalidate them before
  each signal; use pidfds if the final procfs-check-to-signal race must be closed.
- Test concurrent starts, PID reuse, different prefixes, native Niri errors,
  disappearing windows and a game starting before escalation.
- Do not enable live/account testing as part of CI or installation.

The PID-reuse regression tests use fake `/proc` trees and mocked signals. The
existing supervisor signal-escalation test exercises isolated Python helper
processes only; none of these checks starts Darling, Riot or a game. Account
restrictions remain outside the supervisor's control.
