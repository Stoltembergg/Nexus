# Compatibility probe categories

Companion note for `tools/compat-probe/`. Categories come from publicly
discussed Darling gaps (upstream darling-lol issues #49 and #134 and related
thread #31). Framing is compatibility only; see `docs/COMPLIANCE.md`.

| Category | Why it matters for apps | Typical Mac result | Common Darling gap |
|---|---|---|---|
| `sysctl` CPU / model | Apps read `hw.model`, `machdep.cpu.brand_string` | Consistent Intel/Apple Silicon profile | Host CPU brand can disagree with model string |
| IOKit platform | Serial, UUID, model via `IOPlatformExpertDevice` | Present, Apple-shaped | Missing keys, synthetic serials, or host-derived values |
| `csops` | Code-signing status for the running image | Non-zero validated flags when signed | Often zero flags / no validation path |
| SIP / CSR | Security policy queries | Config readable | `kern.csr_config` missing or SIP reported disabled |
| Mounts (`getfsstat`) | Filesystem topology | APFS (+ devfs) | Host Linux fstypes (`ext4`, `proc`, `sysfs`, …) |
| Processes (`proc_listpids`) | Process enumeration | Real Darwin daemons + apps | Unsupported / empty / error |

Workflow: capture JSON on macOS and Darling with `compat_probe`, diff with
`compare_probe.py`, then open ordinary compatibility fixes (truthful APIs,
missing implementations) rather than fabricating a different machine profile.
