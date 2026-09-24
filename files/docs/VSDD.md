# Visual Spec-Driven Development (VSDD) Standards

Diagrams are code. They follow the same delta discipline as OpenSpec text specs:
the current state lives in a Source of Truth, a change proposes a Before/After
delta, and archiving merges the After state back.

Read this file when you create or edit a change's `diagrams.md`, or when you archive
a change. Read `docs/MERMAID_RULES.md` before drawing any diagram.

## 1. Source of Truth

- Capability-owned diagrams: `openspec/specs/<capability>/diagrams.md`, next to the
  capability's `spec.md`.
- Cross-cutting diagrams (package/module hierarchy, end-to-end data flow, global
  state, system topology): `openspec/specs/architecture/diagrams.md`.
- Each diagram is one `## <Stable Name>` section: a one-line description, then a
  ` ```mermaid ` block. The stable name is the merge key. Do not rename it casually.

## 2. The change artifact: `diagrams.md`

Pipeline (schema `visual-driven`): `proposal → diagrams → specs → design → tasks`.

1. **Gate.** Start with `## Diagram needed?`. Answer YES if the change affects
   navigation/routing, a state machine, data flow, infrastructure topology or a data
   schema. Otherwise write `NO - <one-line reason>` and stop.
2. **Before State** (YES only). Copy **verbatim** only the affected sections from the
   Source of Truth, as `### <Stable Name>`. If no Source of Truth exists yet, write
   `No Source of Truth exists yet - this is a new diagram.`
3. **After State.** Use the **same** stable names for modified diagrams, and a
   **new** stable name for a new diagram.

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

For each `### <Stable Name>` under `## After State`:

| Situation | Action |
|---|---|
| Name exists in the Source of Truth | Replace that `## <Stable Name>` section |
| Name is new | Append a `## <Stable Name>` section |
| Source of Truth file missing | Create it with a `# <Domain> Diagrams` header |
| Gate is NO | No-op |

Never touch sections the After State doesn't name, and never merge
`## Before State` or `## Deviations`. The merge cannot delete a diagram. To remove
one, delete its section from the Source of Truth as a task in the change, and say so
in the proposal.

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

Run it after editing any `diagrams.md`. CI runs it on every push.
