#!/usr/bin/env python3
"""Apply the VSDD overlay to OpenSpec-generated skills and /opsx commands.

`openspec init` / `openspec update` (re)generate stock skills and commands for
each configured AI tool (.claude/, .opencode/, .qwen/, .cursor/, ...). Stock
files know nothing about diagrams, and `openspec update` overwrites any edits.
This script re-applies the VSDD additions:

  skills   - inserts diagram steps into openspec-{propose,continue-change,
             ff-change,update-change,apply-change,verify-change,
             archive-change,bulk-archive-change} at anchor lines. Idempotent: each insertion
             carries a `<!-- vsdd:<id> -->` marker and is skipped if present.
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
    (Stable name | Source of Truth file | Action) with one row per diagram touched.
    Action is update, add, `move from <old file>` or remove. Diagrams belong to the
    capability whose behaviour they show. If the change creates a capability,
    consider moving its flows into `specs/<capability>/diagrams.md`.
  - Copy the Before sections VERBATIM from the files the rows name, then write the
    After sections under the SAME stable names. Removed diagrams have no After.
- Read `docs/MERMAID_RULES.md` before drafting any diagram. Then run
  `python3 scripts/vsdd/validate_mermaid.py`: it checks the Placement table and
  that the Before copies are verbatim.
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

ARCHIVE_GUARDRAIL = """\
- VSDD: diagram merges are section-targeted by stable name, a NO gate is always a no-op, and the summary must include a Diagrams line <!-- vsdd:archive-guardrail -->"""

UPDATE_GUARDRAIL = """\
- VSDD: when revising `diagrams.md`, never edit `## Before State` (it is a verbatim Source of Truth snapshot), keep `### <Stable Name>` headings unchanged, keep the `## Placement` table in step with the Before and After sections, re-check the `## Diagram needed?` gate if the scope changed, and keep the After State consistent with the revised proposal, specs and design. Read `docs/VSDD.md` first <!-- vsdd:update-guardrail -->"""

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
        Patch("gen-diagrams", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DIAGRAMS),
    ],
    "openspec-continue-change": [
        Patch("gen-diagrams", (r"^\*\*Artifact Creation Guidelines\*\*\s*$",), "after", GEN_DIAGRAMS),
    ],
    "openspec-ff-change": [
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
        Patch("archive-guardrail", (r"^\*\*Guardrails\*\*\s*$",), "after", ARCHIVE_GUARDRAIL),
    ],
    "openspec-bulk-archive-change": [
        Patch("bulk-guardrail", (r"^\*\*Guardrails\*\*\s*$",), "after", BULK_GUARDRAIL),
    ],
}

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


def wrapper_body(skill_rel: str, skill: str) -> str:
    return (
        f"{WRAPPER_MARK}\n"
        f"Load the `{skill}` skill and follow it exactly. Its instructions are in\n"
        f"`{skill_rel}` - read that file now if the skill is not already loaded.\n"
        f"Treat any text given with this command as the skill's input\n"
        f"(for example a change name or a description of the change).\n"
    )


def tool_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith(".") and p.name not in SKIP_DIRS)


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
        if f"vsdd:{patch.pid}" in "\n".join(lines):
            continue
        idx = None
        for anchor in patch.anchors:
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
    return (fm.group(0) + "\n" if fm else "") + body


def command_name(path: Path) -> str | None:
    stem = path.name
    for suffix in (".prompt.md", ".md", ".toml"):
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--no-commands", action="store_true", help="patch skills only")
    args = ap.parse_args()
    root = args.root.resolve()

    skills_found = 0
    problems = 0
    for tdir in tool_dirs(root):
        files = list(walk(tdir))
        skill_paths: dict[str, Path] = {}
        for f in files:
            if f.name == "SKILL.md" and f.parent.name.startswith("openspec-"):
                skill_paths[f.parent.name] = f
        if not skill_paths:
            continue
        print(f"[{tdir.name}]")
        for skill, path in sorted(skill_paths.items()):
            skills_found += 1
            patches = PATCHES.get(skill)
            if not patches:
                continue
            original = path.read_text(encoding="utf-8")
            new, applied, missing = apply_patches(original, patches)
            rel = path.relative_to(root)
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

        if args.no_commands:
            continue
        for f in sorted(files):
            cmd = command_name(f)
            skill = COMMANDS.get(cmd or "")
            if not skill or skill not in skill_paths:
                continue
            rel = f.relative_to(root)
            if WRAPPER_MARK in f.read_text(encoding="utf-8"):
                print(f"  = {rel}: wrapper up to date")
                continue
            if args.check:
                problems += 1
                print(f"  x {rel}: stock command (bypasses VSDD skill)")
            elif args.dry_run:
                print(f"  ~ {rel}: would become wrapper -> {skill}")
            else:
                body = wrapper_body(str(skill_paths[skill].relative_to(root)), skill)
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
