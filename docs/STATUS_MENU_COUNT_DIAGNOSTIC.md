# Status menu count diagnostic

`patches/experimental/cocotron-status-menu-count.patch` applies after the
status-notifier adapter. It is not in the production manifest. An independent
AppKit framework is staged at `build/status-count-diagnostic/AppKit.framework`;
it is not installed and does not affect already running processes. Its adapter
was rebuilt from `build/darling-src` and linked against the configured AppKit
build. Other framework objects come from that build; this is not a clean-room
rebuild. The host status-notifier library is unchanged.

Only with `DARLING_STATUS_MENU_COUNT_TRACE=1` exactly, stderr receives
`SMCOUNT` records: item count and depth after each menu update, build validity
and entry count, and actual snapshot/clear send count and acceptance, or a
skipped send when the native item was removed. Invalid builds clear the host
menu, so the build count can differ from the send count. Acceptance is the
adapter API return, not proof of panel display. Exceptions during update/build
can prevent a final record. Counts can reveal activity and should be handled as
sensitive; records do not include labels, titles, selectors, credentials,
client APIs or input tracking. Do not enable the unrelated broader debug or
input traces. Existing other traces are separately gated.

No runtime launch is performed by this diagnostic. Any later launch with this
framework override and flag needs explicit authorization and appropriate safety
checks; staging alone neither changes nor diagnoses the current session.

## Owned probe validation

An independent `status-notifier-appkit-check` was run with a fresh private
`build/status-count-probe-private/prefix` and a separate `dbus-run-session`,
using the staged framework and owned notifier wrapper. No Riot process or
client API was used, and no namespace shutdown was requested. The private
prefix is retained; this is not a cleanup instruction. The probe exited zero
with the flag unset, `0`, and `1`. The first two produced zero SMCOUNT lines;
`1` produced 85 lines, all matching the documented fixed numeric schema. The
probe includes an empty menu, populated menu and nested submenu; observed
snapshot acceptance is not evidence of desktop panel display. Failure and
concurrent removal branches were not exercised.

`trace-unset.log` records dyld loading the exact staged AppKit and owned wrapper;
all three runs report `STATUS_MENU_DEFAULT_INIT enabled=1 empty_title=1
empty_key=1` and the adapter's tracking/lifecycle checks passed. Thus the
loaded stage contains the working initializer and adapter, not merely a source
patch. The staged AppKit SHA-256 was
`9c9d394ca91cb4a3c2c9dbe0672fea966f509296ff8d36536abc55f1dc16450a`.
Logs are mode 0600 in the private directory; dyld's diagnostic log contains
filesystem paths and should also be treated as sensitive.

## Visibility aggregate extension

Apply `patches/experimental/cocotron-status-menu-count-visibility.patch` after
the count patch. Its separate stage is
`build/status-count-visibility-diagnostic/AppKit.framework`; it does not modify
the previous stage. With the same exact opt-in flag, `SMCOUNT aggregate` reports
depth, processed items, visible/hidden, enabled/disabled, submenu-bearing items,
and whether traversal completed successfully. Depth 1 is the root; each deeper
record covers one submenu, not an aggregate across all submenus. Records contain
no IDs or labels and cannot correlate individual menus. Counts reuse the exact
visibility/enabled flags used for the snapshot. `complete=0` can mean partial
counts, including when a descendant fails. Separators count as items. Visibility
is the AppKit hidden flag, not proof the host panel displayed anything. Enabled
and visible are independent totals, not their intersection; `build entries`
includes descendants while root counts do not.

The owned probe ran with a separate private prefix and D-Bus session, no Riot
launch and no namespace shutdown. With flag `0` it emitted no SMCOUNT records;
with `1`, 116 records including 31 aggregate records matched the fixed numeric
schema. Root examples included `visible=2 hidden=1` and `enabled=1 disabled=2`;
the nested case reported a root submenu count of 1 and a depth-2 record. Both
runs exited zero, passed the initializer and adapter checks, and dyld identified
the new stage. Logs are in `build/status-count-visibility-probe/trace-{0,1}.log`
(0600, including sensitive dyld paths). The staged binary SHA-256 is
`d9d233cdb927ad847f90faf3ee80f510b13a3d537d8e5eba14ea318cbced539e`.
No real-client inference has been made; failed traversal, rejected submission,
and host rendering were not exercised here.

## Empty-title and separator extension

`patches/experimental/cocotron-status-menu-count-title.patch` layers on the
visibility extension. Its separate stage is
`build/status-count-title-diagnostic/AppKit.framework`. With the same opt-in,
aggregate records additionally contain `empty`, `nonempty`, and `separators`.
These count the already prepared UTF-8 snapshot title bytes and separator flag;
no title contents, IDs, selectors or client API data are logged. A nil title is
converted to empty by the existing adapter; whitespace is nonempty. Separator
counts overlap the empty/nonempty counts. Counts cover processed entries only;
`complete=0` can denote a partial traversal. The prior aggregate caveats apply.

The owned probe at `build/status-count-title-probe/status-notifier-title-probe.m`
adds a blank item and separator to a menu containing two nonblank items, then
refreshes and removes those test items. It ran against the new stage with a
fresh private Darling prefix and a private D-Bus daemon. No Riot or client API
was used and no process was terminated by the validation; the private daemon
and prefix are retained. Both flag `0` and `1` runs exited zero. Flag `0`
emitted no SMCOUNT; flag `1` emitted 120 records, 32 aggregate, all matching the
fixed numeric schema. The test snapshot recorded `processed=4 empty=2
nonempty=2 separators=1 complete=1`; empty includes the separator. Dyld logs
confirm the staged AppKit, and initializer and adapter checks passed. Logs are
`build/status-count-title-probe/trace-{0,1}.log` (0600; dyld paths are
sensitive). SHA-256 of the staged AppKit binary:
`4c995ddb2987c9aaa7fee966e008081a88b77bcae227f2629e8e9e60fe5b9c11`.
The test does not establish Riot menu content or actual panel rendering.
