# VSDD Setup Runbook (for AI coding agents)

You are an AI coding agent. The user has asked you to install **Visual Spec-Driven
Development (VSDD)** into a project. VSDD extends OpenSpec so that every change
records a Before/After Mermaid delta, and archiving merges the After state into a
canonical diagram Source of Truth. Follow this runbook top to bottom.

The installer script does the mechanical Steps 0–5. This file covers running it and
everything it leaves to you. [`docs/SETUP-REFERENCE.md`](docs/SETUP-REFERENCE.md) has
the manual version of Steps 0–5, shared workspaces, maintenance, troubleshooting,
rollback and uninstall: read the part you need only when a step below sends you
there.

## Rules for executing this runbook

1. Run the steps **in order**. Each step ends with a **Verify** block. Do not start
   the next step until Verify passes.
2. If a Verify fails twice, **stop** and report to the user: the step, the command,
   its output, and what you tried.
3. **Never overwrite** a file that already exists in the target unless the step
   says so. Where a step says to ASK, ask the user and wait for the answer.
4. Only the steps marked **ASK** need user input. Make every other decision
   yourself and report it at the end.
5. Record what you do. The final step asks for a summary.

## Variables

| Name | Meaning |
|---|---|
| `KIT` | The directory containing this `SETUP.md`. Its files are under `KIT/files/`. |
| `ROOT` | The target project's root, where the setup is installed. Run commands from `ROOT`. |
| `TOOLS` | The AI tools the team uses, as OpenSpec tool ids: `claude`, `opencode`, `qwen`, `cursor`, `codex`, `github-copilot`, `windsurf`, `gemini`, ... (full list: `openspec init --help`). |

---

## Steps 0–5 — Run the installer

`vsdd_install.py` does the mechanical work in a few seconds: install branch and
snapshot, `openspec init`/`update`, copying the files, the config keys,
`AGENTS.md`/`CLAUDE.md`, and the overlay. It runs each step's Verify, and creates an
empty decisions log. It never makes an **ASK** decision. When one is needed, it stops
before changing anything and names the flag that records the user's answer.

1. **ASK** the user to confirm `TOOLS`. Tool folders that already exist in `ROOT`
   (`.claude`, `.opencode`, `.qwen`, `.cursor`, ...) are strong hints.
2. Dry run:

   ```bash
   python3 "$KIT"/files/scripts/vsdd/vsdd_install.py --root "$ROOT" --tools <TOOLS> --dry-run
   ```

   - **Exit 0:** it prints the plan. Go to 3.
   - **Exit 3:** it lists the decisions needed, each with its options. **ASK** the
     user each one, then re-run with the flags it names. If you need more detail to
     explain an option, read the step in the reference:

     | Decision | Flag | Details in [`docs/SETUP-REFERENCE.md`](docs/SETUP-REFERENCE.md) |
     |---|---|---|
     | Uncommitted changes | `--allow-dirty` | Step 0 |
     | `openspec update` would delete workflows | `--update safe` or `--update plain` (or the user fixes their profile and you re-run) | Step 1 |
     | Custom schema | `--custom-schema switch` or `--custom-schema keep` | Step 3 |
     | Home-folder tool (MiniMax) | `--extra-dir ~/.minimax` | Step 0 |
     | `AGENTS.md` already exists | `--agents-md full`, `pointer` or `skip` | Step 4 |
     | A shared workspace folder has OpenSpec commands | `--extra-dir <folder>` (usually with `--tools none`), or `--leave-shared` | Workspaces with a shared command folder |
     | (Optional) keep the kit's docs and scripts out of the project | `--tooling-dir <folder>` | Workspaces with a shared command folder |
     | Hand-edited skills | none: do Step 1b by hand, then re-run | Step 1b |

   - **Exit 2:** a prerequisite is missing (OpenSpec CLI ≥ 1.2.0, Python ≥ 3.9, tool
     ids). It says which; **ASK** the user to fix it. Don't install global packages
     yourself without permission.
3. Run it without `--dry-run`, with the same flags.
   - **Exit 0:** Steps 0–5 are done. Do the items in its **"Left for you"** list, in
     order ([below](#the-installers-to-do-list)), then Steps 6 to 9.
   - **Exit 1:** a step failed. Everything before it is done (its "Done" list says
     what). Continue by hand from the failed step in [`docs/SETUP-REFERENCE.md`](docs/SETUP-REFERENCE.md).

Add `--json` for machine-readable output. Re-running the installer is safe: it
upgrades an existing install, and on the install branch a re-run changes nothing.
It records the kit version, tools and folders in `openspec/.vsdd.json`; commit that
file with the rest. `--status` compares an install with the kit and changes nothing
(exit 0 up to date, 1 upgrade due, 2 not installed).

**Verify:** the installer exited 0, and printed `check OK` for the overlay.

---

## The installer's to-do list

Each item names the step it belongs to. Most are self-explanatory; these need more:

### Write the project context

For "Step 3: fill in `context:`": replace the placeholders in `openspec/config.yaml`
with facts from the project itself. Read the README, the package manifests
(`package.json`, `pubspec.yaml`, `pyproject.toml`, `go.mod`, ...) and the top-level
directory layout. Keep it to 4–8 lines of facts agents need: what the project is, the
stack, the layout, and the conventions agents get wrong. Don't invent conventions you
can't see in the code. Leave the optional `Pitfalls` line out until the decisions log
has entries.

**Verify:** create the throwaway change Step 8 uses, and check that your text reaches
the instructions, with no `<PROJECT_NAME>` placeholder left:

```bash
openspec new change vsdd-smoke-test
openspec instructions proposal --change vsdd-smoke-test | grep -A8 "<project_context>"
```

### Everything else

| To-do | What to do |
|---|---|
| Step 2: `docs/MERMAID_RULES.md` differs | Diff it against `KIT/files/docs/MERMAID_RULES.md`. Keep the project's own rules, add the kit's new ones |
| Step 3 (ASK): a `prompts:` key | Show the user its contents, then ask whether to rename it to `rules:`. Stale rules can do more harm than none |
| Step 3: config entries couldn't be added / Step 3 (b): custom schema | Step 3 in [`docs/SETUP-REFERENCE.md`](docs/SETUP-REFERENCE.md) |
| Step 4: AGENTS.md TODO line | Replace it with a one-line description of the project |
| Step 4 (ASK): older diagram rules in AGENTS.md | **ASK** before removing them: the VSDD section and `docs/VSDD.md` replace them |

---

## Step 6 — Seed the diagram Source of Truth

VSDD needs a baseline, otherwise every Before state is empty. Build it from the
**real code**, not from the example's placeholders.

1. Create `ROOT/openspec/specs/architecture/diagrams.md`, using
   `KIT/files/openspec/specs/architecture/diagrams.md.example` for structure only.
2. Write **2–4** diagrams for the most important cross-cutting concerns:
   - **Module Hierarchy** (`flowchart TD`): from the package manifests and imports.
   - **End-to-End Data Flow** (`sequenceDiagram`): one representative user action,
     traced through the real classes or functions.
   - A **state machine** (`stateDiagram-v2`) for the most central stateful component,
     if there is one.
   - **System Topology** (`flowchart LR`): if there is backend or infrastructure code
     (IaC, Docker, serverless configs).
3. Use actual names from the code, and search for each participant or node to
   confirm it exists. A wrong baseline is worse than none.
4. **ASK** the user whether to also seed capability-level diagrams
   (`openspec/specs/<capability>/diagrams.md`) for 1–3 high-traffic capabilities.
   Only do so if `openspec/specs/<capability>/` already exists.
5. Follow `docs/MERMAID_RULES.md` exactly.
6. **Decisions log.** If `ROOT/openspec/specs/architecture/decisions.md` doesn't exist,
   create it with the header and introduction from
   `KIT/files/openspec/specs/architecture/decisions.md.example`, **without** the
   example entry. Don't invent rules. If the project already documents conventions
   that agents get wrong (in `AGENTS.md`, a contributing guide, or past fixes the
   user mentions), **ASK** whether to turn up to three of them into entries, with
   `Source: install`.

**Verify:**

```bash
python3 scripts/vsdd/validate_mermaid.py            # "OK: ... 0 problems"
python3 scripts/vsdd/validate_mermaid.py --render   # if mmdc is installed
```

---

## Step 7 — CI (optional)

**ASK** whether to add CI. If the project uses GitHub Actions (`ROOT/.github/`
exists) and the user agrees, copy `KIT/files/ci/github/vsdd.yml` to
`ROOT/.github/workflows/vsdd.yml`. It lints and renders diagrams, and fails if an
`openspec update` has wiped the overlay.

For other CI systems, add a job that runs:

```bash
npm install -g @mermaid-js/mermaid-cli
python3 scripts/vsdd/validate_mermaid.py --render
python3 scripts/vsdd/install_overlay.py --check
```

**Verify:** the workflow file is valid YAML
(`python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/vsdd.yml`,
if PyYAML is available). The first real run happens on the next push.

---

## Step 8 — End-to-end smoke test

Use the `vsdd-smoke-test` change from the context check (or the manual Step 3). If
it doesn't exist, create it: `openspec new change vsdd-smoke-test`.

1. Write `openspec/changes/vsdd-smoke-test/diagrams.md` as a **YES** gate that
   modifies one Source of Truth diagram from Step 6:
   - `## Diagram needed?` → `YES - smoke test`
   - `## Placement` → one row: `| <Stable Name> | specs/architecture/diagrams.md | update |`
   - `## Before State` → `### <Stable Name>`, copied verbatim
   - `## After State` → the same `### <Stable Name>` with one added node
2. Run `python3 scripts/vsdd/validate_mermaid.py`. It must report 0 problems.
3. Break it deliberately, and re-run after each break. It **must** report every problem.
   Undo each break before the next:
   - delete the flowchart direction, or add a `;`;
   - edit one word inside the Before copy (not verbatim);
   - change the Placement action to `remove` (a removed diagram can't have an After
     section).
4. **Do not archive** the smoke test. Delete it: `rm -rf openspec/changes/vsdd-smoke-test`.
5. Confirm that `git status` shows no changes under `openspec/specs/` other than your
   Step 6 files.

**Verify:** each check above behaved as described.

---

## Step 9 — Report to the user

Reply with:

```markdown
## VSDD installed
- OpenSpec <version>, tools: <TOOLS>
- Schema: visual-driven (validated)
- Config: context + rules (<created | updated - note if `prompts:` was renamed>)
- Agent files: <AGENTS.md created / section / pointer / skipped>, <CLAUDE.md created/updated/n.a.>
- Overlay: <N> skills patched, <M> commands wrapped (check: OK)
- Source of Truth: <files and stable section names>
- Decisions log: <created empty | N entries | already existed>
- CI: <added .github/workflows/vsdd.yml | skipped | instructions given>
- Smoke test: passed, removed
- In-flight changes: <list from the preflight, or "none">. They keep their original
  schema, so they have no diagrams.md and their archive does no diagram merge
- Branch: <vsdd-install | not a git repo>. Snapshot: <snapshot dir>
- Decisions I made: <list>
- Needs your attention: <anything skipped, failed, or deferred>
- To undo the whole install: see "Roll back an install" in docs/SETUP-REFERENCE.md in the kit

Next: try `/opsx:propose <small change with a visual impact>` and review its diagrams.md.
```

Then suggest the user commit everything on the install branch as a single commit,
for example `chore: install visual spec-driven development (VSDD)`, review it, and
merge the branch when they're happy. Do not commit or merge unless asked. Point them
at the Maintenance table in `docs/SETUP-REFERENCE.md` for later upkeep, especially
what to run after `openspec update`.
