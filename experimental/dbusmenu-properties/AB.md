# Neutral A/B probe

Everything is under this isolated tree. `ab.py build` builds two separate host
libraries and Mach-O wrappers plus the same guest binary under
`build/dbusmenu-properties-experiment/ab/`. The control uses the original source;
the corrected variant uses the experimental source. Both use the existing
`status-count-title-diagnostic` AppKit stage read-only and the same configured
runtime frameworks/libraries; no installation or stage writes are performed.
The test does **not** exercise the currently installed stage unless it happens
to be this explicitly named diagnostic stage. Each launch allocates a fresh,
retained private Darling prefix; do not run both variants concurrently.

Build and check the guest with a fake watcher on a new private bus:

```sh
python3 experimental/dbusmenu-properties/ab.py build
python3 experimental/dbusmenu-properties/ab.py private --variant both
```

The private check verifies the actual guest, watcher registration, SNI Active
status and a nonempty opaque 22x22 IconPixmap, plus the same four item IDs moving
from hidden/disabled/empty to visible/enabled, with three titles and one empty
title. It also checks layout/property signal counts and changed property values,
and compares the two pixmap digests. The fake watcher is not a desktop host and this is **not** proof that a
real shell renders the icon. The script starts no desktop and does not inspect
the current session bus. Raw guest output is withheld; pass/fail summaries do
not include paths, bus names or other raw diagnostics.

Only when ready to make a real visible item in the current desktop session,
run these one at a time in order (the `--desktop` flag is mandatory):

```sh
python3 experimental/dbusmenu-properties/ab.py desktop --desktop --variant control --seconds 120 | tee /tmp/opencode/tray-control-sanitized.log
python3 experimental/dbusmenu-properties/ab.py desktop --desktop --variant corrected --seconds 120 | tee /tmp/opencode/tray-corrected-sanitized.log
```

Look for the control's **green square with white center**, titled “Neutral control
probe”, and the corrected variant's **bright magenta square with white center**,
titled “Neutral corrected probe”. For the first 8 seconds the four existing menu items are hidden and
empty. After that, open the menu: expect “Primeiro teste”, “Segundo teste”,
“Terceiro teste” and one visible empty item. The guest exits at 120 seconds;
wait for it to exit before starting the second command. The sanitized output
reports guest initialization, population, and exit, not a visual verdict.
Compare both runs and record whether the icon appeared and the menu contents
before/after 8 seconds. A missing icon can be caused by the real session's
watcher/panel configuration; the private fake-watcher result cannot establish
whether a real panel host is present or rendering. No visual result is claimed.

The two scripts use fresh prefixes and leave them in place, rather than stopping
or cleaning any existing Darling namespace. If a guest fails, raw output is not
printed to avoid accidental disclosure; the sanitized status is insufficient
for diagnosis without a separate, deliberately scoped investigation. This is
an A/B of the bridge against the neutral producer, not evidence about Riot.
