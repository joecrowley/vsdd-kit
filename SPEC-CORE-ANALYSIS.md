# spec-core → vsdd-kit: Borrowing Analysis

*Analysis of `/Volumes/LacieStore/flutter/spec-core` against vsdd-kit. Options only — no changes made. Snapshot date: 2026-10-03.*

## What spec-core actually is

Not a kit — a **deployment** of OpenSpec for one org (Comcast), in a specs-only repo (no code). It has three layers:

1. **Two custom schemas** — `spec-core/openspec/schemas/feature/schema.yaml` and `.../capability/schema.yaml`. Both deliberately **omit `tasks.md`** (docs-only, no implementation phase) and use the schema-level `notes:` key to tell the stock OpenSpec skills how to adapt ("Apply: not applicable", "Verify: skip task checks"). Default schema is `feature`; change names are prefixed `feature-` / `capability-`.
2. **Wombat** — a much larger bespoke lifecycle system (~42 skills in `.agents/skills/`, doctrine in `.wombat/prompts/`, strict **markdown contracts** that validate spec section grammars, `.lock` / `.promoted` marker files, semver'd capability spec files with `contracts/` (OpenAPI/JSON-schema/example), trace-audit promotion gates, Figma/Confluence/Smartsheet integrations). Org-specific and not portable. `.wombat/.promoted` pins a wombat-skills git SHA.
3. **`migrate-openspec-skills.sh`** — dedupes the `openspec-*` skills that `openspec init` regenerates redundantly into `.devin/`, `.github/`, `.windsurf/` into a canonical `.agents/skills/` (first-occurrence-wins, with an `.openspec-target` marker file).

Notably, spec-core **does** use Mermaid heavily (~99 matches) — but only inside Wombat's `e2e-arch` / `init-arch` artifacts, with a **non-overlap + revision-drift** discipline (§10 "Architecture Drift" with Revision-Delta rows in `.wombat/templates/e2e-arch-template.md:150`) instead of vsdd-kit's Before/After pairing. There are no AGENTS.md/CLAUDE.md, no CI workflows (`.github/` holds only CODEOWNERS), and OpenSpec **Stores (beta)** is registered via `.openspec-store/store.yaml`.

## Options for vsdd-kit, best-fit first

### A. Borrow the `notes:` adaptation pattern (small, high value)

vsdd-kit's own weak point is that `openspec update` can wipe the overlay; the current backstops are `operations:` config keys and `schema.yaml` `apply.instruction`. spec-core shows a third, cheaper channel not in use: a per-skill adaptation list in `notes:` inside `schema.yaml` (verified in `spec-core/openspec/schemas/capability/schema.yaml:9`). It ships *with* the schema, needs no overlay, no CLI support for `operations:`, and no script.

- **Why:** makes the two most load-bearing rules (check diagram vs code; merge on archive) survive an overlay wipe through a path not dependent on OpenSpec version.
- **Cost:** ~20 lines in `files/openspec/schemas/visual-driven/schema.yaml` plus a smoke-test assertion.

### B. Support docs-only schemas / "diagram-vs-diagram" mode (design question, medium)

spec-core proves a real audience runs OpenSpec with **no code in the repo** and no `tasks.md` / apply step. The vsdd-kit pipeline assumes "check the After state against the code." In a spec-core-style project the gate and merge still work, but step 3 (fidelity vs code) has no referent — and their `notes:` say "Apply: not applicable", which collides with the injected VSDD apply step.

- **Why:** either an explicit docs-only mode (verify Before verbatim + Placement, skip code tracing, record Deviations against the design instead), or a documented limitation. Deciding now is cheaper than discovering it when a specs-only user files an issue.
- **Cost:** a mode flag, validator tolerance for missing `tasks.md`, a runbook note.

### C. Strengthen structure validation with "markdown contracts" (medium)

spec-core's `.wombat/templates/*-markdown-contract.md` files are machine-checkable section grammars — exact H2 sets, ordering, anchor IDs, "fail loud". `validate_mermaid.py` already checks Placement tables and verbatim Before, but informally.

- **Why:** the Placement table + Before/After + Deviations format is exactly the kind of grammar a contract file formalizes — legible validator errors for agents, and a spec for the broken-case tests already in `tests/smoke_test.sh`.
- **Cost:** one contract doc + refactoring validator checks around it. Only worth it if more structure rules are planned.

### D. Skill-dedup awareness in `openspec_preflight.py` (small)

spec-core's `migrate-openspec-skills.sh` exists because `openspec init` writes duplicate skills into several vendor dirs; they consolidate into `.agents/skills/`. The preflight already predicts deletions and the overlay patches per tool.

- **Why:** when a user works in multiple tools (40 verified), the same duplication exists and the overlay patches each copy — `--check` can pass while copies drift. Preflight could *detect and report* duplicate skill copies. Keep it to detection; consolidating would fight OpenSpec's own regeneration.
- **Cost:** one preflight check.

### E. Adoption-governance borrow (trivial)

spec-core's `.github/CODEOWNERS` covers only `openspec/schemas/` and `openspec/config.yaml` — the two paths that break everything if changed casually. Mirror that in the CI template (`files/ci/github/`) docs, or protect schema paths in vsdd-kit itself.

## Explicitly do **not** bring in

- **Wombat wholesale** — 42 skills, Comcast-specific catalogs (platforms, workstreams, products), Confluence/Smartsheet integrations. Its lock/promote/semver machinery duplicates what OpenSpec's archive already does, at much higher ceremony.
- **Their diagram discipline as-is** — revision-drift tables and non-overlap rules solve a different problem (many teams authoring *canonical* arch docs); Before/After + Placement + merge already covers drift for code-bearing repos. The one idea worth remembering is the **non-overlap rule** (init-arch draws shared structure; e2e-arch must cite, not redraw) — vsdd-kit enforces the same thing structurally via stable names in one Source-of-Truth file.
- **Stores (`.openspec-store/`)** — OpenSpec beta; nothing to adopt yet, but add as a watch-item to the OpenSpec-upgrade checklist since it changes how skills are generated.

## Recommendation

Do **A** now (cheap, closes a known fragility). Decide **B** deliberately — it is a scope question. Treat **C–E** as backlog.

## Resume notes

- Nothing has been changed in either repo; this file is the only artifact (untracked, repo root — move or delete as preferred).
- Key spec-core files if revisiting: `openspec/schemas/{feature,capability}/schema.yaml` (notes: pattern), `migrate-openspec-skills.sh`, `.wombat/templates/e2e-arch-template.md` (§10 drift), `.wombat/templates/*-markdown-contract.md`, `openspec/config.yaml`, `README.md` (upgrade ritual), `.openspec-store/store.yaml`.
- Key vsdd-kit files touched by the options: `files/openspec/schemas/visual-driven/schema.yaml` (A), `files/scripts/vsdd/validate_mermaid.py` (B/C), `files/scripts/vsdd/openspec_preflight.py` (D), `files/ci/github/vsdd.yml` (E).
