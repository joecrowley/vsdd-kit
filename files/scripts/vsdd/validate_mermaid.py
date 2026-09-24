#!/usr/bin/env python3
"""Validate Mermaid blocks in OpenSpec markdown against docs/MERMAID_RULES.md.

Lint checks (always):
  - flowchart/graph declares a direction (TD, TB, BT, LR, RL)
  - no semicolons inside diagram lines
  - no +/- activation shorthand on sequence-diagram arrows
  - no quoted participant/actor aliases (they render with literal quotes)
  - unclosed ```mermaid fences

Render check (--render): parses every block with mermaid-cli (`mmdc`), which
catches anything the linter cannot (unquoted labels, bad syntax).

Structure checks (active change diagrams.md files):
  - first section is `## Diagram needed?` with a YES or NO decision
  - YES gate has `## Placement`, `## Before State` and `## After State`
  - every Placement row (update / add / move from <file> / remove) matches the
    Before and After `### <Stable Name>` sections, and vice versa
  - Before sections are verbatim copies of the Source of Truth file the row names
    (checked for active changes only - archived ones describe an older state)
  - a row that adds or moves a diagram INTO specs/architecture/diagrams.md has a
    4th column, `Why here`, saying why it spans capabilities

Decisions log (openspec/specs/**/decisions.md):
  - every `## <Stable Name>` entry has **Rule:**, **Why:** and **Source:** lines

Ownership warnings (active changes; printed, but they don't fail the run):
  - the change creates a capability (it has specs/<cap>/ and openspec/specs/<cap>/
    doesn't exist yet) and still adds or moves a diagram into the architecture file

Usage:
  python3 scripts/vsdd/validate_mermaid.py                 # openspec/specs + active changes
  python3 scripts/vsdd/validate_mermaid.py --render        # plus mmdc parse
  python3 scripts/vsdd/validate_mermaid.py --include-archive
  python3 scripts/vsdd/validate_mermaid.py path/to/file.md ...

Exit code 0 = clean, 1 = errors found, 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DIRECTION_RE = re.compile(r"^\s*(flowchart|graph)\s+(TD|TB|BT|LR|RL)\b")
FLOW_HEADER_RE = re.compile(r"^\s*(flowchart|graph)\b")
SEQ_SHORTHAND_RE = re.compile(r"(--?>>|--?>|--?x|--?\))[+-]")
QUOTED_ALIAS_RE = re.compile(r'^\s*(participant|actor)\s+\S+\s+as\s+"')
GATE_RE = re.compile(r"^\s*(YES|NO)\b", re.IGNORECASE)


def find_files(root: Path, include_archive: bool) -> list[Path]:
    files: list[Path] = []
    for base in (root / "openspec" / "specs", root / "openspec" / "changes"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            if not include_archive and "archive" in path.relative_to(base).parts:
                continue
            files.append(path)
    return files


def extract_blocks(lines: list[str]) -> tuple[list[tuple[int, list[str]]], list[int]]:
    """Return ([(start_line, block_lines)], [unclosed_fence_lines])."""
    blocks: list[tuple[int, list[str]]] = []
    unclosed: list[int] = []
    in_block = False
    start = 0
    buf: list[str] = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not in_block and stripped.startswith("```mermaid"):
            in_block, start, buf = True, i, []
        elif in_block and stripped.startswith("```"):
            blocks.append((start, buf))
            in_block = False
        elif in_block:
            buf.append(line)
    if in_block:
        unclosed.append(start)
    return blocks, unclosed


def lint_block(start: int, block: list[str]) -> list[tuple[int, str]]:
    errors: list[tuple[int, str]] = []
    body = [(start + 1 + n, l) for n, l in enumerate(block)]
    content = [(n, l) for n, l in body if l.strip() and not l.strip().startswith("%%")]
    if not content:
        return [(start, "empty mermaid block")]
    first_no, first = content[0]
    kind = first.strip().split()[0]
    if FLOW_HEADER_RE.match(first) and not DIRECTION_RE.match(first):
        errors.append((first_no, "flowchart must declare a direction (TD, LR, ...)"))
    for n, line in content:
        if ";" in line:
            errors.append((n, "semicolon in diagram - use a comma, dash or period"))
        if kind == "sequenceDiagram" and SEQ_SHORTHAND_RE.search(line):
            errors.append((n, "use explicit activate/deactivate, not +/- shorthand"))
        if kind == "sequenceDiagram" and QUOTED_ALIAS_RE.match(line):
            errors.append((n, "participant alias must not be quoted - quotes render literally"))
    return errors


PLACEMENT_ACTION_RE = re.compile(r"^(update|add|remove|move from\s+(\S+))$")
ARCHITECTURE_FILE = "specs/architecture/diagrams.md"


def _sections(lines: list[str], level: str) -> list[tuple[str, int, str]]:
    """Ordered (heading text, line number, body) for headings of one level ('##', '###')."""
    out: list[tuple[str, int, str]] = []
    current, start, buf = None, 0, []
    in_fence = False
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        heading = not in_fence and line.startswith("#")
        if heading and (line.startswith(level + " ") or len(line) - len(line.lstrip("#")) <= len(level)):
            if current is not None:
                out.append((current, start, "\n".join(buf).strip()))
            current, start, buf = (line[len(level) + 1:].strip(), i, []) if line.startswith(level + " ") else (None, 0, [])
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        out.append((current, start, "\n".join(buf).strip()))
    return out


def _placement_cells(body: str) -> list[tuple[str, list[str]]]:
    """(raw line, cells) for each table row of a Placement section, header and rule excluded."""
    out = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if cells and cells[0].lower() == "stable name":
            continue
        out.append((line, cells))
    return out


def _placement_reasons(body: str) -> dict[str, str]:
    """{stable name: 'Why here' text} from the optional 4th Placement column."""
    return {cells[0]: cells[3] for _, cells in _placement_cells(body) if len(cells) == 4}


def _parse_placement(body: str) -> tuple[list[tuple[str, str, str, str | None]], list[str]]:
    """Return ([(name, file, action, move_from)], [errors]) from a Placement table.

    Columns: Stable name | Source of Truth file | Action [| Why here].
    """
    rows, errors = [], []
    for line, cells in _placement_cells(body):
        if len(cells) not in (3, 4):
            errors.append(f"Placement row needs 3 or 4 columns: {line}")
            continue
        name, target, action = cells[:3]
        m = PLACEMENT_ACTION_RE.match(action)
        if not m:
            errors.append(f"Placement '{name}': action must be update, add, remove or 'move from <file>'")
            continue
        move_from = m.group(2).strip("`") if m.group(2) else None
        for f in (target, move_from):
            if f and not (f.startswith("specs/") and f.endswith("diagrams.md")):
                errors.append(f"Placement '{name}': '{f}' must be a specs/**/diagrams.md path under openspec/")
        rows.append((name, target, m.group(1).split()[0], move_from))
    return rows, errors


def check_change_structure(path: Path, lines: list[str], root: Path, verify_before: bool) -> list[tuple[int, str]]:
    h2 = {n: (ln, body) for n, ln, body in _sections(lines, "##")}
    names = [n for n, _, _ in _sections(lines, "##")]
    if not names or names[0] != "Diagram needed?":
        return [(1, "change diagrams.md must start with '## Diagram needed?'")]
    gate_line_no, gate_body = h2["Diagram needed?"]
    gate_text = next((l for l in gate_body.splitlines() if l.strip() and not l.strip().startswith("<!--")), "")
    match = GATE_RE.match(gate_text)
    if not match:
        return [(gate_line_no, "gate must record YES or NO")]
    if match.group(1).upper() == "NO":
        return []

    errors: list[tuple[int, str]] = []
    for required in ("Placement", "Before State", "After State"):
        if required not in h2:
            errors.append((1, f"YES gate requires '## {required}'"))
    if errors:
        return errors

    rows, row_errors = _parse_placement(h2["Placement"][1])
    placement_line = h2["Placement"][0]
    errors += [(placement_line, e) for e in row_errors]
    if not rows and not row_errors:
        errors.append((placement_line, "Placement table has no rows"))
    reasons = _placement_reasons(h2["Placement"][1])
    for name, target, action, _ in rows:
        if target == ARCHITECTURE_FILE and action in ("add", "move") and not reasons.get(name):
            errors.append((placement_line, f"'{name}' ({action}) goes into the architecture file: add a 4th "
                           "column 'Why here' saying which capabilities it spans, or place it in "
                           "specs/<capability>/diagrams.md"))

    before_line, _ = h2["Before State"]
    after_line, _ = h2["After State"]
    h3 = _sections(lines, "###")
    next_h2 = min((ln for n, (ln, _) in h2.items() if ln > after_line), default=len(lines) + 1)
    before = {n: (ln, body) for n, ln, body in h3 if before_line < ln < after_line}
    after = {n: (ln, body) for n, ln, body in h3 if after_line < ln < next_h2}

    seen = set()
    for name, target, action, move_from in rows:
        if name in seen:
            errors.append((placement_line, f"Placement lists '{name}' twice"))
        seen.add(name)
        needs_before = action in ("update", "move", "remove")
        needs_after = action in ("update", "add", "move")
        if needs_before and name not in before:
            errors.append((before_line, f"'{name}' ({action}) needs '### {name}' under Before State"))
        if action == "add" and name in before:
            errors.append((before_line, f"'{name}' is 'add' but has a Before section - use update or move"))
        if needs_after and name not in after:
            errors.append((after_line, f"'{name}' ({action}) needs '### {name}' under After State"))
        if action == "remove" and name in after:
            errors.append((after_line, f"'{name}' is 'remove' and must not have an After section"))
        if verify_before and needs_before and name in before:
            source = move_from if action == "move" else target
            sot = root / "openspec" / source
            if not sot.is_file():
                errors.append((before[name][0], f"'{name}': Source of Truth file openspec/{source} not found"))
            else:
                sot_sections = {n: (ln, body) for n, ln, body in _sections(sot.read_text(encoding="utf-8").splitlines(), "##")}
                if name not in sot_sections:
                    errors.append((before[name][0], f"'{name}' not found as '## {name}' in openspec/{source}"))
                elif sot_sections[name][1] != before[name][1]:
                    errors.append((before[name][0], f"Before '{name}' is not a verbatim copy of openspec/{source}"))
    for name in after:
        if name not in seen:
            errors.append((after[name][0], f"After section '{name}' has no Placement row"))
    for name in before:
        if name not in seen:
            errors.append((before[name][0], f"Before section '{name}' has no Placement row"))
    return errors


DECISION_FIELDS = ("Rule", "Why", "Source")


def check_decisions(lines: list[str]) -> list[tuple[int, str]]:
    """Each `## <Stable Name>` entry of a decisions log needs Rule, Why and Source."""
    errors = []
    for name, line_no, body in _sections(lines, "##"):
        missing = [f for f in DECISION_FIELDS if not re.search(rf"\*\*{f}:\*\*\s*\S", body)]
        if missing:
            errors.append((line_no, f"decision '{name}' needs {', '.join(f'**{f}:**' for f in missing)}"))
    return errors


def new_capabilities(change_dir: Path, root: Path) -> list[str]:
    """Capabilities this change creates: specs/<cap>/ in the change, not yet in openspec/specs/."""
    specs = change_dir / "specs"
    if not specs.is_dir():
        return []
    return sorted(d.name for d in specs.iterdir()
                  if d.is_dir() and not (root / "openspec" / "specs" / d.name).exists())


def ownership_warnings(path: Path, lines: list[str], root: Path) -> list[tuple[int, str]]:
    """Warn when a change creates a capability but places a new diagram in the architecture file."""
    h2 = {n: (ln, body) for n, ln, body in _sections(lines, "##")}
    if "Placement" not in h2:
        return []
    caps = new_capabilities(path.parent, root)
    if not caps:
        return []
    rows, _ = _parse_placement(h2["Placement"][1])
    reasons = _placement_reasons(h2["Placement"][1])
    owner = " or ".join(f"specs/{c}/diagrams.md" for c in caps)
    return [(h2["Placement"][0],
             f"this change creates {', '.join(caps)}, but '{name}' ({action}) goes into the architecture "
             f"file. A diagram belongs to the capability whose behaviour it shows - check whether it "
             f"belongs in {owner} (Why here: {reasons.get(name) or '-'})")
            for name, target, action, _ in rows
            if target == ARCHITECTURE_FILE and action in ("add", "move")]


def render_blocks(items: list[tuple[Path, int, list[str]]]) -> list[tuple[Path, int, str]]:
    mmdc = shutil.which("mmdc")
    if not mmdc:
        print("error: --render needs mermaid-cli (npm i -g @mermaid-js/mermaid-cli)", file=sys.stderr)
        sys.exit(2)
    failures: list[tuple[Path, int, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "puppeteer.json"
        cfg.write_text(json.dumps({"args": ["--no-sandbox"]}))
        for idx, (path, start, block) in enumerate(items):
            src = Path(tmp) / f"d{idx}.mmd"
            src.write_text("\n".join(block) + "\n")
            proc = subprocess.run(
                [mmdc, "-q", "-p", str(cfg), "-i", str(src), "-o", str(src.with_suffix(".svg"))],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                msg = (proc.stderr or proc.stdout).strip().splitlines()
                detail = next((m for m in msg if "Error" in m or "error" in m), msg[0] if msg else "render failed")
                failures.append((path, start, f"render failed: {detail[:200]}"))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path, help="markdown files (default: scan openspec/)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: cwd)")
    parser.add_argument("--render", action="store_true", help="also parse each diagram with mmdc")
    parser.add_argument("--include-archive", action="store_true", help="also scan openspec/changes/archive")
    parser.add_argument("--strict-archive", action="store_true",
                        help="also apply the change-structure checks to archived changes (older ones predate Placement)")
    args = parser.parse_args()

    root = args.root.resolve()
    files = [p.resolve() for p in args.paths] if args.paths else find_files(root, args.include_archive)
    problems: list[tuple[Path, int, str]] = []
    warnings: list[tuple[Path, int, str]] = []
    to_render: list[tuple[Path, int, list[str]]] = []
    block_count = 0

    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        blocks, unclosed = extract_blocks(lines)
        block_count += len(blocks)
        problems += [(path, n, "unclosed ```mermaid fence") for n in unclosed]
        for start, block in blocks:
            problems += [(path, n, msg) for n, msg in lint_block(start, block)]
            to_render.append((path, start, block))
        if path.name == "decisions.md" and "specs" in path.parts and "changes" not in path.parts:
            problems += [(path, n, msg) for n, msg in check_decisions(lines)]
        is_change = "changes" in path.parts and "specs" not in path.parts[path.parts.index("changes"):]
        if path.name == "diagrams.md" and is_change:
            archived = "archive" in path.parts[path.parts.index("changes"):]
            if not (archived and args.include_archive and not args.strict_archive):
                problems += [(path, n, msg) for n, msg in check_change_structure(path, lines, root, not archived)]
            if not archived:
                warnings += [(path, n, msg) for n, msg in ownership_warnings(path, lines, root)]

    if args.render and to_render:
        problems += render_blocks(to_render)

    def show(path: Path) -> Path:
        try:
            return path.relative_to(root)
        except ValueError:
            return path

    for path, line, msg in sorted(problems, key=lambda p: (str(p[0]), p[1])):
        print(f"{show(path)}:{line}: {msg}")
    for path, line, msg in sorted(warnings, key=lambda p: (str(p[0]), p[1])):
        print(f"{show(path)}:{line}: warning: {msg}")
    status = "FAIL" if problems else "OK"
    print(f"{status}: {len(files)} files, {block_count} mermaid blocks, {len(problems)} problems"
          + (f", {len(warnings)} warnings" if warnings else "")
          + (" (rendered)" if args.render else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
