# Compatibility probe (macOS ↔ Darling)

Neutral audit of Darwin APIs that applications commonly read for platform
identity and security state. Run the same program on a real Mac and inside a
Darling guest, then compare the JSON dumps.

This tool does **not** launch Riot clients, does not change platform identity,
and is not involved with anti-cheat. It exists so contributors can see where
Darling's answers diverge from macOS and fix those gaps as ordinary
compatibility work. See `docs/COMPLIANCE.md`.

## Build

On macOS, or inside a Darling guest that has `clang` and the system frameworks:

```sh
clang -O2 -Wall -Wextra -o compat_probe compat_probe.c \
  -framework IOKit -framework CoreFoundation
```

Optional window-list section (links ApplicationServices / CoreGraphics):

```sh
clang -O2 -Wall -Wextra -DCOMPAT_PROBE_WINDOWS=1 -o compat_probe compat_probe.c \
  -framework IOKit -framework CoreFoundation -framework ApplicationServices
```

## Capture

```sh
./compat_probe > macos.json          # on a real Mac
./compat_probe > darling.json        # inside Darling
python3 compare_probe.py macos.json darling.json
```

Exit status: `0` match, `1` differences, `2` IO/parse errors.

Privacy: the probe never prints the hostname, serial number or platform UUID.
It records only whether the hostname is set and, for the serial and UUID, their
presence, length and coarse format (`uuid`, `alnum-upper`, `other`). It never
lists process names either: `processes` holds only the PID count and
`system_present`, booleans for a fixed list of universal macOS daemons
(`kernel_task`, `launchd`, `WindowServer`, `loginwindow`, `logd`, `configd`,
`notifyd`, `mds`). Mounts report filesystem types only, never paths, and the
optional window section reports a count only. Review a
capture before sharing it anyway.

## Fixtures

`fixtures/` holds synthetic samples so `compare_probe.py` can be exercised
without a Mac:

```sh
python3 compare_probe.py fixtures/match-a.json fixtures/match-b.json
python3 compare_probe.py fixtures/macos-sample.json fixtures/darling-sample.json
```

## Motivation

Public upstream reports document incomplete code-signing / SIP / AMFI behavior
and inconsistent platform reporting across APIs (see `research/compat-probe.md`).
This probe turns those categories into a repeatable local checklist.
