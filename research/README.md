# Research notes

The historical investigation source that used to live in `research/tools/` (version-specific probes, inspectors, profilers and abandoned experiments) has been removed. Those tools automated, inspected or captured the Riot client/game, so they are no longer part of this repository.

Prefer the scripts at the repository root and the current tools described in `docs/`. Logs, client binaries, game assets, account data, generated shader captures and backups are deliberately absent.

`research/diagnostics/` holds the only remaining interposing diagnostic. It is diagnostic only, never for a real account or live servers, and is excluded from every install/build/launch path; see its README.
