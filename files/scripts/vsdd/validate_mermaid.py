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
    (checked for active changes only - archived ones describe an older state - and
    skipped for a change that is already merged but not yet moved to the archive)
  - a row that adds or moves a diagram INTO specs/architecture/diagrams.md has a
    4th column, `Why here`, saying why it spans capabilities

Source of Truth drift (openspec/specs/**/diagrams.md; warnings unless --names-strict):
  - every code-like name in a diagram (CamelCase, snake_case, or followed by "(") must
    appear somewhere in the project's source files; a missing one was probably renamed
    or removed. Labels that are not code go on a `%% vsdd:not-code <names>` line in the
    diagram. Skipped when the project has no source files.

Decisions log (openspec/specs/**/decisions.md):
  - every `## <Stable Name>` entry has **Rule:**, **Why:** and **Source:** lines
  - warning: a Source that isn't a dated archive folder name (2026-01-15-fix-x) or `install`

Catalogue (warning): docs/DIAGRAMS.md, if the project has one, was generated from the
current diagrams and specs (catalog_diagrams.py records a hash of them).

Ownership warnings (active changes; printed, but they don't fail the run):
  - the change creates a capability (it has specs/<cap>/ and openspec/specs/<cap>/
    doesn't exist yet) and still adds or moves a diagram into the architecture file

One change (--change <name>): that change's diagrams.md, and the drift check limited to
the Source of Truth sections its Placement rows name.

Trace (--trace <name>, at the end of apply): everything --change does, plus every
code-like name in the change's After State is looked up in the source files. Names no
file contains fail the run; the others are listed with the files that mention them, so
only "is it on the call path?" is left to check by reading code.

Usage:
  python3 scripts/vsdd/validate_mermaid.py                 # openspec/specs + active changes
  python3 scripts/vsdd/validate_mermaid.py --render        # plus mmdc parse
  python3 scripts/vsdd/validate_mermaid.py --include-archive
  python3 scripts/vsdd/validate_mermaid.py --names-strict   # drift in the Source of Truth fails the run
  python3 scripts/vsdd/validate_mermaid.py --change <name>  # one change (a name or its folder)
  python3 scripts/vsdd/validate_mermaid.py --trace <name>   # one change + After State traced against the code
  python3 scripts/vsdd/validate_mermaid.py path/to/file.md ...   # files, or change folders

Exit code 0 = clean, 1 = errors found, 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import json
import os
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


SOURCE_EXTS = {".dart", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".java", ".kt", ".kts",
               ".swift", ".go", ".rb", ".cs", ".php", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp",
               ".m", ".mm", ".scala", ".ex", ".exs", ".vue", ".svelte"}
SKIP_DIRS = {"openspec", "node_modules", "build", "dist", "out", "target", "vendor", "Pods",
             "coverage", "__pycache__", "venv", "env"}
MERMAID_WORDS = {"sequenceDiagram", "stateDiagram", "erDiagram", "classDiagram", "flowchart",
                 "graph", "gantt", "mindmap", "journey", "gitGraph", "quadrantChart", "timeline",
                 "requirementDiagram", "xychart", "sankey", "classDef", "linkStyle", "subgraph"}
NOT_CODE_RE = re.compile(r"^\s*%%\s*vsdd:not-code\s+(.*)$")
IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def source_identifiers(root: Path) -> tuple[set[str], int]:
    """Every identifier-like word in the project's source files (definitions, uses,
    import paths). Skips hidden folders, build output, openspec/ and the kit's own
    scripts/vsdd/. Returns (words, number of files read)."""
    words: set[str] = set()
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root).parts
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
                       and not (rel == ("scripts",) and d == "vsdd")]
        for name in filenames:
            if Path(name).suffix in SOURCE_EXTS:
                try:
                    words |= set(IDENT_RE.findall((Path(dirpath) / name).read_text(encoding="utf-8", errors="ignore")))
                    count += 1
                except OSError:
                    pass
    return words, count


def code_names(block: list[str]) -> tuple[set[str], set[str]]:
    """(code-like names used in a diagram, names its `%% vsdd:not-code` lines exempt)."""
    exempt: set[str] = set()
    text = []
    for line in block:
        m = NOT_CODE_RE.match(line)
        if m:
            exempt |= set(IDENT_RE.findall(m.group(1)))
        elif not line.strip().startswith("%%"):
            text.append(line)
    body = "\n".join(text)
    names = set()
    for tok in IDENT_RE.findall(body):
        if tok in MERMAID_WORDS or tok.isupper() or len(tok) < 3:
            continue
        camel = re.search(r"[a-z][A-Z]", tok) or re.match(r"^[A-Z][a-z0-9]+[A-Z]", tok)
        snake = "_" in tok.strip("_") and not tok.isupper()
        if camel or snake:
            names.add(tok)
    names |= {t for t in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\(", body) if len(t) >= 3}
    return names - exempt, exempt


def name_locations(root: Path, names: set[str]) -> dict[str, list[str]]:
    """{name: project-relative source files that mention it} for the given names, walking
    the same files as source_identifiers. Files that appear to declare the name come
    first, then other files, then test files."""
    return {n: [p for _, p in v] for n, v in ranked_locations(root, names).items()}


def ranked_locations(root: Path, names: set[str]) -> dict[str, list[tuple[int, str]]]:
    """As name_locations, with each file's rank: 0 = appears to declare the name (not a
    test), 1 = mentions it, 2 = a test file."""
    ranked: dict[str, list[tuple[int, str]]] = {n: [] for n in names}
    if not names:
        return {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root).parts
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
                             and not (rel == ("scripts",) and d == "vsdd"))
        for name in sorted(filenames):
            if Path(name).suffix in SOURCE_EXTS:
                path = Path(dirpath) / name
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                rel_path = str(path.relative_to(root))
                is_test = bool(re.search(r"(^|/)(tests?|spec|__tests__)/|_test\.|\.test\.|_spec\.|\.spec\.", rel_path))
                for n in names & set(IDENT_RE.findall(text)):
                    declares = re.search(
                        rf"\b(class|interface|mixin|enum|typedef|struct|trait|protocol|type|def|func|fun|fn|function)\s+{n}\b"
                        rf"|^[ \t]*(?:[\w<>?,\[\]]+[ \t]+)+{n}[ \t]*(?:<[^>\n]*>)?[ \t]*\((?:[^;\n]*\)[ \t]*(?:async\*?|=>|\{{)|[ \t]*\{{?[ \t]*$)",
                        text, re.M)
                    ranked[n].append((0 if declares and not is_test else 2 if is_test else 1, rel_path))
    return {n: sorted(v) for n, v in ranked.items()}


def drift_warnings(lines: list[str], known: set[str], only: set[str] | None = None) -> list[tuple[int, str]]:
    """Names in a Source of Truth diagram that no longer appear in the project's code.
    With `only`, just the `## <Stable Name>` sections it names."""
    heads = [(ln, n) for n, ln, _ in _sections(lines, "##")]
    blocks, _ = extract_blocks(lines)
    out = []
    for start, block in blocks:
        section = next((n for ln, n in reversed(heads) if ln < start), "?")
        if only is not None and section not in only:
            continue
        names, _ = code_names(block)
        missing = sorted(n for n in names if n not in known)
        if missing:
            out.append((start, f"'{section}': {', '.join(missing)} not found in the project's code "
                        "(renamed or removed?). Check the section against the code; if a name is "
                        "not code, list it on a `%% vsdd:not-code <names>` line in the diagram"))
    return out


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


def _section_body(root: Path, rel: str, name: str) -> str | None:
    """Body of `## name` in openspec/<rel>, or None if the file or section is missing."""
    path = root / "openspec" / rel
    if not path.is_file():
        return None
    for n, _, body in _sections(path.read_text(encoding="utf-8").splitlines(), "##"):
        if n == name:
            return body
    return None


def already_merged(lines: list[str], root: Path) -> bool:
    """True when every Placement row of a change is already reflected in the Source of Truth:
    the archive merge has run, but the change may not have been moved to the archive yet."""
    h2 = {n: (ln, body) for n, ln, body in _sections(lines, "##")}
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


def change_file(root: Path, arg: str | Path) -> Path:
    """A change's diagrams.md from a change name, a change folder or the file itself."""
    p = Path(arg)
    if not p.exists() and not p.is_absolute():
        named = root / "openspec" / "changes" / str(arg)
        p = named if named.exists() else p
    if p.is_dir():
        p = p / "diagrams.md"
    if not p.is_file():
        raise SystemExit(f"error: no diagrams.md for change '{arg}' (looked for {p})")
    return p.resolve()


def gate_is_yes(lines: list[str]) -> bool:
    h2 = {n: body for n, _, body in _sections(lines, "##")}
    gate = next((l for l in h2.get("Diagram needed?", "").splitlines()
                 if l.strip() and not l.strip().startswith("<!--")), "")
    m = GATE_RE.match(gate)
    return bool(m and m.group(1).upper() == "YES")


def placement_rows(lines: list[str]) -> list[tuple[str, str, str, str | None]]:
    """The change's valid Placement rows (invalid rows are reported by the structure check)."""
    body = next((b for n, _, b in _sections(lines, "##") if n == "Placement"), "")
    return _parse_placement(body)[0]


def after_sections(lines: list[str]) -> list[tuple[str, int, list[str]]]:
    """(stable name, heading line, lines) for each `### <Stable Name>` under `## After State`."""
    h2 = [(n, ln) for n, ln, _ in _sections(lines, "##")]
    start = next((ln for n, ln in h2 if n == "After State"), None)
    if start is None:
        return []
    end = min((ln for _, ln in h2 if ln > start), default=len(lines) + 1)
    h3 = [(n, ln) for n, ln, _ in _sections(lines, "###") if start < ln < end]
    out = []
    for i, (name, ln) in enumerate(h3):
        stop = h3[i + 1][1] if i + 1 < len(h3) else end
        out.append((name, ln, lines[ln:stop - 1]))
    return out


def trace_change(path: Path, lines: list[str], root: Path) -> tuple[list[tuple[int, str]], list[str]]:
    """Look up every code-like name in the change's After State in the project's source
    files. Returns (problems: names no source file contains, report lines)."""
    if not gate_is_yes(lines):
        return [], ["trace: the gate is NO, nothing to trace"]
    sections = []
    for name, ln, body in after_sections(lines):
        names = set()
        for _, block in extract_blocks(body)[0]:
            names |= code_names(block)[0]
        sections.append((name, ln, names))
    where = name_locations(root, set().union(*(n for _, _, n in sections)) if sections else set())
    problems, report = [], []
    for name, ln, names in sections:
        missing = sorted(n for n in names if not where[n])
        if missing:
            problems.append((ln, f"trace '{name}': {', '.join(missing)} not found in any source file. "
                             "Build it, or update the After State to what was built and record it under "
                             "## Deviations; label text that is not code goes on a `%% vsdd:not-code` line"))
        found = sorted(n for n in names if where[n])
        if found:
            shown = [f"{n} ({', '.join(where[n][:2])}{f', +{len(where[n]) - 2} more' if len(where[n]) > 2 else ''})"
                     for n in found]
            report.append(f"trace '{name}': " + "; ".join(shown))
        elif not missing:
            report.append(f"trace '{name}': no code-like names")
    return problems, report


DECISION_FIELDS = ("Rule", "Why", "Source")


def check_decisions(lines: list[str]) -> list[tuple[int, str]]:
    """Each `## <Stable Name>` entry of a decisions log needs Rule, Why and Source."""
    errors = []
    for name, line_no, body in _sections(lines, "##"):
        missing = [f for f in DECISION_FIELDS if not re.search(rf"\*\*{f}:\*\*\s*\S", body)]
        if missing:
            errors.append((line_no, f"decision '{name}' needs {', '.join(f'**{f}:**' for f in missing)}"))
    return errors


SOURCE_RE = re.compile(r"^(install|\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*)$")


def decision_warnings(lines: list[str]) -> list[tuple[int, str]]:
    """A decision's **Source:** names archived changes by their dated folder name
    (2026-01-15-fix-detail-flicker), or `install`, so the entry can be traced back."""
    warnings = []
    for name, line_no, body in _sections(lines, "##"):
        m = re.search(r"\*\*Source:\*\*\s*(.+)", body)
        if not m:
            continue
        bad = [s for s in (p.strip().strip("`") for p in m.group(1).split(",")) if s and not SOURCE_RE.match(s)]
        if bad:
            warnings.append((line_no, f"decision '{name}': Source {', '.join(bad)} should be the archived "
                             "change folder name, with its date (e.g. 2026-01-15-fix-detail-flicker), or 'install'"))
    return warnings


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
    parser.add_argument("--names-strict", action="store_true",
                        help="fail (not just warn) when a Source of Truth diagram names something the code no longer has")
    parser.add_argument("--no-names", action="store_true", help="skip the Source of Truth drift check")
    parser.add_argument("--strict-archive", action="store_true",
                        help="also apply the change-structure checks to archived changes (older ones predate Placement)")
    parser.add_argument("--change", metavar="NAME",
                        help="check one change (name or folder) and only the Source of Truth sections its Placement names")
    parser.add_argument("--trace", metavar="NAME",
                        help="as --change, then look up every code-like name in its After State in the source files")
    args = parser.parse_args()

    root = args.root.resolve()
    scope: dict[Path, set[str]] | None = None  # Source of Truth file -> sections to drift-check
    if args.change or args.trace:
        change = change_file(root, args.change or args.trace)
        scope = {}
        for name, target, action, move_from in placement_rows(change.read_text(encoding="utf-8").splitlines()):
            if action != "add":
                scope.setdefault((root / "openspec" / (move_from or target)).resolve(), set()).add(name)
        files = [change] + sorted(p for p in scope if p.is_file())
    elif args.paths:
        files = [(p / "diagrams.md" if p.is_dir() else p).resolve() for p in args.paths]
    else:
        files = find_files(root, args.include_archive)
    problems: list[tuple[Path, int, str]] = []
    warnings: list[tuple[Path, int, str]] = []
    report: list[str] = []
    to_render: list[tuple[Path, int, list[str]]] = []
    block_count = 0
    known, n_sources = (set(), 0) if args.no_names or (scope is not None and not scope) else source_identifiers(root)

    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        blocks, unclosed = extract_blocks(lines)
        block_count += len(blocks)
        problems += [(path, n, "unclosed ```mermaid fence") for n in unclosed]
        for start, block in blocks:
            problems += [(path, n, msg) for n, msg in lint_block(start, block)]
            to_render.append((path, start, block))
        in_specs = "specs" in path.parts and "changes" not in path.parts
        if path.name == "diagrams.md" and in_specs and n_sources:
            only = scope.get(path) if scope is not None else None
            found = [(path, n, msg) for n, msg in drift_warnings(lines, known, only)]
            if args.names_strict:
                problems += found
            else:
                warnings += found
        if path.name == "decisions.md" and "specs" in path.parts and "changes" not in path.parts:
            problems += [(path, n, msg) for n, msg in check_decisions(lines)]
            warnings += [(path, n, msg) for n, msg in decision_warnings(lines)]
        is_change = "changes" in path.parts and "specs" not in path.parts[path.parts.index("changes"):]
        if path.name == "diagrams.md" and is_change:
            archived = "archive" in path.parts[path.parts.index("changes"):]
            if not (archived and args.include_archive and not args.strict_archive):
                # After the archive merge, and before the move, the Before copies no longer match
                # the Source of Truth by design: skip that check for an already-merged change.
                verify_before = not archived and not already_merged(lines, root)
                problems += [(path, n, msg) for n, msg in check_change_structure(path, lines, root, verify_before)]
            if not archived:
                warnings += [(path, n, msg) for n, msg in ownership_warnings(path, lines, root)]
            if args.trace and not archived:
                found, report = trace_change(path, lines, root)
                problems += [(path, n, msg) for n, msg in found]

    if args.render and to_render:
        problems += render_blocks(to_render)
    if scope is None and not args.paths:
        # The one-page catalogue (catalog_diagrams.py), if the project has one.
        try:
            from catalog_diagrams import DEFAULT_OUT, stale
        except ImportError:
            stale = None
        if stale is not None and stale(root, root / DEFAULT_OUT):
            warnings.append((root / DEFAULT_OUT, 1, "out of date: the diagrams or specs changed since it was "
                             "generated - run python3 scripts/vsdd/catalog_diagrams.py"))

    def show(path: Path) -> Path:
        try:
            return path.relative_to(root)
        except ValueError:
            return path

    for path, line, msg in sorted(problems, key=lambda p: (str(p[0]), p[1])):
        print(f"{show(path)}:{line}: {msg}")
    for path, line, msg in sorted(warnings, key=lambda p: (str(p[0]), p[1])):
        print(f"{show(path)}:{line}: warning: {msg}")
    for line in report:
        print(line)
    status = "FAIL" if problems else "OK"
    print(f"{status}: {len(files)} files, {block_count} mermaid blocks, {len(problems)} problems"
          + (f", {len(warnings)} warnings" if warnings else "")
          + (" (rendered)" if args.render else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
