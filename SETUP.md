# VSDD Setup Runbook (for AI coding agents)

You are an AI coding agent. The user has asked you to install **Visual Spec-Driven
Development (VSDD)** into a project. VSDD extends OpenSpec so that every change
records a Before/After Mermaid delta, and archiving merges the After state into a
canonical diagram Source of Truth. Follow this runbook top to bottom.

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

## Step 0 — Preflight

Run and record the results:

```bash
git -C "$ROOT" status --porcelain | head
openspec --version
python3 --version
node --version; mmdc --version
ls -d "$ROOT"/openspec "$ROOT"/.claude "$ROOT"/.opencode "$ROOT"/.qwen "$ROOT"/.cursor "$ROOT"/.github 2>/dev/null
```

Decide:

- **Uncommitted changes** in `ROOT`: **ASK** whether to continue. Recommend
  committing first so the whole setup can be reviewed as one diff.
- **`openspec` missing or older than 1.2.0**: **ASK** the user to install or upgrade
  it (`npm install -g @fission-ai/openspec@latest`), then re-run the check. Do not
  install global packages yourself without permission.
- **`python3` missing or older than 3.9**: stop. The kit scripts need it.
- **`mmdc` missing**: continue. Rendering checks are optional locally (the linter
  still runs), and CI installs mermaid-cli itself.
- **Choosing `TOOLS`**: tool folders that already exist (`.claude`, `.opencode`,
  `.qwen`, ...) are strong hints. **ASK** the user to confirm the list.

**Inspect an existing OpenSpec setup** (after `TOOLS` is confirmed). This runs from
the kit, because the project doesn't have the scripts yet:

```bash
python3 "$KIT"/files/scripts/vsdd/openspec_preflight.py --root "$ROOT" --tools <TOOLS comma-separated>
```

It reports what Step 1 needs to know, and asks OpenSpec itself, so the answers are
exact for the installed CLI version:

| Report line | Meaning | Where it's handled |
|---|---|---|
| `Project initialised: no` | Fresh install | Step 1, `init` branch |
| `!! openspec update would DELETE: …` | Workflows installed in the project are missing from the user's **global** OpenSpec profile, so a plain `openspec update` removes their skills and commands | Step 1 (ASK) |
| `Tools to add: …` | Requested tools that aren't set up in this project yet | Step 1 |
| `Configured schema: … <- CUSTOM` | The project uses its own schema | Step 3 (ASK) |
| `In-flight change: …` | Changes created before VSDD. They keep their schema | Step 9 report |
| `(not an OpenSpec tool folder …)` | A folder with copies of OpenSpec skills that OpenSpec doesn't manage | Step 5 patches it too. Mention it in the report |

**Detect an earlier VSDD install:**

```bash
ls "$ROOT"/openspec/schemas/visual-driven 2>/dev/null
grep -rl "vsdd:" "$ROOT"/.*/skills/openspec-*/SKILL.md 2>/dev/null | head -3
grep -rli "diagram" "$ROOT"/.*/skills/openspec-*/SKILL.md 2>/dev/null | head -3
```

| Finding | Meaning | Action |
|---|---|---|
| Nothing found | Fresh install | Continue |
| `vsdd:` markers found | This kit is already installed | Treat as an upgrade. Steps are idempotent |
| "diagram" found but no `vsdd:` markers | Skills were **hand-edited** for diagrams | Follow **Step 1b** before Step 5, or the steps will be duplicated |

**Verify:** you have values for `ROOT` and `TOOLS`, `openspec --version` is ≥ 1.2.0,
and `python3` works.

---

## Step 1 — Initialise or update OpenSpec

- **No `ROOT/openspec/` directory:**

  ```bash
  openspec init --tools <TOOLS comma-separated> "$ROOT"
  ```

- **`ROOT/openspec/` exists:** OpenSpec is already set up. **Don't run `init` over
  it for the existing tools, and don't run a plain `update` until you've checked
  the preflight report.** If you found hand-edited skills in Step 0, do Step 1b
  **first**.
  1. **If the report shows `openspec update would DELETE: …`**, **ASK** the user,
     explaining that those workflows' skills and commands would be removed:
     - **(Recommended)** they add the workflows to their global profile themselves,
       by running `openspec config profile` in a terminal (it's interactive, and
       their global setting). Re-run the preflight until the line is gone, then run
       `openspec update "$ROOT"`.
     - Or keep the profile as it is and run
       `python3 "$KIT"/files/scripts/vsdd/openspec_preflight.py --root "$ROOT" --safe-update`.
       It runs `update` with a temporary config that keeps every installed
       workflow, and doesn't touch their global config. Tell the user that any
       later plain `openspec update` will still delete them.
     - Or accept the deletion. Only do this if the user explicitly says so.
  2. **Otherwise**, run `openspec update "$ROOT"`.

  `update` regenerates the stock skills and commands for the tools already set
  up, and **overwrites any edits to them**. The overlay in Step 5 re-applies the
  VSDD additions.
  3. **If the report shows `Tools to add: …`**, add them with
     `openspec init --tools <those tools> "$ROOT"`. On a project that is already
     set up, `init` only adds the new tools: it leaves `openspec/config.yaml` and
     the other tools' skills alone.

### Step 1b — Hand-edited skills (only if Step 0 found them)

1. Back them up: `mkdir -p "$ROOT"/.vsdd-backup && cp -R "$ROOT"/.<tool>/skills "$ROOT"/.vsdd-backup/<tool>-skills`
   for each tool directory.
2. Diff each hand-edited skill against a stock copy. To get one, run
   `openspec init --tools <tool> <tmpdir>` in an empty temporary git repo. List
   every customisation that is **not** diagram-related.
3. **ASK** the user whether those non-diagram customisations should be kept. If yes,
   re-apply them by hand after Step 5.
4. Restore stock skills: `openspec update --force "$ROOT"`. If the preflight
   reported workflows that `update` would delete, handle that first, as in Step 1.

**Verify:**

```bash
openspec list            # runs without error
python3 "$KIT"/files/scripts/vsdd/openspec_preflight.py --root "$ROOT" --tools <TOOLS>
```

The preflight must show no `Tools to add`. It must show every workflow the project
had before this step, unless the user agreed to lose some.

---

## Step 2 — Copy the kit files

Copy each file below. **Existing files:** follow the "If it exists" column.

| From `KIT/files/` | To `ROOT/` | If it exists |
|---|---|---|
| `openspec/schemas/visual-driven/` (whole dir) | `openspec/schemas/visual-driven/` | Overwrite. It belongs to the kit |
| `docs/MERMAID_RULES.md` | `docs/MERMAID_RULES.md` | Diff first. Keep any project-specific rules the user added, and merge in kit additions |
| `docs/VSDD.md` | `docs/VSDD.md` | Overwrite. It belongs to the kit |
| `scripts/vsdd/validate_mermaid.py` | `scripts/vsdd/validate_mermaid.py` | Overwrite |
| `scripts/vsdd/install_overlay.py` | `scripts/vsdd/install_overlay.py` | Overwrite |
| `scripts/vsdd/merge_diagrams.py` | `scripts/vsdd/merge_diagrams.py` | Overwrite |
| `scripts/vsdd/openspec_preflight.py` | `scripts/vsdd/openspec_preflight.py` | Overwrite |

```bash
mkdir -p "$ROOT"/openspec/schemas "$ROOT"/docs "$ROOT"/scripts/vsdd
cp -R "$KIT"/files/openspec/schemas/visual-driven "$ROOT"/openspec/schemas/
cp "$KIT"/files/docs/VSDD.md "$ROOT"/docs/
cp "$KIT"/files/scripts/vsdd/*.py "$ROOT"/scripts/vsdd/
[ -e "$ROOT"/docs/MERMAID_RULES.md ] || cp "$KIT"/files/docs/MERMAID_RULES.md "$ROOT"/docs/
```

If the project keeps docs somewhere other than `docs/`, **ASK** before relocating.
The schema, the overlay and the snippets all refer to `docs/VSDD.md` and
`docs/MERMAID_RULES.md`, so every one of those references would need changing.

**Verify:**

```bash
cd "$ROOT" && openspec schema validate visual-driven    # "Schema 'visual-driven' is valid"
openspec schemas | grep visual-driven
```

---

## Step 3 — Configure `openspec/config.yaml`

The OpenSpec CLI reads **`context`** (injected into every artifact) and **`rules`**
(per-artifact constraints). Newer versions (e.g. 1.13) also read **`operations`**
(advisory guidance for the apply and archive workflows). The kit uses `operations`
as a backstop that re-states the diagram steps if the skill overlay is ever wiped.
**Any other key, such as `prompts:`, is silently ignored.**

- **No `config.yaml`, or only the stock template:** newer `openspec init` creates
  a template that is just `schema: spec-driven` plus commented-out examples. Treat
  that as "no config". Replace it with `KIT/files/openspec/config.yaml.example`, then
  fill in `context:` from the project itself:
  read the README, the package manifests (`package.json`, `pubspec.yaml`,
  `pyproject.toml`, `go.mod`, ...) and the top-level directory layout. Keep it to
  4–8 lines of facts agents need. Don't invent conventions you can't see in the
  code.
- **`config.yaml` exists:**
  1. Set `schema: visual-driven`, **unless the preflight flagged a custom schema.**
     In that case, **ASK**:
     - **(a)** switch to `visual-driven`, losing the custom artifacts from new
       changes; or
     - **(b)** keep their schema, and add VSDD to it by copying the `diagrams`
       artifact from `openspec/schemas/visual-driven/schema.yaml`: its template and
       instruction, `requires: [proposal]`, and making their next artifact require
       `diagrams`. Then check it with `openspec schema validate <their schema>`; or
     - **(c)** stop.

     Never replace a custom schema without asking.
  2. If it has a `prompts:` key, it has been ignored. **ASK** whether to rename it to
     `rules:`, and show the user its contents first: enabling stale rules can do more
     harm than having none.
  3. Add the `rules.diagrams` list from the example, if it isn't already there.
  4. Add the `rules.tasks` VSDD line.
  5. Add the `operations.apply` and `operations.archive` VSDD guidance entries from the
     example. Keep any guidance entries already there.
  6. Add `context:` if it's missing, filled in as above.

**Verify** with a throwaway change (it is removed in Step 8):

```bash
openspec new change vsdd-smoke-test
openspec instructions diagrams --change vsdd-smoke-test | grep -E "<project_context>|<rules>|MERMAID_RULES"
```

All three patterns must appear. If `<rules>` is missing, the YAML key is wrong or
the indentation is broken.

On newer OpenSpec (if `openspec instructions --help` mentions `archive`), also check
the backstop:

```bash
openspec instructions archive --change vsdd-smoke-test --json | grep -c "VSDD"    # >= 1
```

---

## Step 4 — Agent instruction files

1. **`AGENTS.md`:**
   - If `ROOT/AGENTS.md` exists and already has a
     `## OpenSpec & Visual Spec-Driven Development` section: replace that section
     with `KIT/files/agents/AGENTS.vsdd.md`.
   - If it exists without one: append the snippet at the end.
   - If there is no `AGENTS.md`: create one from the snippet, preceded by a one-line
     project description.
   - If `AGENTS.md` contains older, longer diagram rules (for example an
     "OpenSpec & Diagram Standards" section): **ASK** before removing them. The
     snippet plus `docs/VSDD.md` replaces them.
2. **Claude Code** (`claude` in `TOOLS`): Claude Code reads `CLAUDE.md`, not
   `AGENTS.md`. If there is no `ROOT/CLAUDE.md`, copy
   `KIT/files/agents/CLAUDE.md.example` to `ROOT/CLAUDE.md`. It contains a single
   line that imports `AGENTS.md`. If `CLAUDE.md` exists, check whether it already
   contains `@AGENTS.md`, and add that line at the top if not.
3. **Other tools:** Codex, OpenCode, Cursor, Qwen Code and most others read
   `AGENTS.md` directly. Nothing more to do.

**Verify:** `grep -n "docs/VSDD.md" "$ROOT"/AGENTS.md` prints a line. If Claude Code
is in `TOOLS`, `grep -n "@AGENTS.md" "$ROOT"/CLAUDE.md` prints a line too.

---

## Step 5 — Apply the skill and command overlay

```bash
cd "$ROOT" && python3 scripts/vsdd/install_overlay.py --dry-run
python3 scripts/vsdd/install_overlay.py
```

What it does, for every tool folder (`.claude`, `.opencode`, `.qwen`, ...):

- Inserts marked VSDD blocks into whichever of these skills exist: `openspec-propose`,
  `-continue-change`, `-ff-change` (diagram generation), `-update-change` (rules for
  revising `diagrams.md`), `-apply-change` (trace the After state against the code),
  `-verify-change` (Diagram Fidelity), `-archive-change` (merge into the Source of
  Truth), and `-bulk-archive-change`. Which skills exist depends on the OpenSpec
  workflow profile (`openspec config list`).
- Rewrites the matching `/opsx` command files as thin wrappers that load the skill.
  Stock commands contain their **own copy** of the skill text, so without this step
  the commands would bypass the VSDD steps.

**If it prints `anchor not found`:** your OpenSpec version changed the stock skill
text. Open `scripts/vsdd/install_overlay.py` and find the `PATCHES` table and the
text constants above it. For each missing patch id, insert the block by hand at the
equivalent place in that skill. Keep the `<!-- vsdd:<id> -->` marker line so that
later runs detect it. Then re-run the script until it reports no problems.

If you did Step 1b and the user wanted to keep non-diagram customisations, re-apply
them now.

**Verify:**

```bash
python3 scripts/vsdd/install_overlay.py --check      # ends with "VSDD overlay OK."
```

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

Use the `vsdd-smoke-test` change created in Step 3.

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
- Agent files: <AGENTS.md created/updated>, <CLAUDE.md created/updated/n.a.>
- Overlay: <N> skills patched, <M> commands wrapped (check: OK)
- Source of Truth: <files and stable section names>
- CI: <added .github/workflows/vsdd.yml | skipped | instructions given>
- Smoke test: passed, removed
- In-flight changes: <list from the preflight, or "none">. They keep their original
  schema, so they have no diagrams.md and their archive does no diagram merge
- Decisions I made: <list>
- Needs your attention: <anything skipped, failed, or deferred>

Next: try `/opsx:propose <small change with a visual impact>` and review its diagrams.md.
```

Then suggest the user commit everything as a single commit, for example
`chore: install visual spec-driven development (VSDD)`. Do not commit unless asked.

---

## Maintenance (tell the user)

| Event | Action |
|---|---|
| About to run `openspec update` | Run `python3 scripts/vsdd/openspec_preflight.py` first. If it would delete workflows, use `--safe-update` instead, or add them to your profile |
| `openspec update` or `openspec init` was run | `python3 scripts/vsdd/install_overlay.py`. CI's `--check` catches a forgotten run |
| OpenSpec upgraded to a new minor or major version | Run the overlay with `--dry-run` first. On `anchor not found`, see Step 5 |
| A new AI tool is added | `openspec update` (after adding the tool via `openspec init --tools`), then the overlay |
| Kit upgraded | Re-run Steps 2, 3 (new `rules`/`operations` entries, e.g. the Placement rule) and 4. Changes still in flight need a `## Placement` table added before they validate. For Step 5, first restore stock skills with `openspec update`, then run the overlay. Blocks already marked `vsdd:` are skipped, so their text only refreshes from stock |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `openspec instructions diagrams` shows no `<rules>` | `config.yaml` uses `prompts:` or has a YAML indentation error | Use `rules:`. Check with `python3 -c "import yaml;print(yaml.safe_load(open('openspec/config.yaml')))"` |
| Change created without `diagrams.md` | Change made with a different schema | `cat openspec/changes/<name>/.openspec.yaml` should show `schema: visual-driven`. Check `schema:` in `config.yaml` |
| Archive summary has no `Diagrams:` line | Stock command or skill used (overlay wiped) | `install_overlay.py --check`, then re-apply |
| Archive reports "Diagrams: no-op" on a YES gate | After State uses `##` instead of `### <Stable Name>`, or there's no `## Placement` table | Fix the headings or add the table, then merge by hand. The validator flags both |
| Validator: "Before ... is not a verbatim copy" | The Before section was edited, or the Source of Truth changed after the change was proposed | Re-copy the section from the file the Placement row names. If the Source of Truth really changed, re-check that the After State still applies |
| Validator: "... has no Placement row" | A Before or After section isn't listed in `## Placement` | Add a row (update / add / move from / remove), or delete the stray section |
| Rendered sequence diagram shows `"Name"` with quotes | Quoted participant alias | Remove the quotes (`participant A as Name`) |
| Skills or `/opsx` commands (continue, ff, …) disappeared after `openspec update` | They weren't in the global OpenSpec profile | Add them with `openspec config profile`, then run `openspec update` again. Next time, run `openspec_preflight.py` first |
| A tool's skills were never created | `openspec update` only refreshes tools that are already set up | `openspec init --tools <tool> .` (safe on an existing project) |
| `openspec archive` used directly | The CLI has no diagram merge | Run `python3 scripts/vsdd/merge_diagrams.py openspec/changes/archive/<dated-name>` (see `docs/VSDD.md` §4) |
| `merge_diagrams.py` refuses: "not a verbatim copy" | The Source of Truth changed after the change was proposed (e.g. another change archived first) | Re-copy the Before sections from the current Source of Truth, re-check that the After State still makes sense, then merge again |

## Uninstall

1. Set `schema: spec-driven` in `openspec/config.yaml`, and delete the `rules.diagrams` entries.
2. `openspec update --force` to restore stock skills and commands.
3. Delete `openspec/schemas/visual-driven/`, `docs/VSDD.md`, `scripts/vsdd/`,
   `.github/workflows/vsdd.yml`, and the VSDD section of `AGENTS.md`.
4. Keep `openspec/specs/**/diagrams.md` and the archived changes. They are still
   useful documentation.
