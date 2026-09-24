# Visual Spec-Driven Development (VSDD) Standards

Diagrams are code. They follow the same delta discipline as OpenSpec text specs:
the current state lives in a Source of Truth, a change proposes a Before/After
delta, and archiving merges the After state back.

Read this file when you create or edit a change's `diagrams.md`, when you design a
change (§6), or when you archive a change. Read `docs/MERMAID_RULES.md` before drawing any diagram.

## 1. Source of Truth

- Capability-owned diagrams: `openspec/specs/<capability>/diagrams.md`, next to the
  capability's `spec.md`.
- Cross-cutting diagrams (package/module hierarchy, end-to-end data flow, global
  state, system topology): `openspec/specs/architecture/diagrams.md`.
- Each diagram is one `## <Stable Name>` section: a one-line description, then a
  ` ```mermaid ` block. The stable name is the merge key. Do not rename it casually.
- **Ownership:** a diagram belongs to the capability whose behaviour it shows. It
  goes in the architecture file only when it spans capabilities (the module
  hierarchy, a state holder shared by several features, system topology). When a
  change **creates a capability**, its new flows go in that capability's file,
  and any existing architecture diagram that now shows only that capability's
  behaviour moves there (§2).
- Putting a diagram **into** the architecture file (`add`, or `move from` another
  file) needs a reason in the Placement table's `Why here` column, saying which
  capabilities it spans. The validator enforces this, and warns when the change
  creates a capability but still adds to the architecture file.

## 2. The change artifact: `diagrams.md`

Pipeline (schema `visual-driven`): `proposal → diagrams → specs → design → tasks`.

1. **Gate.** Start with `## Diagram needed?`. Answer YES if the change affects
   navigation/routing, a state machine, data flow, infrastructure topology or a data
   schema. Otherwise write `NO - <one-line reason>` and stop.
2. **Placement** (YES only). Add a `## Placement` table with one row per diagram
   the change touches:

   ```markdown
   | Stable name | Source of Truth file | Action | Why here |
   |---|---|---|---|
   | Status Update Flow | specs/reading-status-update/diagrams.md | move from specs/architecture/diagrams.md | |
   | ReadingListState Machine | specs/architecture/diagrams.md | update | |
   | Sync Topology | specs/architecture/diagrams.md | add | Shared by reading-list and book-notes |
   ```

   Paths are relative to `openspec/`. `Why here` is required only for rows that
   `add` or `move` a diagram into `specs/architecture/diagrams.md`. Leave it empty,
   or leave the column out, otherwise.

   | Action | Before State | After State | Archive merge |
   |---|---|---|---|
   | `update` | verbatim copy from the file | same stable name | replace the section |
   | `add` | none | new stable name | append (the file is created if it doesn't exist) |
   | `move from <old file>` | verbatim copy from the **old** file | same stable name | delete from the old file, then add to this file |
   | `remove` | verbatim copy (kept as history) | **none** | delete the section, and the file if no diagrams are left |

3. **Before State.** Copy the `## <Stable Name>` section for every update, move and
   remove row **verbatim** from the file the row names, as `### <Stable Name>`.
   Nothing else.
4. **After State.** Write one `### <Stable Name>` for every update, add and move row.
   Keep existing stable names unchanged. A removed diagram has no After section.

The validator checks that the Placement table matches the Before and After sections,
that each Before copy is verbatim, and that architecture-file additions have a
`Why here`. It prints a **warning** (which does not fail the run) when the change
creates a capability but still adds or moves a diagram into the architecture file:
review that row.

## 3. Deviations

The After State must describe what was actually **built**, because it becomes the
canonical diagram. When implementation differs from the proposal:

- Update the After State to match the code.
- Add a top-level `## Deviations` section (a sibling of Before/After, and never
  merged) with **Proposed / Built / Why** for each difference.
- Do not keep a parallel "expected" diagram.

Code that exists but has no production call site yet can stay in the diagram as a
dashed edge, with a Deviations entry explaining it.

## 4. Archive merge

```bash
python3 scripts/vsdd/merge_diagrams.py openspec/changes/<name> --dry-run   # show the plan
python3 scripts/vsdd/merge_diagrams.py openspec/changes/<name>             # apply it
```

The script is the reference implementation of the rules below:
- It validates the change first. If any Before copy is no longer verbatim (because
  the Source of Truth changed after the change was proposed), it writes nothing and
  exits 1. Resolve that conflict before archiving.
- Running it again after a merge reports "already merged".

Without the script, apply the rules by hand. If the gate is NO, the merge does
nothing. Otherwise, apply each `## Placement` row, **removals and moves out first**,
then updates and additions:

| Action | Merge |
|---|---|
| `remove` | Delete `## <Stable Name>` from the file. If the file has no `##` diagram sections left, delete the file |
| `move from <old>` | Delete `## <Stable Name>` from `<old>` (and `<old>` itself if no diagrams are left), then add the After section to the target file: append it, or replace it if the name is already there |
| `update` | Replace `## <Stable Name>` in the file with the After section |
| `add` | Append the After section. If the file doesn't exist, create it with a `# <Domain> Diagrams` header |

Rules for every action:
- Never touch a section that has no Placement row.
- Never merge `## Before State`, `## Placement` or `## Deviations`.
- Afterwards, run the validator on the changed Source of Truth files.

The merge is done by the `openspec-archive-change` skill, not by the
`openspec archive` CLI. Always archive through the skill or the `/opsx` archive
command. On newer OpenSpec, the same instruction also reaches the stock archive skill
as `operations.archive.guidance` from `openspec/config.yaml`, as a backstop.

Paths here assume the default planning root `openspec/`. If your OpenSpec setup
uses another root or a registered store, the same layout applies under that root.

## 5. Validation

```bash
python3 scripts/vsdd/validate_mermaid.py            # lint + structure
python3 scripts/vsdd/validate_mermaid.py --render   # also parse with mermaid-cli
```

For an active change, the validator also checks the `## Placement` table against the
Before and After sections, that each Before copy is still verbatim, and that
architecture-file additions give a `Why here`. Ownership warnings are printed as
`warning:` lines and don't change the exit code.

Run it after editing any `diagrams.md`. CI runs it on every push.

## 6. Architecture decisions

Specs record what each capability does. They don't record the general lessons behind
a fix, such as "after a write, refresh without a loading state". Without that, the
next change in another capability repeats the mistake. The decisions log holds those
lessons:

- **File:** `openspec/specs/architecture/decisions.md`. Each rule is one
  `## <Stable Name>` section with **Rule:**, **Why:**, **Applies to:** and
  **Source:** (the archived change it came from). The validator checks that Rule,
  Why and Source are present.
- **Design:** before writing `design.md` (or `tasks.md`, when there is no design),
  read the log and follow every rule that applies. To break one deliberately, write
  `Overrides: <Stable Name> - <why>` under Decisions in `design.md`.
- **Archive:** if the change fixed a bug caused by a pattern that could recur, or set
  a convention, the agent drafts an entry and **asks** before adding it. If the
  design overrode a rule, it asks whether to update or retire that entry. The archive
  summary has a **Decisions** line.
- **Pitfalls in context:** copy the one to three costliest rules, one line each, into
  `context:` in `openspec/config.yaml`. That text reaches every artifact, even when
  an agent skips the file.
- **Upkeep:** keep entries short, and delete a rule when the code no longer has the
  problem it guards against. A stale rule misleads as much as a missing one.

Whether a design follows a rule is a judgement call, so there is no mechanical check.
Review `design.md` for the rules that apply, and look for `Overrides:` lines.
