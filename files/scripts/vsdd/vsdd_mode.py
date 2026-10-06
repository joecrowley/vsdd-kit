#!/usr/bin/env python3
"""Show or set the VSDD mode: full, light or sketch.

  full   schema `visual-driven`: diagrams.md is planned at propose (Before/After), the
         user can review it before apply, and apply traces it against the code
  light  schema `visual-driven-light`: no diagrams at propose; the last apply task
         writes diagrams.md from the code as built, for review before archiving
  sketch schema `visual-driven-sketch` (experimental): propose writes the planned diagram
         changes in words (Placement + Planned Changes), for review before apply; the
         last apply task draws the Before/After from the code as built

The project default is the `schema:` line of openspec/config.yaml; a new change takes it
unless it is created with `openspec new change <name> --schema <schema>`. Each change
keeps the schema it was created with (its .openspec.yaml), so setting the default never
changes a change already in flight.

Usage:
  python3 scripts/vsdd/vsdd_mode.py            # show the default and each change's mode
  python3 scripts/vsdd/vsdd_mode.py light      # make light the default for new changes
  python3 scripts/vsdd/vsdd_mode.py full       # make full the default for new changes
  python3 scripts/vsdd/vsdd_mode.py sketch     # make sketch the default for new changes

Exit code 0 = ok, 1 = the project has no config.yaml or uses another schema, 2 = bad invocation.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from openspec_preflight import configured_schema, in_flight_changes  # noqa: E402

MODES = {"full": "visual-driven", "light": "visual-driven-light", "sketch": "visual-driven-sketch"}
NAMES = {v: k for k, v in MODES.items()}


def config_path(root: Path) -> Path | None:
    for name in ("config.yaml", "config.yml"):
        if (root / "openspec" / name).is_file():
            return root / "openspec" / name
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", nargs="?", choices=sorted(MODES), help="set the project default")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: cwd)")
    args = parser.parse_args()
    root = args.root.resolve()
    path = config_path(root)
    if path is None:
        print(f"no openspec/config.yaml in {root}")
        return 1
    schema = configured_schema(root)
    if schema not in NAMES:
        print(f"the project's schema is {schema or '(none)'}, not a VSDD one ({', '.join(MODES.values())})")
        return 1
    if args.mode:
        if MODES[args.mode] == schema:
            print(f"default mode is already {args.mode} ({schema})")
        else:
            text = path.read_text(encoding="utf-8")
            path.write_text(re.sub(r"^schema:.*$", f"schema: {MODES[args.mode]}", text, count=1, flags=re.M),
                            encoding="utf-8")
            print(f"default mode: {NAMES[schema]} -> {args.mode} ({MODES[args.mode]}). "
                  "Changes already in flight keep their own mode.")
            schema = MODES[args.mode]
    else:
        print(f"Default mode (new changes): {NAMES[schema]} ({schema})")
    for name, s in in_flight_changes(root):
        print(f"  {name}: {NAMES.get(s, 'not VSDD')} ({s})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
