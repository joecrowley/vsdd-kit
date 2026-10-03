#!/usr/bin/env python3
"""Fill a change's `## Before State` from its Placement table, verbatim.

For every update, move and remove row, the `## <Stable Name>` section is copied from the
Source of Truth file the row names (for a move, the old file) as `### <Stable Name>`, in
Placement order. Whatever `## Before State` held is replaced; if the change has no
`## Before State` yet, one is added before `## After State` (or at the end). Run it after
writing the Placement table and before writing the After State.

It also reports drift for exactly the sections it copied: code-like names that no source
file contains (the same check as validate_mermaid.py). Drift does not stop the copy - a
stale section is still copied as it is; record it in `## Source of Truth drift`.

Usage:
  python3 scripts/vsdd/seed_before.py <change name or folder> [--root DIR] [--dry-run] [--no-names]

Exit code 0 = done (drift is only reported), 1 = a row's file or section is missing or
the Placement table is invalid, 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_mermaid import (  # noqa: E402
    _parse_placement, _section_body, _sections, change_file, code_names, extract_blocks,
    gate_is_yes, source_identifiers,
)


def seed(lines: list[str], sections: list[tuple[str, str]]) -> list[str]:
    """Replace (or add) `## Before State` with the given (name, body) sections."""
    block = ["## Before State", ""]
    for name, body in sections:
        block += [f"### {name}", "", *body.splitlines(), ""]
    h2 = [(n, ln) for n, ln, _ in _sections(lines, "##")]
    before = next((ln for n, ln in h2 if n == "Before State"), None)
    if before is not None:
        end = min((ln for _, ln in h2 if ln > before), default=len(lines) + 1)
        return lines[:before - 1] + block + lines[end - 1:]
    after = next((ln for n, ln in h2 if n == "After State"), None)
    if after is not None:
        return lines[:after - 1] + block + lines[after - 1:]
    return lines + ([""] if lines and lines[-1].strip() else []) + block


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("change", help="change name (openspec/changes/<name>) or its folder")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: cwd)")
    parser.add_argument("--dry-run", action="store_true", help="print the Before State instead of writing it")
    parser.add_argument("--no-names", action="store_true", help="skip the drift report")
    args = parser.parse_args()

    root = args.root.resolve()
    path = change_file(root, args.change)
    lines = path.read_text(encoding="utf-8").splitlines()
    if not gate_is_yes(lines):
        print(f"{path.relative_to(root)}: the gate is not YES - no Before State to seed")
        return 0
    body = next((b for n, _, b in _sections(lines, "##") if n == "Placement"), None)
    if body is None:
        print("error: write the ## Placement table first", file=sys.stderr)
        return 1
    rows, errors = _parse_placement(body)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    copied: list[tuple[str, str, str]] = []  # (name, source file, body)
    for name, target, action, move_from in rows:
        if action == "add":
            continue
        source = move_from if action == "move" else target
        text = _section_body(root, source, name)
        if text is None:
            errors.append(f"'{name}' ({action}): no '## {name}' in openspec/{source}")
            print(f"error: {errors[-1]}", file=sys.stderr)
            continue
        copied.append((name, source, text))
    if errors:
        return 1

    new = seed(lines, [(n, b) for n, _, b in copied])
    if args.dry_run:
        print("\n".join(new[next(i for i, l in enumerate(new) if l == "## Before State"):]).split("\n## ", 1)[0])
    else:
        path.write_text("\n".join(new) + "\n", encoding="utf-8")
        print(f"seeded Before State: {len(copied)} section(s)"
              + (f" from {', '.join(sorted({f'openspec/{s}' for _, s, _ in copied}))}" if copied else ""))

    if not args.no_names and copied:
        known, n_sources = source_identifiers(root)
        if n_sources:
            for name, source, text in copied:
                names = set()
                for _, block in extract_blocks(text.splitlines())[0]:
                    names |= code_names(block)[0]
                missing = sorted(n for n in names if n not in known)
                if missing:
                    print(f"warning: drift in '{name}' (openspec/{source}): {', '.join(missing)} not found in "
                          "the project's code. Read the code behind it; record what the diagram says and "
                          "what the code does under ## Source of Truth drift, and make the After match the code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
