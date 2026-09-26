# Changelog

All notable changes to the VSDD kit. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Each release is tagged `v<version>`.

Installs record the kit version in `openspec/.vsdd.json`. To see whether a project is
behind, run `vsdd-kit status --root <project>`. To upgrade it, re-run the installer
command that `status` prints.

## [Unreleased]

## [0.3.1] - 2026-09-26

### Fixed
- Reinstalling after a rollback reused the old install's snapshot. When a project
  had an earlier `vsdd-install` branch (deleted since), the installer took the
  snapshot of that old install as its own, so a later rollback, with
  `--restore-global`, could put back a months-old global OpenSpec config. A new
  install branch now always gets a new snapshot. A re-run only reuses a snapshot
  taken after its branch was created.
- README and `SETUP.md` gave `KIT` as "what `vsdd-kit path` prints", but `uvx`
  installs nothing, so there is no `vsdd-kit` on the PATH. They now give the full
  `uvx --from <source> vsdd-kit path` command.

## [0.3.0] - 2026-09-26

### Added
- `vsdd-kit validate`, `overlay` and `merge`: the project-side scripts, for projects
  installed with `--tooling-dir`, which hold no copy of them.
- A worked example, `examples/book-notes`: a real change from proposal to merge, with
  the code. The smoke test replays it, and requires its Source of Truth to match byte
  for byte.
- `CONTRIBUTING.md`, issue templates and this changelog.

### Fixed
- The CI template failed on its first run after a `--tooling-dir` install, because it
  called the project's `scripts/vsdd/`, which such installs don't have. It now runs
  the kit release recorded in `openspec/.vsdd.json` with `uvx` in that case. It skips
  the overlay check, with a message, when the skills live in a shared workspace folder.
- The CI template now also runs on pull requests that change skills or commands, not
  only on pushes. mermaid-cli is pinned to major version 11.

## [0.2.0] - 2026-09-26

### Added
- The `vsdd-kit` command, runnable without cloning:
  `uvx --from git+https://github.com/joecrowley/vsdd-kit@v0.2.0 vsdd-kit ...`.
  Subcommands `install`, `status`, `preflight`, `snapshot`, `guide` (prints the
  runbook) and `path` (the kit folder inside the package, usable as `KIT`).

### Changed
- `SETUP.md` covers only the normal path: run the installer, then the steps it leaves
  to you. It is about a third of its old length. The manual steps, workspaces,
  maintenance, troubleshooting, rollback and uninstall moved to
  `docs/SETUP-REFERENCE.md`. (`VERSION` read 0.1.1 for this change, but it was never
  tagged.)

### Fixed
- A missing prerequisite (bad `--root`, unknown tool, old OpenSpec) made the installer
  exit 1, which the runbook reads as "a step failed, continue by hand". It now exits
  2, as documented.
- `kit_commit` is recorded only when the kit is a git clone. A packaged kit inside
  another repository no longer records that repository's commit.

## [0.1.0] - 2026-09-26

The first tagged release. It contains everything since the kit began, on 2026-09-24.

### Added
- The `visual-driven` OpenSpec schema: `proposal → diagrams → specs → design → tasks`.
  Each change's `diagrams.md` has a gate, a Placement table (`update`, `add`,
  `move from`, `remove`), a verbatim Before State, an After State and, when the build
  differs from the plan, Deviations.
- Diagram ownership: a diagram lives with the capability it describes. Adding one to
  the architecture file needs a `Why here` reason.
- `validate_mermaid.py`: Mermaid guardrails for LLM-written diagrams, change
  structure, the verbatim Before check, and `--render` with mermaid-cli.
- `merge_diagrams.py`: the deterministic archive merge. It refuses to merge if the
  Source of Truth changed after the change was proposed.
- The skill and command overlay for all 40 AI tools OpenSpec supports. It survives
  `openspec update`, and `--check` in CI catches a wiped overlay. `/opsx` commands
  become wrappers, so they can't bypass the VSDD steps. The key steps are repeated in
  `config.yaml` `operations` as a backstop.
- An architecture decisions log: fixes that reveal a recurring pattern become rules
  that later designs read first.
- `vsdd_install.py`, the one-shot installer. It does the mechanical steps, and stops
  with exit 3, naming a flag, whenever a decision is the user's.
- Safe installs into existing OpenSpec projects (`openspec_preflight.py`, which
  predicts what `openspec update` would delete, and `--safe-update`). Reversible
  installs: an install branch, plus a snapshot of what git can't restore.
- A choice of how VSDD appears in an existing `AGENTS.md`: a routing section, a
  one-line pointer, or nothing.
- Workspaces that share one folder of `/opsx` commands. `--tooling-dir` keeps the
  kit's docs and scripts out of the project, or uses the kit clone in place.
- Upgrades: overlay blocks end with `<!-- /vsdd:<id> -->`, so re-running the installer
  refreshes them. Installs record the kit version in `openspec/.vsdd.json`, and
  `--status` reports whether a project is behind.
- The kit's own CI: the smoke test on every push, and weekly against the latest
  OpenSpec.

### Fixed
- OpenSpec 1.13 support: the `operations` backstop, `changeRoot`, and the
  `update-change` skill.

[Unreleased]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/joecrowley/vsdd-kit/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/joecrowley/vsdd-kit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joecrowley/vsdd-kit/releases/tag/v0.1.0
