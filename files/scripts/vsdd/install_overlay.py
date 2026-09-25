#!/usr/bin/env python3
"""Apply the VSDD overlay to OpenSpec-generated skills and /opsx commands.

`openspec init` / `openspec update` (re)generate stock skills and commands for
each configured AI tool (.claude/, .opencode/, .qwen/, .cursor/, ...). Stock
files know nothing about diagrams, and `openspec update` overwrites any edits.
This script re-applies the VSDD additions:

  skills   - inserts diagram and decisions-log steps into openspec-{propose,continue-change,
             ff-change,update-change,apply-change,verify-change,
             archive-change,bulk-archive-change} at anchor lines. Idempotent: each insertion
             carries a `<!-- vsdd:<id> -->` marker and is skipped if present. A guard line
             at the top of each skill makes the VSDD steps no-ops in projects without
             docs/VSDD.md, so a skill folder shared by several projects can be patched.
  commands - rewrites the matching /opsx command files as thin wrappers that
             load the (patched) skill, so commands and skills cannot diverge.

Usage (from the project root):
  python3 scripts/vsdd/install_overlay.py            # apply
  python3 scripts/vsdd/install_overlay.py --dry-run  # show what would change
  python3 scripts/vsdd/install_overlay.py --check    # exit 1 if overlay missing
                                                     # (use in CI after updates)

Exit codes: 0 ok, 1 overlay missing (--check) or an anchor was not found,
2 no OpenSpec skills found.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", ".dart_tool", "build", ".venv", "venv"}

GEN_DIAGRAMS = """\
<!-- vsdd:gen-diagrams -->
**VSDD - diagrams.md** (schema `visual-driven`, DAG proposal -> diagrams -> specs -> design -> tasks):
- Decide the `## Diagram needed?` gate first. A visual concern is navigation/routing,
  a state machine, data flow, infrastructure topology, or a data schema.
  - NO: write `NO - <one-line reason>` and stop. No other sections.
  - YES: read `docs/VSDD.md` sections 1-2, then add a `## Placement` table
    (Stable name | Source of Truth file | Action | Why here) with one row per diagram
    touched. Action is update, add, `move from <old file>` or remove. Diagrams belong
    to the capability whose behaviour they show: if the change creates a capability,
    its new flows go in `specs/<capability>/diagrams.md`. A row that adds or moves a
    diagram into `specs/architecture/diagrams.md` must name, in `Why here`, the
    capabilities it spans.
  - Copy the Before sections VERBATIM from the files the rows name, then write the
    After sections under the SAME stable names. Removed diagrams have no After.
- Read `docs/MERMAID_RULES.md` before drafting any diagram. Then run
  `python3 scripts/vsdd/validate_mermaid.py`: it checks the Placement table and
  that the Before copies are verbatim.
"""

GUARD = """\
> **VSDD:** the steps marked `vsdd:` or "(VSDD)" in this skill apply only when the OpenSpec project you are working in (the folder that holds its `openspec/` directory, which may be a package inside a monorepo) uses Visual Spec-Driven Development: its `openspec/config.yaml` uses the `visual-driven` schema or has rules mentioning VSDD, or the project has `docs/VSDD.md`. Otherwise skip them and follow the stock steps. Paths in those steps (`docs/VSDD.md`, `docs/MERMAID_RULES.md`, `scripts/vsdd/`) are relative to the project, unless its config `context:` names a VSDD tooling folder: then they are relative to that folder, and every script needs `--root <the OpenSpec project folder>`. <!-- vsdd:guard -->"""
FRONTMATTER_END = "<frontmatter-end>"  # anchor: the line after the closing `---` of the YAML front matter

GEN_DECISIONS = """\
- Before writing design.md (or tasks.md, when the change has no design), read
  `openspec/specs/architecture/decisions.md` if it exists and follow every rule
  that applies. To break one deliberately, write `Overrides: <Stable Name> - <why>`
  under Decisions in design.md. <!-- vsdd:gen-decisions -->
"""

PROPOSE_LIST = """\
- diagrams.md (visual-driven schema: Before/After diagram delta, after the proposal) <!-- vsdd:propose-list -->"""

APPLY_TRACE = """\
<!-- vsdd:apply-trace -->
6a. **Verify diagrams match the final code (VSDD)**

   If the change has a `diagrams.md` whose `## Diagram needed?` gate is YES,
   re-read it before declaring the work complete and trace `## After State`
   against the final code:
   - For every participant, node and edge, confirm the named class or function
     exists, is in the expected package or module (search for it), and is
     actually on the call path.
   - If the implementation deviated from the proposed After State: update the
     After State to match the code, and add a top-level `## Deviations` section
     recording **Proposed / Built / Why**. Never keep a parallel "expected" diagram.
   - The After State must reflect the ACTUAL implementation - it is merged into
     the Source of Truth on archive.
"""

VERIFY_DIMENSION = """\
   - **Diagram fidelity (VSDD)**: Track whether `diagrams.md` After State matches the code <!-- vsdd:verify-dimension -->"""

VERIFY_FIDELITY = """\
<!-- vsdd:verify-fidelity -->
   **Diagram Fidelity (VSDD)**:
   - If `diagrams.md` exists and its `## Diagram needed?` gate is YES:
     - Treat the code as the source of truth. Trace every participant, node and
       edge in `## After State` to a real class or call in the expected package.
     - Missing or misplaced symbol:
       - Add WARNING: "Diagram does not match code: <participant/edge>"
       - Recommendation: "Update the After State to match the implementation, or fix the code"
     - Implementation deviates from the proposal but there is no `## Deviations` section:
       - Add WARNING: "Diagram deviates from proposal but no Deviations note"
       - Recommendation: "Add a `## Deviations` section (Proposed / Built / Why)"
   - If there is no `diagrams.md` or the gate is NO: note "No diagram to verify"

"""

ARCHIVE_SYNC = """\
<!-- vsdd:archive-sync -->
4a. **Sync diagrams into the Source of Truth (VSDD)**

   Read `diagrams.md` in the change directory (`<changeRoot>` when the CLI reports
   one, otherwise `openspec/changes/<name>/`), and `docs/VSDD.md` section 4.
   - Missing, or gate is NO: no-op. Record "Diagrams: no-op".
   - If `scripts/vsdd/merge_diagrams.py` exists, run it with `--dry-run` first
     and show the plan, then run it for real:
     `python3 scripts/vsdd/merge_diagrams.py <change dir>`. It validates the change
     first, including that the Before copies are still verbatim, then applies the
     Placement rows deterministically. If it refuses (exit 1), the Source of Truth
     changed after the change was proposed: stop, show the errors, and don't archive.
   - Without the script, gate YES: apply every `## Placement` row by hand. Paths are relative to the
     planning root's `openspec/`. Do removals and moves out first:
     - `remove`: delete `## <Stable Name>` from the file. Delete the file if no
       `##` diagram sections are left.
     - `move from <old>`: delete the section from `<old>` (and `<old>` itself if
       it is left empty), then write the After section into the target file:
       append it, or replace it if the name is already there.
     - `update`: replace `## <Stable Name>` in the file with the After section.
     - `add`: append the After section. Create the file with a
       `# <Domain> Diagrams` header if it doesn't exist.
   - An older change with no Placement table: merge each After section into the
     file its Before copy came from (default `specs/architecture/diagrams.md`),
     replacing a section with the same name or appending a new one.
   - Never touch a section with no Placement row. Never merge `## Before State`,
     `## Placement` or `## Deviations`.
   - If `scripts/vsdd/validate_mermaid.py` exists, run it and fix any errors
     before moving the change.
   - Show which sections were replaced, appended, moved or removed, and include a
     `**Diagrams:**` line in the final summary.
"""

ARCHIVE_DECISIONS = """\
<!-- vsdd:archive-decisions -->
4b. **Record architecture decisions (VSDD)**

   Ask: does this change teach a rule that other changes must follow? Typical cases:
   a bug fix whose cause is a pattern that could recur elsewhere (for example a
   loading state emitted after a write), or a new convention set in design.md.
   - If yes: draft an entry for `openspec/specs/architecture/decisions.md`
     (create the file with a `# Architecture Decisions` header if needed):
     `## <Stable Name>`, then **Rule:**, **Why:**, **Applies to:** and
     **Source:** `<the archived change folder name>`. Show it and **ask the user**
     before adding it. Keep it to a few lines.
   - If the change's design.md has `Overrides: <Stable Name>`, ask whether that
     entry should be updated or retired.
   - Otherwise do nothing. Include a `**Decisions:**` line in the final summary
     (added, updated, retired, or none).
"""

ARCHIVE_GUARDRAIL = """\
- VSDD: diagram merges are section-targeted by stable name, a NO gate is always a no-op, and the summary must include a Diagrams line <!-- vsdd:archive-guardrail -->"""

UPDATE_GUARDRAIL = """\
- VSDD: when revising `diagrams.md`, never edit `## Before State` (it is a verbatim Source of Truth snapshot), keep `### <Stable Name>` headings unchanged, keep the `## Placement` table in step with the Before and After sections, re-check the `## Diagram needed?` gate if the scope changed, and keep the After State consistent with the revised proposal, specs and design. Read `docs/VSDD.md` first <!-- vsdd:update-guardrail -->"""

BULK_DECISIONS = """\
- VSDD: for EACH change, also perform the decisions step (4b of the `openspec-archive-change` skill); collect the proposed entries and ask the user once, before archiving the batch <!-- vsdd:bulk-decisions -->"""

BULK_GUARDRAIL = """\
- VSDD: before moving EACH change to the archive, perform the diagram sync described in the `openspec-archive-change` skill (step 4a) for that change, in archive order <!-- vsdd:bulk-guardrail -->"""


@dataclass(frozen=True)
class Patch:
    pid: str
    anchors: tuple[str, ...]  # regexes matched against single lines; first hit wins
    where: str                # "before" | "after"
    text: str
    required: bool = True


PATCHES: dict[str, list[Patch]] = {
    "openspec-propose": [
        Patch("propose-list", (r"^- proposal\.md\b",), "after", PROPOSE_LIST, required=False),
        Patch("gen-decisions", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DECISIONS),
        Patch("gen-diagrams", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DIAGRAMS),
    ],
    "openspec-continue-change": [
        Patch("gen-decisions", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DECISIONS),
        Patch("gen-diagrams", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DIAGRAMS),
    ],
    "openspec-ff-change": [
        Patch("gen-decisions", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DECISIONS),
        Patch("gen-diagrams", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DIAGRAMS),
    ],
    "openspec-update-change": [
        Patch("update-guardrail", (r"^\*\*Guardrails\*\*\s*$",), "after", UPDATE_GUARDRAIL),
    ],
    "openspec-apply-change": [
        Patch("apply-trace", (r"^\d+\.\s+\*\*On completion or pause", r"^\*\*Guardrails\*\*"), "before", APPLY_TRACE),
    ],
    "openspec-verify-change": [
        Patch("verify-dimension", (r"^\s*- \*\*Coherence\*\*:",), "after", VERIFY_DIMENSION, required=False),
        Patch("verify-fidelity", (r"^\d+\.\s+\*\*Generate Verification Report", r"^\*\*Verification Heuristics\*\*"), "before", VERIFY_FIDELITY),
    ],
    "openspec-archive-change": [
        Patch("archive-sync", (r"^\d+\.\s+\*\*Perform the archive",), "before", ARCHIVE_SYNC),
        Patch("archive-decisions", (r"^\d+\.\s+\*\*Perform the archive",), "before", ARCHIVE_DECISIONS),
        Patch("archive-guardrail", (r"^\*\*Guardrails\*\*\s*$",), "after", ARCHIVE_GUARDRAIL),
    ],
    "openspec-bulk-archive-change": [
        Patch("bulk-guardrail", (r"^\*\*Guardrails\*\*\s*$",), "after", BULK_GUARDRAIL),
        Patch("bulk-decisions", (r"^\*\*Guardrails\*\*\s*$",), "after", BULK_DECISIONS),
    ],
}

for _patches in PATCHES.values():
    _patches.insert(0, Patch("guard", (FRONTMATTER_END,), "after", GUARD))

# /opsx command name -> skill it should delegate to
COMMANDS = {
    "propose": "openspec-propose",
    "continue": "openspec-continue-change",
    "ff": "openspec-ff-change",
    "update": "openspec-update-change",
    "apply": "openspec-apply-change",
    "verify": "openspec-verify-change",
    "archive": "openspec-archive-change",
    "bulk-archive": "openspec-bulk-archive-change",
}

WRAPPER_MARK = "<!-- vsdd:wrapper -->"


def wrapper_body(location: str, skill: str) -> str:
    return (
        f"{WRAPPER_MARK}\n"
        f"Load the `{skill}` skill and follow it exactly. Its instructions are in\n"
        f"{location} - read that file now if the skill is not already loaded.\n"
        f"Treat any text given with this command as the skill's input\n"
        f"(for example a change name or a description of the change).\n"
    )


def tool_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith(".") and p.name not in SKIP_DIRS)


def expand_extra(extra: Path) -> list[Path]:
    """A tool folder (e.g. ~/.minimax) as is; a shared workspace folder as its tool folders."""
    if extra.name.startswith("."):
        return [extra]
    return tool_dirs(extra) or [extra]


def skill_location(target: Path, root: Path, owner: Path | None) -> str:
    """How a wrapper names its skill file: project-relative, ~/..., or <workspace folder>/..."""
    if target.is_relative_to(root):
        return f"`{target.relative_to(root)}`"
    home = Path.home()
    if target.is_relative_to(home) and owner is not None and owner.parent == home:
        return f"`~/{target.relative_to(home)}`"
    base = owner.parent if owner is not None and owner.name.startswith(".") else (owner or target.parent)
    return f"`{target.relative_to(base.parent)}` (in the `{base.name}` folder of this workspace)"


def walk(base: Path, depth: int = 4):
    if depth < 0:
        return
    try:
        entries = list(base.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name in SKIP_DIRS:
            continue
        if entry.is_dir():
            yield from walk(entry, depth - 1)
        else:
            yield entry


def apply_patches(text: str, patches: list[Patch]) -> tuple[str, list[str], list[str]]:
    applied: list[str] = []
    missing: list[str] = []
    lines = text.split("\n")
    for patch in patches:
        present = [i for i, l in enumerate(lines) if f"<!-- vsdd:{patch.pid} -->" in l]
        if present:
            block = patch.text.rstrip("\n")
            # Single-line blocks carry their marker inline, so they can be refreshed in place.
            if "\n" not in block and lines[present[0]] != block:
                lines[present[0]] = block
                applied.append(f"{patch.pid} (refreshed)")
            continue
        idx = None
        for anchor in patch.anchors:
            if anchor == FRONTMATTER_END:
                if lines and lines[0].strip() == "---":
                    idx = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
                else:
                    idx = -1 if lines else None  # no front matter: insert at the top
            else:
                rx = re.compile(anchor)
                idx = next((i for i, l in enumerate(lines) if rx.search(l)), None)
            if idx is not None:
                break
        if idx is None:
            if patch.required:
                missing.append(patch.pid)
            continue
        block = patch.text.rstrip("\n").split("\n")
        if patch.where == "after":
            insert_at = idx + 1
            pad = [] if len(block) == 1 else [""]
            lines[insert_at:insert_at] = pad + block
        else:
            lines[idx:idx] = block + [""]
        applied.append(patch.pid)
    return "\n".join(lines), applied, missing


def rewrite_command(path: Path, body: str) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        desc = re.search(r'^description\s*=\s*".*"$', text, re.M)
        head = desc.group(0) + "\n\n" if desc else ""
        return f'{head}prompt = """\n{body}"""\n'
    fm = re.match(r"^---\n.*?\n---\n", text, re.S)
    if fm:
        return fm.group(0) + "\n" + body
    heading = re.match(r"^# .*\n", text)  # e.g. Cline workflows: "# OPSX: Propose"
    return (heading.group(0) + "\n" if heading else "") + body


def command_name(path: Path) -> str | None:
    stem = path.name
    for suffix in (".prompt.md", ".md", ".toml", ".prompt"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        return None
    if stem.startswith("opsx-"):
        return stem[len("opsx-"):]
    if path.parent.name == "opsx":
        return stem
    return None


def display(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--no-commands", action="store_true", help="patch skills only")
    ap.add_argument("--extra-dir", type=Path, action="append", default=[],
                    help="also patch this folder: a tool folder outside the project (e.g. ~/.minimax), "
                         "or a shared workspace folder holding tool folders (.devin/, .github/, ...). "
                         "Repeatable. Affects every project that uses it: ask first")
    args = ap.parse_args()
    root = args.root.resolve()
    extra = [d.expanduser().resolve() for d in args.extra_dir if d.expanduser().is_dir()]
    dirs = tool_dirs(root) + [t for d in extra for t in expand_extra(d)]

    # Pass 1: patch skills in every tool folder, remembering where each skill lives.
    skills_found = 0
    problems = 0
    files_by_dir: dict[Path, list[Path]] = {}
    skills_by_dir: dict[Path, dict[str, Path]] = {}
    for tdir in dirs:
        files = list(walk(tdir))
        files_by_dir[tdir] = files
        skill_paths = {f.parent.name: f for f in files
                       if f.name == "SKILL.md" and f.parent.name.startswith("openspec-")}
        skills_by_dir[tdir] = skill_paths
        if not skill_paths:
            continue
        print(f"[{display(tdir, root)}]")
        for skill, path in sorted(skill_paths.items()):
            skills_found += 1
            patches = PATCHES.get(skill)
            if not patches:
                continue
            original = path.read_text(encoding="utf-8")
            new, applied, missing = apply_patches(original, patches)
            rel = display(path, root)
            if missing:
                problems += 1
                print(f"  ! {rel}: anchor not found for {', '.join(missing)} - apply by hand (see SETUP.md)")
            if applied:
                if args.check:
                    problems += 1
                    print(f"  x {rel}: overlay missing ({', '.join(applied)})")
                elif args.dry_run:
                    print(f"  ~ {rel}: would insert {', '.join(applied)}")
                else:
                    path.write_text(new, encoding="utf-8")
                    print(f"  + {rel}: inserted {', '.join(applied)}")
            elif not missing:
                print(f"  = {rel}: up to date")

    # Pass 2: wrap /opsx commands. Some tools keep commands in a folder without skills
    # (Kilo: .kilo/command, Cline: .clinerules/workflows) - point those at a patched copy
    # elsewhere in the project, preferring the shared .agents/skills.
    def skill_for(tdir: Path, skill: str) -> Path | None:
        if skill in skills_by_dir.get(tdir, {}):
            return skills_by_dir[tdir][skill]
        candidates = sorted((d for d in dirs if skill in skills_by_dir.get(d, {}) and d.is_relative_to(root)),
                            key=lambda d: (not (d.name.startswith(tdir.name) or tdir.name.startswith(d.name)),
                                           d.name != ".agents", d.name))
        return skills_by_dir[candidates[0]][skill] if candidates else None

    if not args.no_commands:
        for tdir in dirs:
            header_printed = False
            for f in sorted(files_by_dir[tdir]):
                cmd = command_name(f)
                skill = COMMANDS.get(cmd or "")
                if not skill:
                    continue
                target = skill_for(tdir, skill)
                if target is None:
                    continue
                if not header_printed:
                    print(f"[{display(tdir, root)}] commands")
                    header_printed = True
                rel = display(f, root)
                if WRAPPER_MARK in f.read_text(encoding="utf-8"):
                    print(f"  = {rel}: wrapper up to date")
                    continue
                if args.check:
                    problems += 1
                    print(f"  x {rel}: stock command (bypasses VSDD skill)")
                elif args.dry_run:
                    print(f"  ~ {rel}: would become wrapper -> {skill}")
                else:
                    owner = next((d for d in dirs if target.is_relative_to(d)), None)
                    body = wrapper_body(skill_location(target, root, owner), skill)
                    f.write_text(rewrite_command(f, body), encoding="utf-8")
                    print(f"  + {rel}: now wraps {skill}")

    if skills_found == 0:
        print("No OpenSpec skills found. Run `openspec init --tools <tool>` first.", file=sys.stderr)
        return 2
    if problems:
        print(f"{problems} problem(s).")
        return 1
    print("VSDD overlay OK." if args.check else "Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
