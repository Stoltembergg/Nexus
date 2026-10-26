# Safe diagnostics and account restrictions

Nexus-LoL is unofficial compatibility tooling, not an approved Riot integration.
There is no proven change that prevents account restrictions. Successful unit
tests, a working client and a clean diagnostic report do not establish account
safety. Follow [the upstream compliance scope](COMPLIANCE.md).

If an account is restricted, pause authenticated experiments. Do not rotate
accounts, serials or UUIDs to work around a restriction. Keep the original logs
private and request review through Riot Support. Do not change security checks,
attestations, client binaries or anti-cheat behavior in response to a restriction.

## Local, opt-in reports

The collector never starts Darling or the client, queries Riot APIs, reads process
arguments, or uploads data. By default it records only the source revision, basic
OS/tool version information and whether the prefix directory exists:

```sh
python3 tools/collect-diagnostics.py
```

Logs are read only when explicitly selected. Each input is limited to the final
256 KiB, up to 10 files. Partial first lines are discarded after truncation.
Symlinks, binary files, devices and pipes are refused.

```sh
python3 tools/collect-diagnostics.py --log /path/to/selected-launcher.log
```

Reports are new mode-0600 JSON files under ignored `build/diagnostics/`.
`--output` selects an existing parent directory and a new filename; an existing
file or symlink is never overwritten. `--prefix` selects an additional private
path to mask, not a directory to scan.

Common auth fields, including `--riotclient-auth-token` and `--agent-auth-token`,
are masked, along with HTTP auth/cookie headers, OAuth query parameters, email
addresses, labelled account identifiers, private keys and local home paths.
Unlabelled identifiers and novel secret formats may remain. **Read the whole
report before sharing. Never automatically publish it or attach raw logs.**

## Support request outline

Submit privately to Riot Support, not a public issue. Fill only facts you know:

> My account received a three-day restriction on [date/time/timezone]. The message
> states [exact message, without account identifiers]. I used the official macOS
> client through the unofficial Darling compatibility layer on Linux, revision
> [revision], client version [version]. [Describe what you did, without assuming
> why the restriction happened.] I have paused testing. Could you review the
> restriction and clarify whether this configuration is permitted?

Do not claim that a GPU string, signature API or hardware identifier caused the
restriction without confirmation. Do not provide passwords or authentication
tokens. This tool cannot identify or reverse a Riot account action.

## Session recovery safety

See [the staged session-supervisor review](reviews/nexus-session-safety.md) for
Niri/iNiR-aware detection and the remaining requirements before automatic
session cleanup can be integrated. A minimized window is not a closed client.
