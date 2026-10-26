# Reliability work and account restrictions

## Objective and limits

Reduce project-caused interruptions that could contribute to disconnects,
inactivity or abandoned matches. We have no confirmed explanation from Riot
for the reported restriction, and no evidence that these changes reduce
integrity-related account actions. Eliminating penalties is not an acceptance
criterion we can honestly measure or guarantee.

Use original test programs, fake process trees, mocked signals and synthetic
compositor inventories. Do not start Darling/Riot, authenticate an account,
query client APIs or modify the installed runtime as part of this work.
Do not replace security behavior with fabricated approval or signing state.

## Priorities

See the [dated open-PR review](open-pr-account-risk-2026-10-26.md) for specific
candidate changes, source findings, blockers and evidence limits.

1. **Preserve sessions on uncertainty.** Audit every launcher/recovery cleanup
   path for active-game guards, prefix ownership, saved process identity and
   concurrent startup races. Window absence alone cannot establish an idle
   session or authorize an automatic supervisor.
2. **Close compositor coverage gaps.** Niri has a native read-only inventory;
   other detected Wayland sessions currently block stale-client recovery.
   Add native backends only with fixtures covering hidden, minimized and
   off-workspace windows, command failures and malformed responses.
3. **Reduce startup failures before playing.** Extend prerequisite and runtime
   consistency checks without making destructive repairs automatic. Keep
   headless build checks distinct from runtime readiness.
4. **Investigate crashes privately.** Classify explicitly supplied logs into
   observed failures without attributing a suspension to an unconfirmed cause.
   Never upload diagnostic reports automatically.
5. **Validate compatibility independently.** Continue the isolated PR #144 lab;
   correct format parsing and loader behavior before considering integration.
   Synthetic success is not Apple trust, Riot approval or account safety.

## Current incremental change

- Detected non-Niri Wayland sessions return unknown without relying on an
  empty Xwayland window list.
- X11 WM_CLASS must be a complete, supported two-string value; incomplete,
  escaped or otherwise malformed responses preserve the session.
- Recovery regression tests assert that unknown Wayland state issues no
  termination signals and performs no X11 fallback.

These controls are conservative and can prevent recovery from acting on a
genuinely stale client. Manual restoration is preferable to killing a live
session. They cannot eliminate check-to-signal races or identify queue,
champion-selection or download state from window inventories alone.
