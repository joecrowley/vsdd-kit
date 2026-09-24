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

Structure checks (always, change diagrams.md only):
  - first section is `## Diagram needed?` with a YES or NO decision
  - YES gate has `## Before State` and `## After State`
  - After State diagrams sit under `### <Stable Name>` headings

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


def check_change_structure(path: Path, lines: list[str]) -> list[tuple[int, str]]:
    headings = [(i, l.rstrip()) for i, l in enumerate(lines, 1) if l.startswith("#")]
    if not headings or headings[0][1] != "## Diagram needed?":
        return [(1, "change diagrams.md must start with '## Diagram needed?'")]
    gate_line = next(
        (l for l in lines[headings[0][0]:] if l.strip() and not l.strip().startswith("<!--")),
        "",
    )
    match = GATE_RE.match(gate_line)
    if not match:
        return [(headings[0][0], "gate must record YES or NO")]
    if match.group(1).upper() == "NO":
        return []
    errors: list[tuple[int, str]] = []
    names = [h for _, h in headings]
    for required in ("## Before State", "## After State"):
        if required not in names:
            errors.append((1, f"YES gate requires '{required}'"))
    if "## After State" in names:
        after_idx = names.index("## After State")
        after_line = headings[after_idx][0]
        next_h2 = next(
            (ln for ln, h in headings[after_idx + 1:] if h.startswith("## ")), len(lines) + 1
        )
        has_stable = any(
            h.startswith("### ") for ln, h in headings if after_line < ln < next_h2
        )
        if not has_stable:
            errors.append((after_line, "After State needs '### <Stable Name>' sections"))
    return errors


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
    args = parser.parse_args()

    root = args.root.resolve()
    files = [p.resolve() for p in args.paths] if args.paths else find_files(root, args.include_archive)
    problems: list[tuple[Path, int, str]] = []
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
        is_change = "changes" in path.parts and "specs" not in path.parts[path.parts.index("changes"):]
        if path.name == "diagrams.md" and is_change:
            problems += [(path, n, msg) for n, msg in check_change_structure(path, lines)]

    if args.render and to_render:
        problems += render_blocks(to_render)

    for path, line, msg in sorted(problems, key=lambda p: (str(p[0]), p[1])):
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        print(f"{shown}:{line}: {msg}")
    status = "FAIL" if problems else "OK"
    print(f"{status}: {len(files)} files, {block_count} mermaid blocks, {len(problems)} problems"
          + (" (rendered)" if args.render else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
