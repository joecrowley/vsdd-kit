## OpenSpec & Visual Spec-Driven Development

- Changes use the OpenSpec `visual-driven` schema: `proposal → diagrams → specs → design → tasks`.
  Use the `/opsx` commands or `openspec-*` skills rather than editing change folders ad hoc.
- Current architecture diagrams: `openspec/specs/<capability>/diagrams.md`
  (cross-cutting: `openspec/specs/architecture/diagrams.md`). Read the relevant one before
  proposing structural changes.

| When you are... | Read first |
|---|---|
| Writing or editing a change's `diagrams.md`, or archiving a change | `docs/VSDD.md` |
| Drawing or editing any Mermaid diagram | `docs/MERMAID_RULES.md` |
| Designing a change, or fixing a bug that could recur elsewhere | `openspec/specs/architecture/decisions.md` (rules learned from past changes) |

- After editing any diagram, run `python3 scripts/vsdd/validate_mermaid.py`.
- After `openspec init` or `openspec update`, run `python3 scripts/vsdd/install_overlay.py`,
  because those commands overwrite the VSDD skill additions.
