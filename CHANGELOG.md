# Changelog

All notable changes to the VSDD kit. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Each release is tagged `v<version>`.

Installs record the kit version in `openspec/.vsdd.json`. To see whether a project is
behind, run `vsdd-kit status --root <project>`. To upgrade it, re-run the installer
command that `status` prints.

## [Unreleased]

### Fixed
- The installer didn't check Python, although `SETUP.md` said it exits 2 for
  Python < 3.9. Under `uvx` the install itself worked with uv's own Python, but every
  later step (validator, archive merge, overlay) runs `python3 scripts/vsdd/...` and
  failed when `python3` was missing, didn't run (macOS's Xcode stub) or was too old.
  The installer now checks that `python3` is on PATH, runs, and is 3.9 or later, and
  exits 2 with how to fix it before changing anything.

### Changed
- README requirements list `python3` (and why `uvx` doesn't replace it), uv with its
  install command, and the macOS `python3` stub.

## [0.3.5] - 2026-09-28

### Changed
- A decision's **Source:** is the change's dated archive folder name
  (`2026-01-15-fix-detail-flicker`). The archive's decisions step runs before the
  change is moved, so agents saw only the bare change name and wrote that. The step now
  says to form the name from today's date and the change name, and the validator warns
  (without failing) about a Source that has no date and isn't `install`.

## [0.3.4] - 2026-09-27

### Fixed
- The validator failed on a change that had just been merged but not yet moved to the
  archive: its Before copies no longer match the Source of Truth, by design. The
  archive skill runs the validator at exactly that point and says to fix any errors,
  so an agent could "fix" the Before copy or merge twice. The validator now
  recognises an already-merged change (the same check `merge_diagrams.py` uses, now
  shared) and skips the verbatim-Before check for it.
- `vsdd-kit status` printed its upgrade command as `vsdd-kit install ...`, which
  doesn't exist in the user's shell when the kit runs through `uvx`. It now prints the
  pinned `uvx --from git+https://github.com/joecrowley/vsdd-kit@v<version> vsdd-kit`
  form, and `vsdd-kit` only when that works (pipx, or an active virtualenv).
- A re-run of the installer reported "overlay: 8 file change(s)" even when the
  skills ended up byte-identical: `openspec update` had just regenerated them, and the
  overlay re-applied the same blocks. It now counts the skill and command files that
  differ from before the run.

### Changed
- The archive's decisions step no longer turns the existing pattern into a rule. A
  change that just follows what the code already does doesn't set a convention, even
  when its design chose that "for consistency", and most of all when the design lists
  a cost of the pattern. In a test run, a notes change copied a reload that makes the
  detail screen flicker, and the archive proposed "Reload After Write: never patch in
  place", making the bug a rule. As with 0.3.2, existing installs get the new wording
  when the overlay is re-applied; the `config.yaml` backstop line changes only on new
  installs.
- Stopping on uncommitted changes (exit 3): on an install branch with an earlier
  install, the message says when `--allow-dirty` is safe (the changes are only that
  install and work done with it, as in a trial run kept uncommitted). The Step 0
  reference says the same.

## [0.3.3] - 2026-09-27

### Fixed
- `SETUP.md` Step 9: the install report's next step always said `/opsx:propose`, the
  Claude Code form. OpenCode and Qwen name the command `/opsx-propose`, so their users
  were given a command that doesn't exist. The report now uses the installed tools'
  form.

### Added
- `THIRD_PARTY_NOTICES.md`: the kit's `visual-driven` schema and templates are adapted
  from OpenSpec's `spec-driven` schema (MIT, © 2024 OpenSpec Contributors). The notice
  names what was adapted and includes OpenSpec's license. The wheel ships it, and
  `schema.yaml` now starts with a short notice, so each project's installed copy
  credits OpenSpec too.

### Changed
- `docs/concept-report.md` starts with a note: it's the pre-kit background research,
  kept as it was. Its claims aren't linked to individual sources, so check them before
  quoting.

## [0.3.2] - 2026-09-27

### Changed
- The archive's decisions step now also asks whether the change deliberately does
  something differently from existing code that does the same kind of thing. For
  example, a new write that refreshes in place while an existing write still reloads
  through a loading state. That difference is drafted as a decision, whose
  **Applies to:** names the code that doesn't follow it yet. Before, an archive could
  report "Decisions: none" for a change that left two writes behaving differently.
  A `none` now comes with a one-line reason. Existing installs get the new wording
  when the overlay is re-applied (re-run the installer, or `install_overlay.py`). The
  matching `operations.archive.guidance` line in `config.yaml` is only written on new
  installs: copy it from `files/openspec/config.yaml.example` to update an existing one.
- `SETUP.md` Step 9: the install report tells the user to start a new agent session
  before the first `/opsx` command. Agents load commands when a session starts, so the
  commands the install creates aren't available in the session that ran it.
- `docs/SETUP-REFERENCE.md` Troubleshooting: two new rows, for `/opsx` commands being
  unknown right after an install, and for the misleading `with schema 'spec-driven'`
  line that `openspec new change` prints before it applies `schema: visual-driven`.

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

[Unreleased]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.5...HEAD
[0.3.5]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/joecrowley/vsdd-kit/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/joecrowley/vsdd-kit/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/joecrowley/vsdd-kit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/joecrowley/vsdd-kit/releases/tag/v0.1.0
