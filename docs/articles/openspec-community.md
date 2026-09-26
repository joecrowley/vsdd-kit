# OpenSpec community posts (drafts)

OpenSpec has four places for this, each with its own rules. Post in this order:

1. **GitHub Discussions** first: the introduction, and questions for the maintainers.
2. **Community Schemas table**, a row in `docs/customization.md`. Its note says: open
   an issue with a link to your repository, or submit a PR adding a row.
3. **Community Showcase**, one line in `docs/community.md`, by PR. Its rules: say
   what people can use, no promotional claims, no tracking links.
4. **Discord**: a short pointer to the discussion.

OpenSpec's CONTRIBUTING asks for a discussion or issue before a PR, and links from the
PR back to it. So open the discussion first, and link it from both PRs.

---

## 1. GitHub Discussion

Category: "Show and tell" if there is one, otherwise "General" or "Ideas".
Discussions: https://github.com/Fission-AI/OpenSpec/discussions

**Title:**

```text
VSDD: a community schema that adds Before/After Mermaid diagrams to each change
```

**Body:**

```markdown
Hi all. I've built a community schema and toolkit on top of OpenSpec, and I'd like feedback, and to ask the maintainers a few questions about the parts of OpenSpec it depends on.

**What it is.** VSDD (Visual Spec-Driven Development) gives architecture diagrams the same delta treatment OpenSpec gives specs. The `visual-driven` schema adds a `diagrams` artifact: `proposal → diagrams → specs → design → tasks`. Each change records a gate (`Diagram needed?`), a Placement table, a verbatim Before State copied from a Source of Truth (`openspec/specs/**/diagrams.md`), and an After State. During apply, the agent traces the After State against the code, and records a Deviations note where the build differs from the plan. On archive, a deterministic script merges the After State into the Source of Truth, section by section.

Repo: https://github.com/joecrowley/vsdd-kit
Worked example (an unedited change on a small Flutter app, with the code and the Source of Truth before and after): https://github.com/joecrowley/vsdd-kit/tree/main/examples/book-notes

**How it uses OpenSpec.** It tries to stay on supported surfaces:
- a custom schema in `openspec/schemas/visual-driven/`
- `context`, `rules` and `operations` in `config.yaml`. `operations.apply` and `operations.archive` repeat the key steps as a backstop
- an overlay that inserts marked blocks into the `openspec-*` skills generated for each tool, and turns the `/opsx` commands into thin wrappers that load those skills. It re-applies after `openspec update`, and has a `--check` for CI

It installs for all 40 tools `openspec init --tools` supports. I've used it end to end with Claude Code. OpenCode and Qwen Code run in its smoke test, and the rest are checked structurally. The smoke test runs weekly against the latest OpenSpec.

**Questions for the maintainers:**

1. **Stable anchors.** The overlay finds its insertion points by matching lines in the generated skills: `**Artifact Creation Guidelines**`, `**Guardrails**`, `N. **Perform the archive**`, `N. **On completion or pause**`, `N. **Generate Verification Report**`, `**Verification Heuristics**` and `- **Coherence**:`. Are these reasonably stable? Or is there a better extension point I should use, now or planned? I'd rather not depend on skill wording.
2. **An archive hook.** `openspec archive` from the CLI doesn't run the diagram merge, so people who archive without the skill skip it. `operations.archive` guidance helps, but it's advisory. Is a hook that runs a command before or after archive something you'd consider?
3. **Workflows removed by `openspec update`.** `update` removes skills for workflows missing from the global profile. The kit ships a preflight that predicts this and a `--safe-update` that keeps them. Is that the intended behaviour, or would a flag to keep installed workflows fit in core?

If the schema looks useful, I'd like to add it to the Community Schemas table and the Community Showcase. I'll link the PRs here.

Feedback welcome, especially where it gets in the way.
```

---

## 2. Community Schemas row

File: `docs/customization.md`, table under "Community Schemas". Keep it to one row,
in the style of the others. The link goes to the schema folder, and the description
says the kit's installer is needed, because copying the schema alone doesn't give the
merge.

**PR title:** `docs: add visual-driven (VSDD) to community schemas`

**Row:**

```markdown
| `visual-driven` | @joecrowley | [joecrowley/vsdd-kit](https://github.com/joecrowley/vsdd-kit/tree/main/files/openspec/schemas/visual-driven) | Adds a `diagrams` artifact after the proposal: Before/After Mermaid diagrams of the change, placed per capability and copied verbatim from a diagram Source of Truth (`specs/**/diagrams.md`). During apply, the After State is traced against the code, with a Deviations note where the build differs. On archive, a deterministic script merges it back into the Source of Truth. Install with the kit's installer (`uvx --from git+https://github.com/joecrowley/vsdd-kit vsdd-kit guide`), which also adds the skill overlay and validator. |
```

**PR description:**

```markdown
Adds the `visual-driven` schema from VSDD to the Community Schemas table.

Discussion: <link to the discussion>

The schema lives in https://github.com/joecrowley/vsdd-kit, with its own releases (currently v0.3.1). The row says that the kit's installer is needed, because the diagram merge on archive and the skill steps come from the kit, not from the schema alone.
```

---

## 3. Community Showcase line

File: `docs/community.md`, under "Projects and resources".

**PR title:** `docs: add VSDD kit to the community showcase`

**Line:**

```markdown
- **[VSDD kit](https://github.com/joecrowley/vsdd-kit)**: A schema, skill overlay and scripts that add Before/After Mermaid diagrams to each OpenSpec change, check them against the code during apply, and merge them into a diagram Source of Truth on archive.
```

**PR description:**

```markdown
Adds the VSDD kit to the showcase. It's open source (MIT), with no accounts or paid features.

Discussion: <link to the discussion>
```

---

## 4. Discord

Channel: whichever one is for sharing projects, or #general. Post after the discussion
is up.

```text
Hi all. I've built a community schema for OpenSpec that adds Before/After Mermaid diagrams to each change, checks them against the code during apply, and merges them into a diagram Source of Truth on archive. There's a worked example on a small Flutter app in the repo. Feedback, and a couple of questions for the maintainers, are in this discussion: <link to the discussion>
```
