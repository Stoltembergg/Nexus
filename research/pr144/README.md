# PR #144: isolated code-signature parser lab

Pinned source: upstream PR [#144](https://github.com/lucannez64/darling-lol/pull/144),
commit `000d594436137f1077896166b2f22e3e7bf5a836`.

This is a targeted parser/format review, not a full security audit or a way to
make anti-cheat accept Darling. The PR is **not integrated into Nexus-LoL**.
Do not test it by authenticating a Riot account.

## What was tested

`parser_lab.py` compiles the PR's canonical native parser with AddressSanitizer
and UndefinedBehaviorSanitizer. It uses Clang/LLD to generate our original
`fixture.c` as ad-hoc-signed x86-64/arm64 Mach-O libraries, plus an unsigned
fixture and a universal container. None of these Mach-O files is executed.
Only the native parser runs, against these synthetic inputs.

The runner checks its pinned Git revision and refuses local edits by default.
`--allow-parser-edits` only permits explicit local changes to the canonical
parser and its two patch copies, and records the changed filenames. It runs no
Makefile, installer, shell security suite, Darling, Riot, sudo or network call.

```sh
python3 research/pr144/parser_lab.py --source /path/to/clean/pr144-checkout
```

Requirements: clang, ld64.lld, llvm-lipo and native OpenSSL development headers
and libraries. Build artifacts are temporary, under ignored `build/`, and are
removed after the run. JSON observations are new mode-0600 files there.
Exit 1 means a parser check found a blocker; exit 2 is a lab/tool error. A crash
or sanitizer error cannot be counted as a successful malformed-input rejection.

## Reproduced findings

| Observation | Original PR head | Local experimental fix |
| --- | --- | --- |
| Canonical parser equals mldr/server embedded copies | pass | pass |
| Signed thin x86-64 and arm64 fixtures | accepted | accepted |
| Unsigned fixture | rejected | rejected |
| Changed byte in signed `__text` | rejected | rejected |
| Signed universal fixture | rejected | still rejected |
| `sizeofcmds = 0`, but commands remain | parser accepts in `info` mode | rejected |
| `sizeofcmds` shorter than its commands | parser accepts in `info` mode | rejected |
| `sizeofcmds` larger than the sum of commands | parser accepts in `info` mode | rejected |

No sanitizer findings occurred in these limited cases. This was not a fuzzing
campaign or proof that the parser is memory-safe for all inputs.

### A. Universal format and the loader gate

The canonical `dc_parse()` deliberately accepts thin images only. However,
`codesign_gate()` in `patches/darling.patch` passes the entire main file to it,
before `load()` performs architecture selection. The same copies were checked
to be byte-identical to the canonical parser. A universal fixture is rejected
with the "not a thin Mach-O" condition.

This is a gate/format compatibility blocker under `enforce`, not a request to
disable verification or modify a client. A proper fix must select and bound
the architecture slice on the same descriptor, verify that slice, record the
correct offset/state and ensure that the loader maps exactly what was verified.
The actual loader was not built/executed in this experiment; its consequence
is supported by source inspection plus the parser-format reproduction.

### B. Declared load-command bounds

`find_signature()` checks `sizeofcmds` against the full file, but originally
checks each load command against the full file too, not against the declared
command region. It also never compares the final command offset to the region
end. The synthetic inspection cases demonstrate structural acceptance.

These tests use `info`, not successful page verification, and do **not** prove
that an altered executable loads or obtains valid signing state. In particular,
the modified header's original signed page hash is no longer correct.

`sizeofcmds-fix.patch` bounds commands to the declared region and checks its
exact end. It updates the canonical parser and both embedded patch copies.
It applies only to the pinned PR checkout, not to the current Nexus-LoL base:

```sh
git -C /path/to/experimental/pr144-checkout apply --check \
    /path/to/Nexus-LoL/research/pr144/sizeofcmds-fix.patch
git -C /path/to/experimental/pr144-checkout apply \
    /path/to/Nexus-LoL/research/pr144/sizeofcmds-fix.patch
python3 research/pr144/parser_lab.py \
    --source /path/to/experimental/pr144-checkout --allow-parser-edits
```

The final command intentionally still exits 1 while universal-format support
remains missing. Do not relabel that as full acceptance.

The experimental patch's forward/reverse applicability was checked; all 32
component patches also passed `prepare.py --check-only` against pinned base
indexes. That check did not change or rebuild the installed source/runtime.

## Still outside this experiment

- Loader/server integration, concurrent file mutation and signing-state RPCs.
- Apple CMS chain, entitlement policy, notarization and Gatekeeper acceptance.
- Trust-store privilege boundaries, full SIP enforcement and rootless support.
- Any claim about the cause of account restrictions or their prevention.

The relevant upstream M9/M10 gaps remain open. Further work should use original
fixtures and real macOS reference observations, not repeated account logins.
