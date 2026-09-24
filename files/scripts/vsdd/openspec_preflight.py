#!/usr/bin/env python3
"""Inspect an existing OpenSpec setup before installing or upgrading VSDD.

Reports, for the project at --root:
  - whether OpenSpec is initialised, and the configured schema (flags custom schemas)
  - which AI-tool folders hold OpenSpec skills, and which workflows each has
  - which workflows `openspec update` would DELETE: those installed in the project
    but missing from your global OpenSpec profile. This is found by running
    `openspec init` in a throwaway folder with your real config, so it is exact for
    the installed CLI version.
  - requested tools (--tools) that are not set up yet: add them with
    `openspec init --tools <tool>`, which leaves other tools and config.yaml alone
  - in-flight changes and their schema (changes made before VSDD keep their schema)

--safe-update runs `openspec update` with a temporary global config listing every
workflow that is either installed or in your profile, so nothing is deleted. Your
real global config is not modified.

Usage (from the project root):
  python3 scripts/vsdd/openspec_preflight.py --tools claude,opencode
  python3 scripts/vsdd/openspec_preflight.py --json
  python3 scripts/vsdd/openspec_preflight.py --safe-update

Exit codes: 0 no blocking findings, 1 findings that need a decision
(workflows would be deleted, custom schema), 2 bad invocation / CLI missing.
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

SKIP_DIRS = {".git", "node_modules", ".dart_tool", "build", ".venv", "venv"}
STOCK_SCHEMAS = {"spec-driven", "visual-driven"}
# OpenSpec tool id -> project folders it writes (measured with OpenSpec 1.13.2 by running
# `openspec init --tools <id>` for every tool). Several tools share `.agents`.
# HOME_TOOLS write outside the project instead.
TOOL_DIRS: dict[str, tuple[str, ...]] = {
    "amazon-q": (".amazonq",), "antigravity": (".agents",), "auggie": (".augment",),
    "bob": (".bob",), "claude": (".claude",), "cline": (".cline", ".clinerules"),
    "command-code": (".commandcode",), "codeartsagent": (".codeartsdoer",), "codex": (".agents",),
    "devin": (".devin",), "windsurf": (".devin",), "forgecode": (".forge",),
    "codebuddy": (".codebuddy",), "continue": (".continue",), "costrict": (".cospec",),
    "crush": (".crush",), "cursor": (".cursor",), "factory": (".factory",),
    "gemini": (".gemini",), "github-copilot": (".github",), "hermes": (".hermes",),
    "iflow": (".iflow",), "junie": (".junie",), "kilocode": (".kilo", ".kilocode"),
    "kimi": (".kimi-code",), "kiro": (".kiro",), "lingma": (".lingma",), "vibe": (".vibe",),
    "oh-my-pi": (".omp",), "opencode": (".opencode",), "pi": (".pi",),
    "codeassistant": (".codeassistant",), "qoder": (".qoder",), "qwen": (".qwen",),
    "rovodev": (".rovodev",), "roocode": (".roo",), "trae": (".trae",), "zed": (".agents",),
    "zcode": (".zcode",), "agents": (".agents",),
}
HOME_TOOLS: dict[str, str] = {"minimax-code": "~/.minimax"}


def workflow_id(skill_dir: str) -> str:
    """openspec-bulk-archive-change -> bulk-archive, openspec-sync-specs -> sync."""
    name = skill_dir.removeprefix("openspec-")
    for suffix in ("-change", "-specs"):
        name = name.removesuffix(suffix)
    return name


def installed_skills(root: Path) -> dict[str, set[str]]:
    """{tool folder: {workflow ids}} for every dot-folder holding openspec-* skills."""
    found: dict[str, set[str]] = {}
    for tool in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith(".") and p.name not in SKIP_DIRS):
        for skill in tool.rglob("openspec-*/SKILL.md"):
            if any(part in SKIP_DIRS for part in skill.parts):
                continue
            found.setdefault(tool.name, set()).add(workflow_id(skill.parent.name))
    return found


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)


def profile_workflows(tool: str) -> set[str] | None:
    """Workflows `openspec init/update` generates with the user's real global config."""
    with tempfile.TemporaryDirectory(prefix="vsdd-preflight-") as tmp:
        tmp_path = Path(tmp)
        run(["git", "init", "-q"], tmp_path)
        proc = run(["openspec", "init", "--tools", tool, "."], tmp_path)
        if proc.returncode != 0:
            return None
        return {w for ws in installed_skills(tmp_path).values() for w in ws}


def global_config() -> dict:
    proc = run(["openspec", "config", "list", "--json"], Path.cwd())
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def configured_schema(root: Path) -> str | None:
    for name in ("config.yaml", "config.yml"):
        path = root / "openspec" / name
        if path.is_file():
            m = re.search(r"^schema:\s*['\"]?([\w.-]+)", path.read_text(encoding="utf-8"), re.M)
            return m.group(1) if m else None
    return None


def in_flight_changes(root: Path) -> list[tuple[str, str]]:
    changes = root / "openspec" / "changes"
    out = []
    if changes.is_dir():
        for d in sorted(p for p in changes.iterdir() if p.is_dir() and p.name != "archive"):
            meta = d / ".openspec.yaml"
            m = re.search(r"^schema:\s*(\S+)", meta.read_text(encoding="utf-8"), re.M) if meta.is_file() else None
            out.append((d.name, m.group(1) if m else "unknown"))
    return out


MANAGED_DIRS = {d for dirs in TOOL_DIRS.values() for d in dirs}


def tool_for_dir(folder: str) -> str | None:
    return next((t for t, dirs in TOOL_DIRS.items() if folder in dirs), None)


def safe_update(root: Path, keep: set[str]) -> int:
    cfg = global_config()
    temp_cfg = {k: v for k, v in cfg.items() if k in ("featureFlags", "delivery")}
    temp_cfg.update({"profile": "custom", "workflows": sorted(keep), "telemetry": {"noticeSeen": True}})
    with tempfile.TemporaryDirectory(prefix="vsdd-xdg-") as xdg:
        (Path(xdg) / "openspec").mkdir()
        (Path(xdg) / "openspec" / "config.json").write_text(json.dumps(temp_cfg))
        env = {**os.environ, "XDG_CONFIG_HOME": xdg}
        proc = run(["openspec", "update", "."], root, env)
        print(proc.stdout.strip()[-2000:])
        if proc.returncode != 0:
            print(proc.stderr.strip(), file=sys.stderr)
            return 2
    after = {w for ws in installed_skills(root).values() for w in ws}
    lost = keep - after
    print(f"Updated with workflows: {', '.join(sorted(keep))}")
    if lost:
        print(f"WARNING: not present after update: {', '.join(sorted(lost))}")
        return 1
    print("No workflows were removed. A plain `openspec update` would still remove the ones "
          "missing from your global profile - add them with `openspec config profile`.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--tools", default="", help="comma-separated OpenSpec tool ids you want set up")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--safe-update", action="store_true",
                    help="run `openspec update` without deleting installed workflows")
    args = ap.parse_args()
    root = args.root.resolve()

    if shutil.which("openspec") is None:
        print("openspec CLI not found. Install: npm install -g @fission-ai/openspec@latest", file=sys.stderr)
        return 2
    version = run(["openspec", "--version"], root).stdout.strip()
    initialised = (root / "openspec").is_dir()
    installed = installed_skills(root) if root.is_dir() else {}
    managed = {d: ws for d, ws in installed.items() if d in MANAGED_DIRS}
    installed_all = {w for ws in managed.values() for w in ws}
    # Always probe with claude: it writes only inside the throwaway folder.
    profile = profile_workflows("claude")
    would_remove = sorted(installed_all - profile) if profile is not None else []
    requested = [t.strip() for t in args.tools.split(",") if t.strip()]
    missing_tools, unknown_tools = [], []
    home_tools = []
    for tool in requested:
        if tool in HOME_TOOLS:
            home_tools.append(tool)
            continue
        folders = TOOL_DIRS.get(tool)
        if folders is None:
            unknown_tools.append(tool)
        elif not any(f in installed for f in folders):
            missing_tools.append(tool)
    schema = configured_schema(root)
    custom_schema = schema is not None and schema not in STOCK_SCHEMAS
    changes = in_flight_changes(root)

    if args.safe_update:
        if not initialised:
            print("No openspec/ directory: run `openspec init --tools <tools>` instead.", file=sys.stderr)
            return 2
        return safe_update(root, installed_all | (profile or set()))

    report = {
        "openspec_version": version,
        "initialised": initialised,
        "schema": schema,
        "custom_schema": custom_schema,
        "installed": {k: sorted(v) for k, v in installed.items()},
        "unmanaged_folders": sorted(set(installed) - set(managed)),
        "profile_workflows": sorted(profile) if profile is not None else None,
        "update_would_remove": would_remove,
        "tools_to_add": missing_tools,
        "unknown_tools": unknown_tools,
        "home_folder_tools": {t: HOME_TOOLS[t] for t in home_tools},
        "in_flight_changes": [{"name": n, "schema": s} for n, s in changes],
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"OpenSpec CLI:        {version}")
        print(f"Project initialised: {'yes' if initialised else 'no (fresh install: use openspec init)'}")
        if initialised:
            print(f"Configured schema:   {schema or '(none)'}" + ("   <- CUSTOM: ASK before changing" if custom_schema else ""))
        for folder, workflows in installed.items():
            tag = "" if folder in managed else "   (not an OpenSpec tool folder - `openspec update` leaves it alone)"
            print(f"Skills in {folder + ':':<11} {', '.join(sorted(workflows))}{tag}")
        print("Profile workflows:   " + (", ".join(sorted(profile)) if profile is not None else "(could not determine)"))
        if would_remove:
            print(f"!! `openspec update` would DELETE: {', '.join(would_remove)}")
            print("   Options: add them to the profile (`openspec config profile`, the user runs it), or")
            print("   run this script with --safe-update instead of a plain `openspec update`.")
        if missing_tools:
            print(f"Tools to add:        {', '.join(missing_tools)}  ->  openspec init --tools {','.join(missing_tools)} .")
        for t in home_tools:
            print(f"Home-folder tool:    {t} installs skills in {HOME_TOOLS[t]} (machine-wide) -> ASK; then pass")
            print(f"                     --extra-dir {HOME_TOOLS[t]} to install_overlay.py and vsdd_snapshot.py")
        if unknown_tools:
            print(f"Unknown tool ids:    {', '.join(unknown_tools)} (check their folder by hand)")
        for name, s in changes:
            note = "" if s == "visual-driven" else "  (keeps its schema: no diagrams.md, no diagram merge)"
            print(f"In-flight change:    {name} [{s}]{note}")
    return 1 if (would_remove or custom_schema) else 0


if __name__ == "__main__":
    sys.exit(main())
