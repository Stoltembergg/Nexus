# Open PR review: compatibility, session safety and account restrictions

Reviewed 2026-10-26. This is a snapshot, not a standing approval of later PR
updates. **No reviewed PR demonstrates that Darling/Linux is accepted by Riot
or prevents `UNSUPPORTED_THIRD_PARTY_TOOLS`.** That message does not identify
the exact check or establish which local change, if any, would affect it.

## Evidence and scope

- GitHub listed 7 open Nexus-LoL PRs and 10 open upstream PRs at collection.
- Source review focused on the security API changes, supervisor cleanup and
  priority handling, library installers and setup fixes. PR descriptions and
  test counts are contributor claims unless explicitly reproduced below.
- Upstream #144 remains at the head previously examined by our synthetic lab;
  that lab's documented findings still apply. It was not rerun for this review.
- Upstream #6 received only scope-level triage; its diff has 24,639 lines.
  GitHub refused the #125 diff as too large; its demo scope is based on the PR
  description, not a complete source audit. No full audit of either is claimed.
- No Riot authentication, game, client API, installed runtime modification or
  real macOS validation was performed. One installer failure was reproduced
  using temporary files only, as described below.

### What Riot actually documents

1. [Third Party Applications](https://support.riotgames.com/en-us/riot/events/third-party-applications)
   describes game-integrity policy, does not promise a complete safe-software
   list, and advises avoiding applications when their acceptability is uncertain.
2. [Patch 25.S1.2 notes](https://www.leagueoflegends.com/en-us/news/game-updates/patch-25-s1-2-notes/)
   announced Embedded Vanguard for macOS and the need for trusted Mac sessions.
   Using the macOS client is therefore not evidence that there is no anti-cheat.
3. [/dev: Vanguard x LoL](https://www.leagueoflegends.com/en-us/news/dev/dev-vanguard-x-lol/)
   says Linux was not officially supported and discusses the Windows/Wine
   attestation problem. This 2024 statement is context, not a diagnosis of a
   2026 Darling suspension or documentation of its precise detection rules.

None of these sources authorizes this project. Correct Darwin behavior, a
clean library inventory, a matching probe or passing CI cannot confer Riot
approval. Request clarification/review through Riot Support; do not rotate
accounts or identifiers, suppress checks, or fabricate trust/attestation.

## Nexus-LoL PR triage

Numbers in this table refer to [Stoltembergg/Nexus-LoL](https://github.com/Stoltembergg/Nexus-LoL/pulls).

| PR | Potential engineering value | Recommendation and outstanding evidence |
| --- | --- | --- |
| [#3](https://github.com/Stoltembergg/Nexus-LoL/pull/3) | Stops unconditional `CS_VALID` / AMFI success; adds an offline signature verifier. | Prioritize isolated correctness validation. File verification is not task-owned signing state, enforcement or Apple trust. Honest unsupported results may make callers refuse to run. Keep draft until pinned-patch checks, build and neutral Mac/Darling comparison are available. No penalty-reduction claim. |
| [#13](https://github.com/Stoltembergg/Nexus-LoL/pull/13) | Documents future signing/SIP/AMFI enforcement. | Useful planning, dependent on #3. Documentation only: not implemented protection, and no direct gameplay or account effect. |
| [#10](https://github.com/Stoltembergg/Nexus-LoL/pull/10) | Builds the XShm host/guest bridge through Darling's normal build/install paths. | Worth validating as packaging and provenance work. Need full host/guest build separation, install-prefix/relocation tests, and a neutral graphics fixture. The absolute native-library path is still compiled in; moving it is not elimination of the host bridge. Requires CONTRIBUTING's probe comparison before merge. |
| [#11](https://github.com/Stoltembergg/Nexus-LoL/pull/11) | Places graphics libraries at system paths in the guest prefix. | Hold integration pending transactional install/restore and idle-session guards. Same bytes in a new path are not new signatures or trust. Overrides remain; broader Darling processes can now load these libraries. See finding D. |
| [#12](https://github.com/Stoltembergg/Nexus-LoL/pull/12) | Consolidates six core libraries, reducing divergent duplicate copies. | Useful architecture, but block on interrupted-install recovery and an enforced idle-runtime/locking protocol. Failure reproduction below left mixed versions without a rollback manifest. Also needs neutral loader/probe comparison before merge. |
| [#4](https://github.com/Stoltembergg/Nexus-LoL/pull/4) | Signal forwarding and orphan cleanup. | Do not enable by default in this form. Cleanup after loader exit lacks a final active-game/window gate; ownership is observed, not exclusively leased; signaling lacks saved start-time revalidation. X11-only inventory bypasses our Niri/Wayland safety work. |
| [#8](https://github.com/Stoltembergg/Nexus-LoL/pull/8) | Waits for a detected game after an ordinary loader exit. | Split game preservation from priority tuning. It improves #4 but does not fix all cleanup races or unknown-state handling. Automatic priority changes have correctness/permission problems; see findings B/C. Depends on #4. |

Changing where a library is installed can improve maintainability and loading
consistency. It must not be justified as hiding third-party code: these remain
Darling components, not Apple-signed system libraries. Remove overrides only
after all consumers are accounted for and original fixture tests show the
intended library is actually loaded, including dependencies and rollback.

## Concrete source findings

### A. #4/#8: cleanup is not proven safe by loader exit

`run_supervised()` in #4 calls `cleanup()` after its child exits when
`owns_runtime = not runtime_alive(...)`. That observation does not prevent two
concurrent launchers from both claiming ownership. `stop_processes()` tests
liveness, but does not compare captured start ticks before each signal.
`managed_client_window()` uses X11 only rather than `client_window_state.py`.

#8 waits while `game_running()` is true after ordinary loader exit, which is a
useful partial fix. However, unreadable argv/environment can make that probe
miss a game, and the final cleanup is still not guarded against unknown state,
new windows or a newly starting game. SIGHUP still enters the stop path: closing
a terminal is not made harmless during a match. Require exclusive ownership,
tri-state probes, shared compositor inventory, identity-safe signaling and
tests for each transition before enabling automatic cleanup.

### B. #8: nice restoration can silently fail

`set_priority()` lowers each thread to nice 15. `restore()` later requests nice
0, an increase in scheduling priority which an ordinary process may not have
permission to perform (depending on capabilities/resource limits). OSErrors
are swallowed, so the UI can remain deprioritized while the code reports
restoration. Previous nice/scheduler values are not saved. Existing tests mock
the apply function, so they do not establish real permission semantics.

Do not solve this by granting the launcher broad privileges. Keep tuning
disabled unless a bounded, permission-safe design preserves original values,
reports failures, and is tested independently of game/client processes.

### C. #8: bare PID set and namespace-wide priority selection

`MatchPriority.lowered` holds numeric PIDs without their process-start identity;
`restore()` applies to those PIDs without rechecking identity or namespace.
A reused PID could therefore name another process. Selection includes every
non-game namespace member, not just UI/CEF; shared services may be slowed too.
Capture identities, limit eligibility and test PID reuse, missing /proc data,
exceptions and session exit. Do not couple this feature to game preservation.

### D. #11/#12: library migration needs a recoverable idle transaction

#11 prechecks source presence and uses per-file `.next` renames, but this is not
an all-files transaction. It invokes `stop-darling-runtime.py`, whose shutdown
is not an active-game/unknown-state refusal. An instruction to close the game
is not an enforced guard. An intermediate write failure can leave mixed
graphics libraries; add durable journaling, serialization and failure tests.

#12 stages copies and checks their hashes, then performs multiple replacements,
removes overrides and only finally writes `manifest.json`. On a first install,
failure during these mutations can leave backups but no manifest for
`--rollback`. Its standalone install/rollback also has no enforced idle-session
guard. Do not run either operation against a live or uncertain runtime.

**Reproduced for pinned #12 using original temporary fixtures:** extracted only
the added installer module from its reviewed diff, imported it without running
`main()`, created two synthetic Mach-O-header artifacts and two old destination
files under a temporary directory, and injected OSError on the second
`os.replace`. No real prefix or runtime tool was used.

| Observation after injected failure | Result |
| --- | --- |
| First destination contains new bytes | true |
| Second destination still contains old bytes | true |
| Backup files exist | true |
| `manifest.json` exists | false |
| Built-in rollback | refuses: no installation manifest |

Require a validated durable recovery journal before the first mutation,
atomic journal updates, failure recovery for every replacement/removal and
repeat/rollback operations, safe path handling and a shared setup/runtime lock.
Per-file atomic rename alone cannot establish all-files atomicity.

## Upstream PR triage

Numbers here refer to [lucannez64/darling-lol](https://github.com/lucannez64/darling-lol/pulls).

| PR | Decision |
| --- | --- |
| [#149](https://github.com/lucannez64/darling-lol/pull/149) | Good small stability candidate: checks for a null X display before EGL and avoids terminating an absent EGL display. Validate patch applicability and headless iokitd with our own program. A bootable headless runtime still cannot render a game. No account-risk evidence. |
| [#148](https://github.com/lucannez64/darling-lol/pull/148) | Useful moved-checkout repair: relative build symlink, conservative CMake-cache warning and prefix migration. Port selectively with tests preserving explicit prefixes and local state. No reason to expect it to change a third-party-tools restriction. |
| [#150](https://github.com/lucannez64/darling-lol/pull/150) | Compare with our existing preflight, not a wholesale replacement. LFS-pointer inspection and actual LLVM-library consistency deserve follow-up. Keep our stricter runtime graphics policy; lowering Python requirements requires a tree-wide compatibility audit. Tool version alone does not prove loaded-library compatibility. |
| [#133](https://github.com/lucannez64/darling-lol/pull/133) | Useful doctor/performance ideas; review collection scope separately. It collects process information and default log tails and offers `--no-redact`. Preserve our explicit-input, bounded, private-report model. Diagnostics do not confer approval. |
| [#48](https://github.com/lucannez64/darling-lol/pull/48), [#50](https://github.com/lucannez64/darling-lol/pull/50) | Correspond to Nexus #3 and #13. Honest API semantics and an enforcement plan, not evidence of a trusted game session. |
| [#144](https://github.com/lucannez64/darling-lol/pull/144) | Still conflicting and prototype-level. Local trust is not Apple trust; notarization/production validation remain pending. Our prior lab found universal-image rejection and a sizeofcmds parsing issue, with only the latter experimentally fixed. Keep isolated; see [lab](../../research/pr144/README.md). |
| [#147](https://github.com/lucannez64/darling-lol/pull/147) | Same supervisor baseline as Nexus #4; retain the [session-safety blockers](nexus-session-safety.md). |
| [#125](https://github.com/lucannez64/darling-lol/pull/125) | Consent-banner demo only according to its description. Risk disclosure can help informed decisions but does not reduce enforcement or establish permission. Source audit incomplete. |
| [#6](https://github.com/lucannez64/darling-lol/pull/6) | Conflicting broad launcher/desktop change, described as including bundled game icons. No demonstrated restriction-related benefit; no recommendation to import wholesale, including third-party assets. Source audit incomplete. |

## Recommended sequence

1. Establish an explicit Riot Support/Developer Relations position on this
   compatibility configuration. Keep account experiments paused in the meantime.
2. Validate small non-authenticated stability changes (#149/#148) and strengthen
   setup/runtime locks and idle-state guards before library migration.
3. Review truthful security semantics (#3), then the documentation plan (#13).
   Use own test programs and real Mac reference observations, not client probes.
4. Validate #10, then repaired #11/#12 as provenance/loading work. Satisfy the
   CONTRIBUTING neutral-probe requirement; a match is not a safety certificate.
5. Rework #4 with #8's preservation idea, shared tri-state detection, exclusive
   ownership and PID-identity checks. Leave priority tuning separate and off.
6. Continue #144 as isolated research, not as an account-risk mitigation release.

No authenticated match, including custom/bot matches or another account, is
required for these review steps. A run without a penalty cannot establish an
acceptable restriction rate or substitute for Riot approval.

## Reviewed heads

| Repository | PR | Head SHA |
| --- | --- | --- |
| Nexus-LoL | 3 | `68635bc8cf13780b0c87f99d5ff1cfd185ac78bf` |
| Nexus-LoL | 4 | `a90b5406e860834eff71bfe66f9f98c16406f162` |
| Nexus-LoL | 8 | `2bdcd13eacfa7bae746827c198cfc8124da22386` |
| Nexus-LoL | 10 | `1b3672afcdd941a3ce33957588b63320c923cbdf` |
| Nexus-LoL | 11 | `f3b563e97208330ebb6b795fdf6eb4ddb3887c7c` |
| Nexus-LoL | 12 | `885039ffb5aed434fba63ab789dee687484358e8` |
| Nexus-LoL | 13 | `3d5544cf83809dbbc07bec0e6b4e2cb9b17c9fa6` |
| darling-lol | 6 | `b9d1e48fe6a2fa153fb3977a384b93478583d2f6` |
| darling-lol | 48 | `c7948abe0ba6cef79846a7f0e230e4e490f9d4c6` |
| darling-lol | 50 | `1895b3d924c9211438c7061e52cd358ef45d83d6` |
| darling-lol | 125 | `0706d7a9aeeaff40c9264a15534a2bbdd4e284d5` |
| darling-lol | 133 | `a07ebb8c5aff15222b7538330fe39c5e1c0e3adc` |
| darling-lol | 144 | `000d594436137f1077896166b2f22e3e7bf5a836` |
| darling-lol | 147 | `6b8cf67ca42c6db4daa38dce54f70ed9a124eca1` |
| darling-lol | 148 | `eb3333e421776650482d7810da0b92c6279342a3` |
| darling-lol | 149 | `33a5c486560164510efb3ed5bc940a65302e43ff` |
| darling-lol | 150 | `a87c041def3d8a62b1d9d0e601fa10856abca7d8` |
