#!/usr/bin/env python3
"""Write one browsable page of every Source of Truth diagram: docs/DIAGRAMS.md.

Collects every `## <Stable Name>` section of `openspec/specs/**/diagrams.md`
(architecture first, then each capability) with its prose and Mermaid block, and adds:
  - per capability: the `## Purpose` of its spec.md and links to spec.md and diagrams.md
  - per diagram: its kind, a link to the source file that declares each code-like name
    in it (only where exactly one file does; names no source file contains are marked,
    like the validator's drift warning), and the other diagrams that show the same names
  - an index of the names that appear in more than one diagram
Names that appear in more than a third of the diagrams (`emit`, a shared base class)
link everything to everything, so they are left out of the cross-links and the index.

The page is generated: edit the diagrams.md files, then run this again. The only part
kept between runs is the block between `<!-- vsdd:overview -->` and
`<!-- /vsdd:overview -->`, where an agent or a person can write an overview by hand.
The page records a hash of the files it was built from; `--check` (and
validate_mermaid.py, as a warning) reports when those files changed since.

Usage:
  python3 scripts/vsdd/catalog_diagrams.py [--root DIR] [--out docs/DIAGRAMS.md]
  python3 scripts/vsdd/catalog_diagrams.py --check     # exit 1 if the page is out of date
  python3 scripts/vsdd/catalog_diagrams.py --no-code   # skip the source lookup (faster)

Exit code 0 = written (or up to date), 1 = out of date (--check), 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_mermaid import _sections, code_names, extract_blocks, ranked_locations  # noqa: E402

DEFAULT_OUT = Path("docs") / "DIAGRAMS.md"
OVERVIEW_START, OVERVIEW_END = "<!-- vsdd:overview -->", "<!-- /vsdd:overview -->"
SOURCE_RE = re.compile(r"<!-- vsdd:catalog-source ([0-9a-f]{16}) -->")
KINDS = {"sequenceDiagram": "sequence", "stateDiagram": "state machine", "stateDiagram-v2": "state machine",
         "flowchart": "flowchart", "graph": "flowchart", "classDiagram": "class diagram",
         "erDiagram": "entity relationship", "C4Context": "C4 context", "C4Container": "C4 container",
         "C4Component": "C4 component"}


def diagram_files(root: Path) -> list[Path]:
    """Source of Truth diagrams.md files: architecture first, then capabilities by name."""
    base = root / "openspec" / "specs"
    files = sorted(base.rglob("diagrams.md")) if base.is_dir() else []
    return sorted(files, key=lambda p: (p.parent.name != "architecture", str(p.relative_to(base))))


def inputs(root: Path) -> list[Path]:
    """Every file the page is built from (diagrams and the specs next to them)."""
    out = []
    for path in diagram_files(root):
        out.append(path)
        if (path.parent / "spec.md").is_file():
            out.append(path.parent / "spec.md")
    return out


def source_hash(root: Path) -> str:
    h = hashlib.sha256()
    for path in inputs(root):
        h.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def recorded_hash(page: Path) -> str | None:
    if not page.is_file():
        return None
    m = SOURCE_RE.search(page.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def stale(root: Path, page: Path) -> bool:
    """True when the page exists and the files it was built from have changed since."""
    rec = recorded_hash(page)
    return rec is not None and rec != source_hash(root)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def purpose(spec: Path) -> str | None:
    if not spec.is_file():
        return None
    for name, _, body in _sections(spec.read_text(encoding="utf-8").splitlines(), "##"):
        if name.lower() == "purpose":
            para = body.split("\n\n")[0].strip()
            return " ".join(para.split()) or None
    return None


def file_title_and_intro(lines: list[str]) -> tuple[str | None, str]:
    title, intro = None, []
    for line in lines:
        if line.startswith("## "):
            break
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
        elif title is not None:
            intro.append(line)
    return title, "\n".join(intro).strip()


def demote(body: str) -> str:
    """Push headings inside a section down two levels so they sit under the page's ###."""
    out, fence = [], False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
        out.append("##" + line if not fence and line.startswith("#") else line)
    return "\n".join(out)


def kind(block: list[str]) -> str:
    for line in block:
        s = line.strip()
        if s and not s.startswith("%%"):
            return KINDS.get(s.split()[0], s.split()[0])
    return "diagram"


def collect(root: Path) -> list[dict]:
    """One entry per diagrams.md file, with its sections."""
    out = []
    for path in diagram_files(root):
        lines = path.read_text(encoding="utf-8").splitlines()
        title, intro = file_title_and_intro(lines)
        cap = path.parent.relative_to(root / "openspec" / "specs").as_posix()
        sections = []
        for name, _, body in _sections(lines, "##"):
            blocks, _ = extract_blocks(body.splitlines())
            names: set[str] = set()
            for _, block in blocks:
                names |= code_names(block)[0]
            sections.append({"name": name, "body": body, "names": names,
                             "kind": ", ".join(dict.fromkeys(kind(b) for _, b in blocks)) or "text",
                             "anchor": f"{slug(cap)}--{slug(name)}"})
        out.append({"cap": cap, "path": path, "title": title or f"{cap} diagrams", "intro": intro,
                    "purpose": purpose(path.parent / "spec.md"),
                    "spec": path.parent / "spec.md" if (path.parent / "spec.md").is_file() else None,
                    "sections": sections})
    return out


def rel(target: Path, page: Path) -> str:
    return Path(os.path.relpath(target, page.parent)).as_posix()


def render(root: Path, page: Path, files: list[dict], overview: str | None, with_code: bool) -> str:
    sections = [(f, s) for f in files for s in f["sections"]]
    where: dict[str, list[tuple[dict, dict]]] = {}
    for f, s in sections:
        for n in s["names"]:
            where.setdefault(n, []).append((f, s))
    locs = ranked_locations(root, set(where)) if with_code and where else {}
    common = {n for n, v in where.items() if len(sections) >= 6 and len({id(s) for _, s in v}) * 3 > len(sections)}
    out = [
        "# Diagrams",
        "",
        "<!-- Generated by scripts/vsdd/catalog_diagrams.py from openspec/specs/**/diagrams.md. "
        "Don't edit it: edit those files and run the script again. Only the overview block "
        "below is kept between runs. -->",
        f"<!-- vsdd:catalog-source {source_hash(root)} -->",
        "",
        f"Every Source of Truth diagram in one page: {len(sections)} diagrams in {len(files)} "
        f"files under `openspec/specs/`. Each section comes from a `diagrams.md` file; the links "
        "next to it lead to that file, the capability's spec, and the code the diagram names.",
        "",
        OVERVIEW_START,
        overview.strip() if overview and overview.strip() else
        "_No overview yet. An agent or a person can write one here: how the areas below fit "
        "together, in a few paragraphs. It is kept when the page is regenerated._",
        OVERVIEW_END,
        "",
        "## Contents",
        "",
    ]
    for f in files:
        out.append(f"- [{f['title']}](#{slug(f['cap'])})")
        out += [f"  - [{s['name']}](#{s['anchor']}) ({s['kind']})" for s in f["sections"]]
    for f in files:
        links = [f"[diagrams.md]({rel(f['path'], page)})"]
        if f["spec"]:
            links.append(f"[spec.md]({rel(f['spec'], page)})")
        out += ["", f'<a id="{slug(f["cap"])}"></a>', "", f"## {f['title']}", "",
                f"`{f['cap']}` · " + " · ".join(links), ""]
        if f["purpose"]:
            out += [f"**Purpose:** {f['purpose']}", ""]
        if f["intro"]:
            out += [f["intro"], ""]
        for s in f["sections"]:
            out += [f'<a id="{s["anchor"]}"></a>', "", f"### {s['name']}", "", demote(s["body"]), ""]
            if s["names"] and with_code:
                parts = []
                for n in sorted(s["names"], key=str.lower):
                    found = locs.get(n) or []
                    declared = [p for r, p in found if r == 0]
                    if len(declared) == 1:
                        parts.append(f"[`{n}`]({rel(root / declared[0], page)})")
                    elif not found:
                        parts.append(f"`{n}` (not found in the code)")
                if parts:
                    out += ["**In the code:** " + ", ".join(parts), ""]
            shared: dict[str, tuple[dict, dict, list[str]]] = {}
            for n in s["names"] - common:
                for of, os_ in where[n]:
                    if os_ is not s:
                        shared.setdefault(os_["anchor"], (of, os_, []))[2].append(n)
            if shared:
                links = [f"[{os_['name']}](#{a}) ({', '.join(f'`{n}`' for n in sorted(ns, key=str.lower))})"
                         for a, (of, os_, ns) in sorted(shared.items(), key=lambda kv: kv[1][1]["name"].lower())]
                out += ["**Also shown in:** " + "; ".join(links), ""]
    multi = {n: v for n, v in where.items() if n not in common and len({id(s) for _, s in v}) > 1}
    if multi:
        out += ["## Names in more than one diagram", "", "| Name | Diagrams |", "|---|---|"]
        for n in sorted(multi, key=str.lower):
            seen = dict.fromkeys(s["anchor"] for _, s in multi[n])
            names = {s["anchor"]: s["name"] for _, s in multi[n]}
            out.append(f"| `{n}` | " + ", ".join(f"[{names[a]}](#{a})" for a in seen) + " |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def existing_overview(page: Path) -> str | None:
    if not page.is_file():
        return None
    text = page.read_text(encoding="utf-8")
    i, j = text.find(OVERVIEW_START), text.find(OVERVIEW_END)
    if i < 0 or j < i:
        return None
    body = text[i + len(OVERVIEW_START):j].strip()
    return None if body.startswith("_No overview yet.") else body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: cwd)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="page to write, relative to the root "
                        f"(default: {DEFAULT_OUT})")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if the page is missing or out of date")
    parser.add_argument("--no-code", action="store_true", help="skip linking names to source files")
    args = parser.parse_args()
    root = args.root.resolve()
    page = args.out if args.out.is_absolute() else root / args.out
    files = collect(root)
    if not files:
        print("no openspec/specs/**/diagrams.md files - nothing to catalogue")
        return 0
    if args.check:
        if not page.is_file():
            print(f"{page.relative_to(root)} does not exist - run catalog_diagrams.py")
            return 1
        if stale(root, page) or recorded_hash(page) is None:
            print(f"{page.relative_to(root)} is out of date: the diagrams or specs changed - run catalog_diagrams.py")
            return 1
        print(f"{page.relative_to(root)} is up to date")
        return 0
    text = render(root, page, files, existing_overview(page), not args.no_code)
    page.parent.mkdir(parents=True, exist_ok=True)
    old = page.read_text(encoding="utf-8") if page.is_file() else None
    if old != text:
        page.write_text(text, encoding="utf-8")
    n = sum(len(f["sections"]) for f in files)
    print(f"{'wrote' if old != text else 'unchanged:'} {page.relative_to(root)} "
          f"({n} diagrams from {len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
