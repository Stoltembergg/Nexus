# Issue #31: compatibility risks and sandbox follow-ups

Baseline: upstream `b88893b1cd7d0ecd954c393e94a5a4a3c214a29d`.
[Issue #31](https://github.com/lucannez64/darling-lol/issues/31) contains
suspension reports and runtime logs, not a confirmed explanation from Riot.
The objective is to reduce unsupported interactions and correct real security
and compatibility defects, without reverse-engineering anti-cheat, fabricating
security state, or concealing the compatibility layer. See `docs/COMPLIANCE.md`.

## Evidence and priorities

The order below is **implementation priority**, not a prediction of ban causes.
Confidence describes the observed defect, never its relationship to sanctions.
The user reports delays of up to 48 hours; this review has not independently
verified that interval. Passing offline tests or a short session proves no
absence of delayed account sanctions.

| Priority | Observable evidence | Plausible compatibility concern, not an established ban trigger | Action and ownership |
| --- | --- | --- | --- |
| 1: certificate provisioning | `tools/run-riot-client.sh` previously continued after the root helper failed. Historical issue logs show missing trust settings (`-25263`) and Chromium assuming all roots trusted. High confidence in the launcher defect; historical logs do not establish current guest TLS behavior. | Proceeding after failed trust bootstrap can cause HTTPS failures or unsafe verifier fallbacks. | This contribution stops new client launches and optional session helpers on a nonzero provisioning result, preserving its status. It does not replace guest TLS validation. |
| 2: accidental graphics layers | `tools/exec-guest.py` intentionally preserves host driver variables. Open PR #60 documents a MangoHud procfs exception and a standalone reproduction. Final launcher removes `DYLD_INSERT_LIBRARIES`, but this is not a blanket prevention of native layers. | An inherited overlay can execute unsupported code inside graphics paths or crash. Whether a vendor flags that interaction is unknown. | Reuse/review #60's targeted overlay handling rather than remove required `VK_*`, Mesa, display, or GameMode configuration indiscriminately. Do not duplicate its patch here. |
| 3: truthful security APIs | `patches/xnu.patch`, added `sys___mac_syscall`, explicitly returns success for AMFI and Seatbelt without enforcement. PR #48 additionally examines upstream `csops` and CSR stubs; those findings require the pinned upstream source, not just a search of this patch. | Successful query/setter results that do not represent implemented checks can contradict other APIs and mislead applications about their protection. | PR #48 owns the detailed contract/verification changes; #50 tracks actual enforcement. Support those efforts rather than manufacture signing identities or claim Linux namespace isolation implements SIP. |
| 4: hardware reports | Issue logs describe a model/CPU mismatch. Current launcher enables `DARLING_METAL_MAC_GPU_NAME` by default; `docs/reviews/pr41-adaptation.md` records concerns with replacing real hardware properties with fixed values. High confidence that reporting paths need consistency review, not that any one string causes sanctions. | A fixed model or GPU name may disagree with actual capabilities, memory, or instructions. | Compare standalone API probes against actual supported capabilities. Do not add fixed Apple identities, filter telemetry, or advertise CPU features the host cannot execute. PR #104's closure does not establish its hypothesis as correct. |
| 5: actual isolation | `darling-lol-launcher.sh` creates a user namespace; `scripts/fhs-entry.sh` requests all inheritable/ambient namespace capabilities. `flake.nix` uses `buildFHSEnv` for path compatibility, not a declared hostile-code containment boundary. Exact mounts and PID visibility must be measured in that generated environment. | Broad access can expose user files or allow accidental cross-application interactions. No evidence here establishes that unrelated visible host tools cause suspensions. | Measure and narrow access with explicit threat-model tests. Namespace root is not host root, but the mapped user can still access host files permitted to that user. |

## Prior work: reuse without duplicating it

All links below refer to `https://github.com/lucannez64/darling-lol/pull/`.
The saved review snapshot was taken on October 20, 2026; recheck live status
before adopting an unmerged branch.

- [#41](https://github.com/lucannez64/darling-lol/pull/41): broad original proposal;
  use its bug inventory and standalone probes as leads, not its assertion that
  bans are resolved. Inspect semantic changes, not regenerated patch volume.
- [#42](https://github.com/lucannez64/darling-lol/pull/42),
  [#43](https://github.com/lucannez64/darling-lol/pull/43),
  [#44](https://github.com/lucannez64/darling-lol/pull/44), and
  [#45](https://github.com/lucannez64/darling-lol/pull/45): already merged;
  preserve the path validation, independent compatibility extraction and
  follow-up behavior documented in `pr41-adaptation.md` and
  `pr41-deferred-implementation.md`. Do not cherry-pick them again.
- [#48](https://github.com/lucannez64/darling-lol/pull/48): open draft with
  signing/CSR/AMFI contract work and CPUID candidate validation. Its standalone
  verifier and tests do not alone implement live-task enforcement.
- [#50](https://github.com/lucannez64/darling-lol/pull/50): open tracking draft
  for staged signing/SIP/AMFI enforcement. A design document is not enforcement.
- [#60](https://github.com/lucannez64/darling-lol/pull/60): open targeted
  MangoHud crash fix. Prefer its early launcher boundary and inert tests over
  a new broad environment scrubber.
- [#79](https://github.com/lucannez64/darling-lol/pull/79): merged per-prefix
  identity provisioning/shared-default migration. It does not establish a
  genuine Apple device or eliminate other reporting contradictions.
- [#104](https://github.com/lucannez64/darling-lol/pull/104): closed hardware
  reporting proposal, not a root-certificate fix or proven suspension remedy.
- [#105](https://github.com/lucannez64/darling-lol/pull/105): merged `trustd`
  startup/lifecycle fix. Distinct from the already-present host CA import and
  this contribution's failure gate.

## Three real sandbox-hardening experiments

These are follow-up designs, **not implemented protections**. They restrict
actual access instead of synthesizing platform data. Run synthetic probes with
clients closed; never attach a debugger to the game or test with live accounts.

### 1. PID namespace and matching procfs

Measure current PID/procfs behavior first, then prototype a private PID namespace
with its real matching procfs and a reaper. Acceptance: a disposable host sentinel
process is absent from the namespace's process enumeration; its own children are
visible, reaped, and stopped cleanly; `--stop`, prefix ownership checks, signal
forwarding and stale-marker handling still work. Risks: current lifecycle code
uses host `/proc` and `.init.pid`; namespace changes can invalidate those checks
and create wrong-PID signaling hazards. This needs lifecycle redesign, not just
one extra bubblewrap flag. Do not fabricate a macOS process list.

### 2. Filesystem access minimization

Record the generated FHS mounts, then prototype an explicit read/write allowlist
for the prefix, workspace and caches, read-only runtime dependencies, and required
GPU/display/audio sockets. Acceptance: synthetic private host files cannot be
read or modified, while prefix writes, fonts, driver loading, audio sockets and
shader caches work. Include alternate prefixes, symlinks and XDG paths. Risks:
Darling's `/Volumes/SystemRoot` bridge, launch scripts, certificate bootstrap and
installer need real host paths. Masking `$HOME` alone does not close other aliases;
UID mapping does not prevent writes to permitted bind-mounted host files.

### 3. Measured capability reduction

Inventory capability use during standalone runtime setup and synthetic guest
execution before replacing `--inh-caps +all --ambient-caps +all`. Acceptance:
observed unnecessary capabilities are absent in actual child credentials, while
namespace mounts, effective-ID transitions, guest thread/exception handling and
clean shutdown remain functional. Test effective, permitted, inheritable,
bounding and ambient sets, not only environment variables. Risks: dropping
`SYS_ADMIN`, `SETUID`, `SETGID` or tracing-related permissions without measurement
can break rootless setup or Darling's own machinery. No minimum set is established
by this review; privilege reduction must not pretend macOS AMFI/SIP is present.

## What the current patch proves

The stub launcher regression covers healthy installed-client and installer
paths, plus certificate helper exits 1 and 127 in both modes with optional
recovery/watch helpers enabled. Failed bootstrap prevents **new** client/session
helper execution; earlier maintenance may already have started Darling.
It neither stops a running client nor validates the cached keychain's full
integrity. The certificate helper's cache/content checks and guest TLS behavior
remain separate review/test targets. No proprietary client was launched and no
suspension-risk hypothesis was validated against a live account.
