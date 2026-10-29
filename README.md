# darling-lol

> [!WARNING]
> This is an unofficial, experimental compatibility project, not a Riot-supported Linux client. Running League through a modified runtime may violate Riot's terms and can lead to account restrictions. Do not test with an account you value or play ranked. This project cannot guarantee account safety.

This repository continues the Darling LoL work originally published at [lucannez64/darling-lol](https://github.com/lucannez64/darling-lol). It contains experimental source patches and tools for running the **macOS League of Legends client on x86-64 Linux through Darling**.

This is a development snapshot, not a finished launcher. Riot and League clients can launch, and manually played matches have run on the machines listed in [the compatibility matrix](docs/COMPATIBILITY.md). A fresh checkout has not been validated end to end on another machine. Review [current status](docs/STATUS.md) for measurement details and known limitations.

## Current development focus

The current priority is performance and stability across the launcher, Darling runtime, desktop integration and gameplay. Work is focused on repeatable frame-pacing baselines, CPU/GPU profiling, memory behavior in longer sessions, and failures between launch and entering or continuing a match. Performance changes remain experimental until comparable measurements support them.

Available results come from specific machines and manually played matches; they are not a general performance guarantee. The Ryzen 5 5500 / RX 6600 development PC reached 135.4 average FPS in one ARAM match, while five ARAM matches on an Intel UHD 620 laptop averaged 24–32 FPS. See [status](docs/STATUS.md) and [compatibility](docs/COMPATIBILITY.md) for the conditions and limitations. The effect of memory changes on real-client RAM use remains unmeasured.

`darling-lol --doctor` and `darling-lol --perf` collect host and game-log data for compatibility reports. The performance percentiles are based on League's ten-second frame-time samples, not individual frame timings; see [how the numbers are measured](docs/COMPATIBILITY.md#what-the-numbers-mean).

## Included

- Pinned upstream revisions and patches for 30 Darling components, including Metal/Indium, AppKit, QuartzCore, CoreAudio, the kernel shim and darlingserver.
- Event-poll presentation and GPU synchronization fixes, floating-point-safe GL resolvers, multi-window presentation and nullable LaunchServices error handling.
- Reusable server receive buffers and Darwin allocator hints translated to Linux lazy reclamation.
- Build/install/launch wrappers, atomic incremental installers and standalone regression probes.

Game files, Riot installers, account databases, tokens, local prefixes, captures and compiled binaries are not included. Install the game manually through Riot. The normal launcher does not enable an Electron inspector or start UI automation helpers; the opt-in window-management helpers described below are off by default and do not patch client binaries. The launcher clears `DYLD_INSERT_LIBRARIES` and retains Darling runtime library/framework overrides; this is not a claim of approval by Riot.

## Requirements

- x86-64 Linux **5.14 or newer**, an X11 session or Xwayland, and a working hardware Vulkan/OpenGL driver. AMD RADV and the NVIDIA driver (proprietary and open kernel modules) have been exercised, see [NVIDIA](docs/TROUBLESHOOTING.md#nvidia); other drivers are not validated. Hybrid laptops usually render on the integrated GPU unless started with PRIME offload. See [hybrid graphics](docs/TROUBLESHOOTING.md#hybrid-graphics-laptops-amdintel-igpu--nvidia).
- Git + Git LFS (2.13 or newer), Bash, curl, unzip, CMake 3.20+, Make, Clang/LLD, LLVM development files (16 or newer), a C/C++ compiler, Python 3.10+ and the Darling build dependencies. `scripts/build.sh` and `scripts/install-runtime.sh` run `scripts/preflight.py` first and stop on a version that cannot build or run the result; `RCLOL_SKIP_PREFLIGHT=1` bypasses that gate. The patch includes LLVM 22/23 branch-opcode compatibility, and LLVM 22 or 23 is what the Metal overlays are tested with. Node.js is needed only for the offline JavaScript checks.
- X11/XCB/SHM development files for the current runtime helpers.
- Enough free disk for Darling sources/build, Git LFS assets and the game: budget at least 50 GB. Building is substantially larger than this source-only repository.

Use the dependency list in the [pinned Darling source](https://github.com/darlinghq/darling/tree/60ba801decee7a00782f74f6be4c8ffb013f79ff) for your distribution. `tools/env-check.sh` provides a starting check; its legacy package names may need adapting to your distro.

## Experimental Nix/rootless package

```sh
nix run github:Stoltembergg/Nexus-LoL#installer
nix run github:Stoltembergg/Nexus-LoL#default -- --update
nix run github:Stoltembergg/Nexus-LoL#default
nix run github:Stoltembergg/Nexus-LoL#shell
```

Or from a local checkout:

```sh
nix run .#installer
nix run .#default
```

Nix supplies the launcher/dependencies, not a prebuilt Darling or game. First
setup is interactive and builds into the writable per-user workspace. The
desktop entry requests a terminal; EOF stdin produces an actionable error.
Run updates only after manually closing the clients and shutting Darling down
in the original namespace. A live prefix marker blocks a second launch rather
than killing or attempting to reconnect. One workspace/foreground namespace is
supported at a time. Readiness is per canonical prefix, configured guest and
compatible package/runtime/source identity. Store closure roots are retained
for mutable binaries; do not delete `build/nix-gcroots/` while using them.
See [Nix setup and operational limits](docs/SETUP.md#nixos-package).

## Build from source (non-Nix)

```sh
git clone https://github.com/Stoltembergg/Nexus-LoL.git
cd Nexus-LoL
python3 -m venv build/venv
build/venv/bin/pip install -r requirements.txt
python3 scripts/configure.py --guest-user "$USER"
./scripts/build.sh
sudo cmake --install build/darling-src/build
./scripts/install-runtime.sh
```

The default layout is `/usr/local/libexec/darling`, `~/.darling` and `/Users/$USER` inside the guest. Use the actual guest account name if it differs. Paths are rendered into ignored files under `build/runtime/tools`; do not run the tokenized `tools/` templates directly. See [setup details](docs/SETUP.md).

The install wrapper compiles the paired runtime, shuts down Darling before replacing per-user overrides, and backs up relevant files. Do this with no Riot/League session running.

## Install and launch Riot

After the runtime is installed:

```sh
./scripts/installer.sh euw
```

Sign in and install League through Riot's own UI. For subsequent launches:

```sh
./scripts/run.sh
```

First installation and future Riot updates can still encounter compatibility gaps. An accepted Install action can fail native LaunchAgent registration and leave the download idle. The archived inspector-based workaround is excluded from the manual workflow; the client window-visibility correction is part of the installed runtime (Darling's AppKit overlay), not a patch to Riot's binaries. See [troubleshooting](docs/TROUBLESHOOTING.md) for the known limitation and fixes that are in the runtime.

For another region, set `RCLOL_REGION` and `RCLOL_LOCALE` before launch. For example `RCLOL_REGION=NA RCLOL_LOCALE=en_US ./scripts/run.sh`. Linux display selection follows `$DISPLAY`; the legacy launcher fallback is `:1`.

If the game or Riot client was closed but `darlingserver` is still running, opt in to partial recovery before the next launch:

```sh
RCLOL_RECOVER_STALE_CLIENT=1 ./scripts/run.sh
```

It stops only a windowless Riot/League/CEF tree at least 60 seconds old,
preserves `darlingserver`, launchd/mldr, sockets and `.init.pid`, and then
starts the product normally. It recognizes `LeagueClientUx`, `Riot Client` and
`RiotClientServices` windows, does nothing while a game or managed client window
is present, and fails closed when X11 properties cannot be read. See
[troubleshooting](docs/TROUBLESHOOTING.md#client-remains-running-without-a-window).

If repeated launches leave several `close-league-client-in-game.py` watchers,
opt in to removing the orphaned ones before the new helper starts:

```sh
RCLOL_CLEAN_STALE_HELPERS=1 ./scripts/run.sh
```

It only removes helpers of this prefix whose parent is `init`/`systemd` (the
launcher that started them has exited). A helper of a live launcher, another
prefix, the game, Riot/League/CEF, `darlingserver` and the runtime are never
touched. See [troubleshooting](docs/TROUBLESHOOTING.md#multiple-client-in-game-helpers).

For automatic client handling during a match, opt in with one switch:

```sh
RCLOL_CLIENT_IN_GAME_TRICKS=1 ./scripts/run.sh
```

It reads `lol-user-experience` from the installed League client's
`LCULocalPreferences.yaml`. When `potatoModeEnabled` is true, it closes the
client UI if `closeLeagueClientDuringGame` is true, and hides the
`LeagueClientUx`/`Riot Client` X11 windows when that value is false. Missing or
invalid preference values, disabled client optimizations and unreadable files
select no action. The `RCLOL_CLOSE_CLIENT_IN_GAME` and
`RCLOL_HIDE_CLIENT_IN_GAME` low-level switches remain available when the
automatic switch is not set. The helper exits after ten minutes without a
client or match once it has seen one. See
[troubleshooting](docs/TROUBLESHOOTING.md#automatic-client-handling-during-a-match)
for the measured effect and caveats.

## Testing

Start with standalone regression checks, then play a match manually. See [testing](docs/TESTING.md). Do not attach a debugger, query client APIs, inject diagnostic hooks or automate client/game input. The project includes standalone compatibility probes and the opt-in host-side window-management helpers described above, but no client injection hooks, client API automation or input automation; the normal launcher enables none of them.

FPS counters, game presentation requests and physical display refresh are different measurements. Record average and p99 frame times, the active scene, graphics settings, charger/power state and whether the game stayed focused. See [current status](docs/STATUS.md).

On the Ryzen 5 5500 / RX 6600 test PC, ARAM on Hexgate went from 84 to 135 FPS average over 2026-10-13/14, with the slowest 10-second stretches around 119 in the best match (one match so far with Hyprland's direct scanout off; [status](docs/STATUS.md#game-fps-2026-10-1314)). The game-process speed switches and their opt-out files are listed in [setup](docs/SETUP.md#game-process-switches), and passive match capture is described in [testing](docs/TESTING.md#passive-match-capture).

To update an existing installation, exit the game and both clients, then:

```sh
git pull
./scripts/update.sh
sh scripts/run.sh
```

`update.sh` re-applies the patches that changed (reverting the earlier version of each, so other edits in the source tree survive), rebuilds incrementally, and reinstalls the base runtime and the per-user overrides. It refuses to run while a Riot or League process is open.

For updating single components, [incremental update instructions](docs/SETUP.md#updating-an-existing-runtime) explain the server and memory installers, user-owned backups and the full Darling restart needed to activate replacements. Perform activation only after manually exiting the game and both clients.

## Layout

```
scripts/             portable entry points
upstream/manifest.json  exact base revisions and patch ownership
patches/             current source changes, one patch per repository
tools/               runtime templates, installers and standalone regression probes
docs/                setup, testing, status, compliance and interoperability notes
build/               local generated sources, outputs and rendered tools (ignored; not tracked)
```

Darling/upstream components retain their existing licenses; see [third-party notes](NOTICE.md). Original integration tooling is distributed under GPL-3.0; patches retain the licensing of their target files.

## Interoperability and compliance

This project is an unofficial interoperability effort. It distributes source patches for Darling and original tooling, not the Riot client, game code, assets or accounts. The normal launcher does not patch the client, game, CEF or anti-cheat. Users obtain the client from Riot and are responsible for complying with Riot's terms; account restrictions are possible. See [interoperability and compliance scope](docs/INTEROPERABILITY.md) and [compliance guidance](docs/COMPLIANCE.md). Neither document is legal advice.

## Trademarks

League of Legends and Riot Games are trademarks or registered trademarks of Riot Games, Inc.
This project is an unofficial compatibility effort and is not affiliated with, endorsed by, or
sponsored by Riot Games. No game client, game assets, or account data are distributed in this
repository.

See [compliance and terminology guidance](docs/COMPLIANCE.md) and [interoperability and compliance scope](docs/INTEROPERABILITY.md) for the project's scope and review expectations.
