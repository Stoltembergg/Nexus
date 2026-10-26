# Host prerequisite checks

Run the read-only checker before setup:

```sh
python3 scripts/preflight.py --mode build
python3 scripts/preflight.py --mode runtime --json
```

It starts host inspection tools only, not Darling or Riot, and never installs
packages, uploads reports, or collects client/account data. Raw command output,
environment values and Xauthority paths are not printed. Use a trusted PATH:
like the build itself, the checker executes the host tools selected there.

## Blocking checks

- Linux x86-64, kernel >= 5.14.
- Python >= 3.12, matching this source tree's existing requirement. The proposed
  upstream Python-3.10 migration has not been integrated.
- CMake >= 3.20 and Git LFS >= 2.13.
- Clang and llvm-config >= 16 with matching major versions. LLVM 22/23 is the
  primary patch baseline; other matching versions produce a warning.
- llvm-objdump and llvm-nm >= 16, with the same major as llvm-config.
- Git, Make, curl, unzip and pkg-config available on PATH.
- Vulkan development headers >= 1.3 discoverable through pkg-config.

The existing binary inspection tools still invoke unversioned LLVM commands.
Therefore versioned tools alone do not satisfy this check. On distributions
with versioned installations, select the matching LLVM bindir on PATH (for
example, the directory reported by that installation's llvm-config --bindir).
No symlinks or system configuration are changed automatically.

Matching executable versions does not verify which shared LLVM library an
already-built Iridium will load. Runtime binary/library verification is a
separate requirement; a passed preflight does not replace it.

## Graphics checks

Vulkan is checked with text-mode `vulkaninfo`. API >= 1.3 and timeline-semaphore
support must belong to the **same physical device**. Missing or incomplete
inventories are unverified, not a successful capability check. Finding one
capable device does not guarantee that the launcher will select it; hybrid-GPU
selection remains a separate concern.

For X11/Xwayland, DISPLAY must be set. If xdpyinfo is installed it probes access;
otherwise glxinfo -B is used. An unavailable probe tool is advisory, not proof
that the display is broken. Install one to remove that unverified state.

Graphics failures warn in `build` mode, since headless compilation is valid.
They block `runtime` mode, where an accessible display and supported GPU are
needed. A missing display-probe tool remains a warning in either mode.

## Setup integration and limits

`scripts/build.sh` checks before configure/fetch/build. `install-runtime.sh`
checks before configure, readiness invalidation or prefix initialization;
rootless idle/base-readiness guards still run first. An error exits nonzero
before expensive or mutable setup actions. Warnings are visible but nonblocking.

The legacy tools/env-check.sh is not the authoritative version/capability gate.
Use this checker for the versioned report. No bypass variable was introduced.

This is not a full dependency audit or runtime acceptance test. It does not
authenticate to Riot, assert macOS signing state, establish Riot approval, or
demonstrate that an account will not be restricted.
