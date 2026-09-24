#!/usr/bin/env python3
"""Save and restore the parts of an OpenSpec/VSDD setup that git can't restore.

Git should own every tracked file: install on a branch, and undo by switching back.
This script covers the rest:

  - files in the install's footprint that git does NOT track, e.g. gitignored tool
    folders (.claude/, .opencode/ ...), untracked /opsx command files, openspec/
    in a project that doesn't commit it
  - your global OpenSpec config (profile, workflows, stores): `openspec config path`
  - the OpenSpec CLI version (recorded only - never reinstalled for you)

Footprint: openspec/, AGENTS.md, CLAUDE.md, docs/VSDD.md, docs/MERMAID_RULES.md,
scripts/vsdd/, .github/workflows/vsdd.yml, and any path inside a top-level
dot-folder whose name contains "openspec-" or "opsx" (skills and commands).

Snapshots live OUTSIDE the project (default ~/.vsdd-snapshots/<project>-<time>/),
so `git clean` or a reset can't delete them.

Usage (from the project root):
  python3 scripts/vsdd/vsdd_snapshot.py save
  python3 scripts/vsdd/vsdd_snapshot.py save --extra-dir ~/.minimax   # home-folder tools
  python3 scripts/vsdd/vsdd_snapshot.py latest                    # print newest snapshot dir
  python3 scripts/vsdd/vsdd_snapshot.py restore <dir> --dry-run   # show what would change
  python3 scripts/vsdd/vsdd_snapshot.py restore <dir> --yes       # restore untracked files
  python3 scripts/vsdd/vsdd_snapshot.py restore <dir> --yes --restore-global

Restore puts saved untracked files back and deletes untracked files in the footprint
that did not exist at save time. It never touches tracked files (use git), and only
replaces the global config with --restore-global.

Exit codes: 0 ok, 1 differences remain / nothing done without --yes, 2 bad invocation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

FOOTPRINT = ["openspec", "AGENTS.md", "CLAUDE.md", "docs/VSDD.md", "docs/MERMAID_RULES.md",
             "scripts/vsdd", ".github/workflows/vsdd.yml"]
SKIP_DIRS = {".git", "node_modules", ".dart_tool", "build", ".venv", "venv", "__pycache__"}
DEFAULT_HOME = Path.home() / ".vsdd-snapshots"


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def footprint_files(root: Path) -> set[str]:
    """Relative paths of regular files in the install footprint."""
    out: set[str] = set()

    def add_tree(base: Path) -> None:
        if base.is_file() and not base.is_symlink():
            out.add(base.relative_to(root).as_posix())
        elif base.is_dir():
            for p in base.rglob("*"):
                if p.is_file() and not p.is_symlink() and not (set(p.relative_to(root).parts) & SKIP_DIRS):
                    out.add(p.relative_to(root).as_posix())

    for rel in FOOTPRINT:
        add_tree(root / rel)
    for tool in root.iterdir():
        if tool.is_dir() and tool.name.startswith(".") and tool.name not in SKIP_DIRS:
            for p in tool.rglob("*"):
                rel = p.relative_to(root)
                if (p.is_file() and not p.is_symlink() and not (set(rel.parts) & SKIP_DIRS)
                        and any("openspec-" in part or "opsx" in part for part in rel.parts)):
                    out.add(rel.as_posix())
    return out


def extra_files(folder: Path) -> set[str]:
    """OpenSpec skill/command files in an extra (e.g. home-folder) tool folder."""
    if not folder.is_dir():
        return set()
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*")
            if p.is_file() and not p.is_symlink()
            and any("openspec-" in part or "opsx" in part for part in p.relative_to(folder).parts)}


def tracked_files(root: Path) -> set[str] | None:
    """Files git tracks, or None if root is not a git work tree."""
    proc = run(["git", "ls-files", "-z"], root)
    if proc.returncode != 0:
        return None
    return {p for p in proc.stdout.split("\0") if p}


def untracked_footprint(root: Path) -> set[str]:
    tracked = tracked_files(root) or set()
    return {p for p in footprint_files(root) if p not in tracked}


def global_config_path() -> Path | None:
    proc = run(["openspec", "config", "path"], Path.cwd())
    return Path(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else None


def cli_version() -> str | None:
    if shutil.which("openspec") is None:
        return None
    return run(["openspec", "--version"], Path.cwd()).stdout.strip() or None


def cmd_save(root: Path, out: Path | None, extra_dirs: list[Path]) -> int:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    snap = out or DEFAULT_HOME / f"{root.name}-{stamp}"
    if snap.exists():
        print(f"error: {snap} already exists", file=sys.stderr)
        return 2
    files_dir = snap / "files"
    files_dir.mkdir(parents=True)
    in_git = tracked_files(root) is not None
    saved = sorted(untracked_footprint(root))
    for rel in saved:
        dest = files_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dest)
    extras = []
    for i, folder in enumerate(extra_dirs):
        rels = sorted(extra_files(folder))
        for rel in rels:
            dest = snap / "extra" / str(i) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(folder / rel, dest)
        extras.append({"dir": str(folder), "files": {rel: sha256(folder / rel) for rel in rels}})
    gpath = global_config_path()
    global_info = {"path": str(gpath) if gpath else None, "existed": bool(gpath and gpath.is_file())}
    if global_info["existed"]:
        shutil.copy2(gpath, snap / "global-config.json")
        global_info["sha256"] = sha256(gpath)
    head = run(["git", "rev-parse", "--short", "HEAD"], root).stdout.strip() if in_git else None
    branch = run(["git", "branch", "--show-current"], root).stdout.strip() if in_git else None
    manifest = {
        "created": stamp, "root": str(root), "git": {"repo": in_git, "head": head, "branch": branch},
        "files": {rel: sha256(root / rel) for rel in saved},
        "global_config": global_info, "openspec_version": cli_version(), "extra_dirs": extras,
    }
    (snap / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Snapshot saved: {snap}")
    print(f"  untracked footprint files: {len(saved)}" + ("" if in_git else " (not a git repo: all footprint files)"))
    for e in extras:
        print(f"  extra folder:              {e['dir']} ({len(e['files'])} files)")
    print(f"  global OpenSpec config:    {gpath if global_info['existed'] else 'none'}")
    print(f"  OpenSpec CLI:              {manifest['openspec_version'] or 'not installed'}")
    if in_git:
        print(f"  git: {branch or '(detached)'} @ {head} - tracked files are restored with git, not this snapshot")
    return 0


def cmd_latest(root: Path) -> int:
    snaps = sorted(DEFAULT_HOME.glob(f"{root.name}-*"))
    snaps = [s for s in snaps if (s / "manifest.json").is_file()
             and json.loads((s / "manifest.json").read_text()).get("root") == str(root)]
    if not snaps:
        print(f"No snapshots for {root} in {DEFAULT_HOME}", file=sys.stderr)
        return 1
    print(snaps[-1])
    return 0


def cmd_restore(root: Path, snap: Path, yes: bool, dry_run: bool, restore_global: bool) -> int:
    manifest_path = snap / "manifest.json"
    if not manifest_path.is_file():
        print(f"error: {manifest_path} not found", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text())
    if manifest["root"] != str(root):
        print(f"warning: snapshot was taken of {manifest['root']}, restoring into {root}")
    apply = yes and not dry_run
    saved: dict[str, str] = manifest["files"]
    tracked = tracked_files(root) or set()

    to_write = [rel for rel, digest in saved.items()
                if not (root / rel).is_file() or sha256(root / rel) != digest]
    to_delete = sorted(untracked_footprint(root) - set(saved))
    skipped_tracked = sorted(rel for rel in to_write if rel in tracked)
    to_write = sorted(rel for rel in to_write if rel not in tracked)

    verb = "" if apply else "would "
    for rel in to_write:
        print(f"{verb}restore: {rel}")
        if apply:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snap / "files" / rel, root / rel)
    for rel in to_delete:
        print(f"{verb}delete (untracked, not in snapshot): {rel}")
        if apply:
            (root / rel).unlink()
    if apply:
        for rel in to_delete:  # tidy directories the deletions emptied
            parent = (root / rel).parent
            while parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    for rel in skipped_tracked:
        print(f"skipped (now tracked by git - restore it with git): {rel}")

    extra_changes = False
    for i, e in enumerate(manifest.get("extra_dirs", [])):
        folder = Path(e["dir"])
        want: dict[str, str] = e["files"]
        writes = sorted(r for r, d in want.items() if not (folder / r).is_file() or sha256(folder / r) != d)
        deletes = sorted(extra_files(folder) - set(want))
        extra_changes |= bool(writes or deletes)
        for rel in writes:
            print(f"{verb}restore: {folder / rel}")
            if apply:
                (folder / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snap / "extra" / str(i) / rel, folder / rel)
        for rel in deletes:
            print(f"{verb}delete (not in snapshot): {folder / rel}")
            if apply:
                (folder / rel).unlink()

    g = manifest["global_config"]
    gpath = Path(g["path"]) if g.get("path") else None
    global_differs = False
    if gpath:
        now_exists = gpath.is_file()
        if g["existed"]:
            global_differs = not now_exists or sha256(gpath) != g["sha256"]
        else:
            global_differs = now_exists
    if global_differs:
        if restore_global:
            print(f"{verb}restore global OpenSpec config: {gpath}")
            if apply:
                if g["existed"]:
                    gpath.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snap / "global-config.json", gpath)
                else:
                    gpath.unlink()
        else:
            print(f"global OpenSpec config differs from the snapshot: {gpath}")
            print("  (not restored - it is machine-wide; add --restore-global after confirming)")

    now_version = cli_version()
    if manifest.get("openspec_version") and now_version != manifest["openspec_version"]:
        print(f"OpenSpec CLI is {now_version or 'not installed'}, snapshot had {manifest['openspec_version']}.")
        print(f"  To go back: npm install -g @fission-ai/openspec@{manifest['openspec_version']}")

    git = manifest.get("git", {})
    if git.get("repo"):
        print(f"Tracked files: use git. The snapshot was taken on {git.get('branch') or '(detached)'} @ {git.get('head')}.")

    changes = bool(to_write or to_delete or extra_changes or (global_differs and restore_global))
    if not changes and not global_differs:
        print("Untracked footprint matches the snapshot - nothing to restore.")
        return 0
    if not apply:
        print("Nothing changed. Re-run with --yes to apply." if not dry_run else "Dry run: nothing changed.")
        return 1
    print("Restore complete.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save", help="save untracked footprint + global config")
    s.add_argument("--out", type=Path, help="snapshot directory (default ~/.vsdd-snapshots/<project>-<time>)")
    s.add_argument("--extra-dir", type=Path, action="append", default=[],
                   help="also save OpenSpec files in this folder (e.g. ~/.minimax). Repeatable")
    sub.add_parser("latest", help="print this project's newest snapshot directory")
    r = sub.add_parser("restore", help="restore a snapshot")
    r.add_argument("snapshot", type=Path)
    r.add_argument("--yes", action="store_true", help="actually change files (otherwise: report only)")
    r.add_argument("--dry-run", action="store_true", help="report only, even with --yes")
    r.add_argument("--restore-global", action="store_true", help="also restore the global OpenSpec config")
    args = ap.parse_args()
    root = args.root.resolve()
    if args.cmd == "save":
        return cmd_save(root, args.out.resolve() if args.out else None,
                        [d.expanduser().resolve() for d in args.extra_dir])
    if args.cmd == "latest":
        return cmd_latest(root)
    return cmd_restore(root, args.snapshot.resolve(), args.yes, args.dry_run, args.restore_global)


if __name__ == "__main__":
    sys.exit(main())
