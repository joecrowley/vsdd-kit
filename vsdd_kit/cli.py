"""`vsdd-kit`: run the kit without cloning it.

  uvx --from git+https://github.com/joecrowley/vsdd-kit@v0.2.0 vsdd-kit install --root . --tools claude

Each subcommand runs the kit script of the same job, with the same flags, so
everything SETUP.md says about a script applies to its subcommand:

  install    files/scripts/vsdd/vsdd_install.py
  status     files/scripts/vsdd/vsdd_install.py --status
  preflight  files/scripts/vsdd/openspec_preflight.py
  snapshot   files/scripts/vsdd/vsdd_snapshot.py
  validate   files/scripts/vsdd/validate_mermaid.py   (pass --root <project>)
  overlay    files/scripts/vsdd/install_overlay.py    (pass --root <project>)
  merge      files/scripts/vsdd/merge_diagrams.py     (pass --root <project>)
  guide      print SETUP.md (--reference: docs/SETUP-REFERENCE.md)
  path       print the kit folder: use it as KIT in SETUP.md

The package holds the kit laid out as in the repository (files/, SETUP.md, docs/,
VERSION), so `KIT=$(vsdd-kit path)` works with every command in SETUP.md.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Installed: the kit is inside the package. From a clone: the package sits in the kit.
KIT = HERE if (HERE / "files").is_dir() else HERE.parent
SCRIPTS = KIT / "files" / "scripts" / "vsdd"

COMMANDS = {
    "install": ("vsdd_install.py", []),
    "status": ("vsdd_install.py", ["--status"]),
    "preflight": ("openspec_preflight.py", []),
    "snapshot": ("vsdd_snapshot.py", []),
    # The project-side scripts, for projects that don't hold a copy (--tooling-dir),
    # e.g. in CI: `vsdd-kit validate --root . --render`.
    "validate": ("validate_mermaid.py", []),
    "overlay": ("install_overlay.py", []),
    "merge": ("merge_diagrams.py", []),
}


def version() -> str:
    return (KIT / "VERSION").read_text(encoding="utf-8").strip()


def run_script(name: str, extra: list[str], args: list[str], command: str) -> int:
    script = SCRIPTS / name
    # The scripts print commands to re-run (e.g. `status` prints the upgrade command):
    # name this entry point, not a file inside a temporary uvx environment.
    os.environ["VSDD_KIT_CLI"] = "vsdd-kit"
    sys.argv = [f"vsdd-kit {command}", *extra, *args]
    sys.path.insert(0, str(SCRIPTS))
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        if isinstance(e.code, str):  # what Python itself does with a message
            print(e.code, file=sys.stderr)
            return 1
        return e.code or 0
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    command, args = argv[0], argv[1:]
    if command in ("-V", "--version", "version"):
        print(f"vsdd-kit {version()}")
        return 0
    if command == "path":
        print(KIT)
        return 0
    if command == "guide":
        doc = KIT / ("docs/SETUP-REFERENCE.md" if "--reference" in args else "SETUP.md")
        print(doc.read_text(encoding="utf-8"), end="")
        return 0
    if command in COMMANDS:
        name, extra = COMMANDS[command]
        return run_script(name, extra, args, command)
    print(f"vsdd-kit: unknown command '{command}'. Run `vsdd-kit --help`.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
