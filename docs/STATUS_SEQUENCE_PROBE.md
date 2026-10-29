# Neutral status sequence probe

The owned AppKit probe creates an empty status menu, waits eight seconds, adds
four root entries (three neutral labels and one empty label; all enabled and
visible), and leaves the menu unchanged until it exits at 180 seconds. The
entries have harmless no-op actions. The green/white icon is original, not a
client asset. No client APIs, credentials, or live Riot process are used.

Build with `python3 tools/status-sequence-probe.py build`. The manual desktop
launch, **not performed by this validation**, is:

```
cd <repository root>
python3 tools/status-sequence-probe.py desktop --desktop
```

It creates a unique private prefix under `sp-*` in the project root, uses
the pre-existing staged diagnostic AppKit and wrapper, and reads runtime
dependencies from the configured prefix without changing them. It does not
shut down any namespace. Prefixes are retained. Existing staged binaries and
configuration are prerequisites; this is not a clean-room build. The empty
menu may not be shown by every panel, and a successful launch is not proof of
panel rendering. Logs may contain paths and should be handled as sensitive.

Validation: the focused private D-Bus native transport test checks the empty
snapshot, the four properties, both asynchronous `LayoutUpdated` and `NewMenu`
signals, and an unchanged revision after a repeated snapshot. The original
private guest prefix was too long for Linux's 108-byte AF_UNIX socket path:
the socket appeared truncated as `shellspawn.` rather than `shellspawn.sock`.
The old failed log is `build/status-sequence-probe/private-validation/guest.log`.
The launcher now chooses a short private prefix and checks the socket length.

The owned guest was subsequently validated with `dbus-run-session -- python3
tests/status_sequence_guest_check.py`, using a private bus and short new prefix.
Its actual AppKit owner exported the empty menu, then four visible and enabled
root entries, including one empty label, with both update signals, and retained
an unchanged layout. It exited normally; its retained prefix and log are
`sg-6nfelt4w/p` and `sg-6nfelt4w/guest.log`. The owner republishes the populated
menu through `setMenu:` because adding items alone did not emit an update in
this staged adapter. This private-bus validation does not establish physical
desktop rendering. No manual desktop test has been run.
