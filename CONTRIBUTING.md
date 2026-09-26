# Contributing to the VSDD kit

Thanks for helping. Bug reports from real projects are the most useful contribution
of all, especially when VSDD gets in the way. See [Reporting a problem](#reporting-a-problem).

## Setting up

You need:
- the [OpenSpec CLI](https://github.com/Fission-AI/OpenSpec): `npm install -g @fission-ai/openspec`
- Python 3.9 or later. The scripts use only the standard library.
- optional: [uv](https://docs.astral.sh/uv/) for the package checks,
  [mermaid-cli](https://github.com/mermaid-js/mermaid-cli) (`mmdc`) for render checks,
  and PyYAML for the CI template checks. The smoke test skips what's missing and says so.

Then clone the kit and run the smoke test:

```bash
git clone https://github.com/joecrowley/vsdd-kit && cd vsdd-kit
tests/smoke_test.sh
```

It builds throwaway projects in your temp folder, and uses an isolated OpenSpec
config, so your own setup isn't touched. It ends with `All checks passed.`

## How the kit fits together

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) first. It maps which script does
what and who calls whom. `files/` mirrors what gets installed into a project.
`vsdd_kit/` is the `vsdd-kit` command, which runs those same scripts.

## Rules for changes

- **Every behaviour change comes with a check in `tests/smoke_test.sh`.** A change to a
  script without a matching check is incomplete. A failing check is easier to review
  than a claim in a PR description.
- **Keep the scripts on the standard library.** They're copied into users' projects
  and run in their CI.
- **Never rename an overlay block's `<id>`** (`<!-- vsdd:<id> -->`). Upgrades find
  blocks by id.
- **Diagrams follow [`files/docs/MERMAID_RULES.md`](files/docs/MERMAID_RULES.md).**
  After editing one, run `python3 files/scripts/vsdd/validate_mermaid.py <file> --render`.
- **Update `docs/ARCHITECTURE.md`** (diagram and table) when you add a script or
  change who calls whom.
- **Add a line under `[Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md)** for anything a
  user would notice.
- **Don't edit `examples/book-notes/` by hand.** It's the output of a real run, and the
  smoke test replays it. If a merge change makes it fail, that's a real behaviour
  change: say so in the PR, and regenerate the example with a new run.

## When OpenSpec releases a new version

The overlay inserts VSDD steps at anchor lines in the skills OpenSpec generates. A new
OpenSpec version can change that text. The kit's CI runs weekly against the latest
OpenSpec to catch this.

1. Upgrade (`npm install -g @fission-ai/openspec@latest`) and run `tests/smoke_test.sh`.
2. On `anchor not found for <ids>`, open `files/scripts/vsdd/install_overlay.py`,
   find those ids in `PATCHES`, and update their anchor regexes to match the new stock
   skill text. Run `openspec init --tools claude` in a scratch folder to see it.
3. Keep the old anchor as a second alternative where you can: anchors are tried in
   order, so older OpenSpec versions keep working.
4. Re-run the smoke test, and note the OpenSpec version in `CHANGELOG.md`.

## Releasing

Installs record `VERSION` in `openspec/.vsdd.json`, and a project's CI fetches the tag
`v<VERSION>`. So `VERSION` only changes in a release commit, together with its tag:

1. Move the `[Unreleased]` entries in `CHANGELOG.md` to a new version heading, with
   the date, and update the compare links at the bottom.
2. Set `VERSION`, following semver: a patch for fixes, a minor version for new
   features, a major version for changes that need users to act.
3. Merge, then tag the merge commit `v<VERSION>` (annotated) and push the tag.
4. Check the release from a clean machine:
   `uvx --from git+https://github.com/joecrowley/vsdd-kit@v<VERSION> vsdd-kit --version`.

## Reporting a problem

Open an issue using the bug report template. The most useful details are:

- `openspec --version`, `python3 --version`, and your OS
- the AI tools you installed for (`--tools`)
- the installer's machine-readable output: `vsdd-kit install ... --json`, or
  `vsdd-kit status --root <project> --json` for an existing install
- for a diagram problem: the change's `diagrams.md`, and the validator's output

Ideas are welcome as issues too. Say what you were trying to do, and where VSDD got
in the way.
