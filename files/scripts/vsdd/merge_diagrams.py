#!/usr/bin/env python3
"""Merge a change's diagrams.md into the diagram Source of Truth (VSDD archive step).

Applies every row of the change's `## Placement` table, as docs/VSDD.md section 4
describes: removals and moves out first, then updates and additions.

  remove              delete `## <Stable Name>` from the file (and the file if no
                      diagram sections are left)
  move from <old>     delete from <old> (and <old> if left empty), then write the
                      After section into the target file (append, or replace)
  update              replace `## <Stable Name>` with the After section
  add                 append the After section (create the file if needed)

The change is validated first, including that every Before copy is still a
verbatim copy of the Source of Truth. If the Source of Truth changed after the change
was proposed, nothing is written.

Usage (from the project root):
  python3 scripts/vsdd/merge_diagrams.py openspec/changes/<name>            # merge
  python3 scripts/vsdd/merge_diagrams.py openspec/changes/<name> --dry-run  # show plan

Running it twice gives the same result. Exit codes: 0 merged or no-op,
1 validation failed (nothing written), 2 bad invocation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_mermaid import (  # noqa: E402
    GATE_RE,
    _parse_placement,
    _sections,
    check_change_structure,
)


def _is_heading(line: str, level: int) -> bool:
    hashes = len(line) - len(line.lstrip("#"))
    return 0 < hashes <= level and line[hashes:hashes + 1] == " "


def _span(lines: list[str], name: str) -> tuple[int, int] | None:
    """[start, end) line indexes of the `## name` section, fences respected."""
    in_fence, start = False, None
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if start is None and line.rstrip() == f"## {name}":
            start = i
        elif start is not None and _is_heading(line, 2):
            return start, i
    return (start, len(lines)) if start is not None else None


def _has_diagram_sections(text: str) -> bool:
    return any(n for n, _, _ in _sections(text.splitlines(), "##"))


def _normalise(text: str) -> str:
    return text.rstrip("\n") + "\n"


def _remove(text: str, name: str) -> tuple[str, bool]:
    lines = text.splitlines()
    span = _span(lines, name)
    if span is None:
        return text, False
    del lines[span[0]:span[1]]
    return _normalise("\n".join(lines)), True


def _put(text: str, name: str, body: str) -> tuple[str, str]:
    """Replace the section if present, else append. Returns (text, 'replaced'|'appended')."""
    block = [f"## {name}", "", *body.splitlines(), ""]
    lines = text.splitlines()
    span = _span(lines, name)
    if span is not None:
        lines[span[0]:span[1]] = block
        return _normalise("\n".join(lines)), "replaced"
    return _normalise(text.rstrip("\n") + "\n\n" + "\n".join(block)), "appended"


def _section_body(root: Path, rel: str, name: str) -> str | None:
    path = root / "openspec" / rel
    if not path.is_file():
        return None
    for n, _, body in _sections(path.read_text(encoding="utf-8").splitlines(), "##"):
        if n == name:
            return body
    return None


def _already_merged(lines: list[str], h2: dict, root: Path) -> bool:
    """True when every Placement row is already reflected in the Source of Truth."""
    if "Placement" not in h2 or "After State" not in h2:
        return False
    rows, errs = _parse_placement(h2["Placement"][1])
    if errs or not rows:
        return False
    after_line = h2["After State"][0]
    next_h2 = min((ln for ln, _ in h2.values() if ln > after_line), default=len(lines) + 1)
    after = {n: body for n, ln, body in _sections(lines, "###") if after_line < ln < next_h2}
    for name, target, action, move_from in rows:
        if action == "remove":
            if _section_body(root, target, name) is not None:
                return False
            continue
        if name not in after or _section_body(root, target, name) != after[name]:
            return False
        if action == "move" and _section_body(root, move_from, name) is not None:
            return False
    return True


def _title_for(path: Path) -> str:
    return path.parent.name.replace("-", " ").replace("_", " ").title()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("change_dir", type=Path, help="the change directory (contains diagrams.md)")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: cwd)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = ap.parse_args()

    root = args.root.resolve()
    diagrams = (args.change_dir if args.change_dir.is_absolute() else root / args.change_dir) / "diagrams.md"
    if not diagrams.is_file():
        print(f"Diagrams: no-op (no {diagrams.relative_to(root) if diagrams.is_relative_to(root) else diagrams})")
        return 0
    lines = diagrams.read_text(encoding="utf-8").splitlines()
    h2 = {n: (ln, body) for n, ln, body in _sections(lines, "##")}
    gate = next((l for l in h2.get("Diagram needed?", (0, ""))[1].splitlines()
                 if l.strip() and not l.strip().startswith("<!--")), "")
    m = GATE_RE.match(gate)
    if m and m.group(1).upper() == "NO":
        print("Diagrams: no-op (NO gate)")
        return 0

    errors = check_change_structure(diagrams, lines, root, verify_before=True)
    if errors and _already_merged(lines, h2, root):
        print("Diagrams: already merged (Source of Truth matches the After State) - nothing to do")
        return 0
    if errors:
        for line_no, msg in errors:
            print(f"{diagrams.name}:{line_no}: {msg}", file=sys.stderr)
        print("Not merged: fix diagrams.md first (nothing was written).", file=sys.stderr)
        return 1

    rows, _ = _parse_placement(h2["Placement"][1])
    after_line = h2["After State"][0]
    next_h2 = min((ln for ln, _ in h2.values() if ln > after_line), default=len(lines) + 1)
    after = {n: body for n, ln, body in _sections(lines, "###") if after_line < ln < next_h2}

    files: dict[Path, str | None] = {}

    def load(rel: str) -> str | None:
        path = root / "openspec" / rel
        if path not in files:
            files[path] = path.read_text(encoding="utf-8") if path.is_file() else None
        return files[path]

    report: list[str] = []
    order = {"remove": 0, "move": 1, "update": 2, "add": 3}
    for name, target, action, move_from in sorted(rows, key=lambda r: order[r[2]]):
        if action == "remove":
            text = load(target)
            new, done = _remove(text or "", name)
            files[root / "openspec" / target] = new
            report.append(f"removed: {name} from {target}" if done else f"already absent: {name} in {target}")
            continue
        if action == "move":
            text = load(move_from)
            new, done = _remove(text or "", name)
            files[root / "openspec" / move_from] = new
            if not done:
                report.append(f"already moved out: {name} from {move_from}")
        text = load(target)
        if text is None:
            text = f"# {_title_for(root / 'openspec' / target)} Diagrams\n"
        new, how = _put(text, name, after[name])
        files[root / "openspec" / target] = new
        verb = {"move": f"moved: {name} from {move_from} to", "add": f"added ({how}): {name} to",
                "update": f"{how}: {name} in"}[action]
        report.append(f"{verb} {target}")

    for line in report:
        print(("would be " if args.dry_run else "") + line)
    for path, text in files.items():
        rel = path.relative_to(root)
        if text is None:
            continue
        if not _has_diagram_sections(text):
            if path.exists():
                print(("would delete" if args.dry_run else "deleted") + f" empty file: {rel}")
                if not args.dry_run:
                    path.unlink()
            continue
        if args.dry_run:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if not args.dry_run:
        print(f"Diagrams: merged {len(rows)} placement row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
