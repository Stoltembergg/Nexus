# dc-codesign

Prototype of the phase-M1 parser from
[`docs/security/SIP_AMFI_IMPLEMENTATION_PLAN.md`](../../docs/security/SIP_AMFI_IMPLEMENTATION_PLAN.md).

It reads a thin 64-bit Mach-O, finds `LC_CODE_SIGNATURE`, parses the
`CS_SuperBlob` and the `CodeDirectory`, verifies every code-page hash, and
reports the effective cdhash exactly as `csops(CS_OPS_CDHASH)` would.

## Build

```sh
make            # needs OpenSSL headers (libcrypto)
```

## Usage

```sh
./dc-codesign info         path/to/binary     # key=value dump
./dc-codesign verify       path/to/binary     # parse + page hashes
./dc-codesign cdhash       path/to/binary     # 20-byte cdhash, hex
./dc-codesign entitlements path/to/binary     # XML entitlements
./dc-codesign blobs        path/to/binary     # SuperBlob slot listing
```

Exit codes: `0` ok, `1` parse/verification failure, `2` usage/IO error.

## What is checked

- Mach-O magic/endianness (64-bit LE/BE; fat binaries are rejected).
- Load-command bounds, exactly one `LC_CODE_SIGNATURE`.
- SuperBlob magic/length/count and every blob `offset + length`.
- CodeDirectory version-gated field sizes (v0x20100 … v0x20500).
- `hashOffset`/`nSpecialSlots`/`nCodeSlots` arithmetic without overflow.
- hash type ↔ hash size consistency; identifier/team-id NUL termination.
- `codeLimit` (32- and 64-bit forms) against the file size, and
  `nCodeSlots == ceil(codeLimit / pageSize)`.
- cdhash = H(CodeDirectory blob) truncated to 20 bytes, per hash type.
- Every page hash, including the short last page.
- XML and DER entitlements are located and returned, not interpreted.

## What is *not* checked yet

- CMS/PKI chains, designated requirements, notarization, Apple policy.
- Special slots (Info.plist, requirements, resource envelope) — they need the
  bundle, not just the Mach-O.
- Fat/universal binaries.
- Fat Mach-O slices and `LC_CODE_SIGNATURE` in non-first slices.

Those belong to M4/M9 in the plan and are deliberately not claimed here.

## Tests

```sh
make test
# or, with an explicit input:
./test.sh /path/to/some.dylib
```

`test.sh` cross-checks against [`rcodesign`](https://github.com/indygreg/apple-platform-rs),
an independent implementation: SHA-1/SHA-256 of the CodeDirectory, effective
cdhash, page verification, tamper rejection, entitlements round-trip,
self-signed team id, truncated and non-Mach-O inputs.

If no Mach-O is passed and no Darling build tree is present, the script reports
`SKIP` instead of failing.
