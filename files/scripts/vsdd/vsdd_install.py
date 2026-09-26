#!/usr/bin/env python3
"""Install or upgrade VSDD in one go: the mechanical steps of the kit's SETUP.md.

Run it from the kit, not from the project:

  python3 "$KIT"/files/scripts/vsdd/vsdd_install.py --root "$ROOT" --tools claude,qwen
  python3 "$KIT"/files/scripts/vsdd/vsdd_install.py --root "$ROOT" --tools qwen --dry-run

It does Steps 0-5 (docs/SETUP-REFERENCE.md has each one by hand) and creates the
decisions log:
  0  install branch (vsdd-install) and a snapshot of what git can't restore
  1  openspec init (fresh project), or add missing tools and run `openspec update`
  2  copy the schema, docs and scripts
  3  config.yaml: write the kit example (fresh or stock config), or merge the VSDD
     keys into an existing one where that can be done safely
  4  AGENTS.md: the VSDD section, a one-line pointer, or nothing (--agents-md);
     CLAUDE.md imports AGENTS.md for Claude Code
  5  skill and command overlay, then `--check`
  6  openspec/specs/architecture/decisions.md header (no rules are invented)
  7  record the kit version, tools and folders in openspec/.vsdd.json

Re-running it upgrades an install: files are copied again, and overlay blocks from
an older kit are refreshed. `--status` compares an install with this kit and
changes nothing:

  python3 "$KIT"/files/scripts/vsdd/vsdd_install.py --root "$ROOT" --status

It never makes a decision that the runbook marks ASK. When one is needed, it stops
BEFORE changing anything (exit 3) and names the flag that records the answer:
  uncommitted changes                 --allow-dirty
  `openspec update` would delete      --update safe  (keep them) | --update plain (accept)
  a custom schema                     --custom-schema switch | --custom-schema keep
  an existing AGENTS.md               --agents-md full | pointer | skip
  a shared workspace folder with      --extra-dir <folder> (patch it: affects every project
  OpenSpec commands (VS Code/Devin)     that uses it) | --leave-shared
  a home-folder tool (e.g. MiniMax)   --extra-dir <folder>
  hand-edited skills                  do Step 1b of docs/SETUP-REFERENCE.md by hand, then re-run

--tooling-dir <folder> keeps the kit's docs and scripts out of the project: they are
copied to that folder (e.g. a shared spec-core/vsdd in the editor workspace), and the
project's config names it. Pointing it at the kit's own files/ folder (the kit clone
added to the workspace) uses them in place: nothing is copied, and `git pull` in the
kit upgrades them. Only the schema (OpenSpec needs it in the project), the
config entries and the project's own diagrams stay in the project.

What is left for the agent is printed at the end (and in --json): the config
`context:`, the baseline diagrams (Step 6), CI (Step 7), the smoke test (Step 8)
and the report (Step 9), plus anything it could not merge safely.

Exit codes: 0 installed (see the to-do list), 1 a step failed, 2 bad invocation or
missing prerequisite, 3 stopped for a decision (nothing was changed).
With --status: 0 up to date, 1 an upgrade is due, 2 VSDD isn't installed.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from openspec_preflight import (  # noqa: E402
    HOME_TOOLS,
    STOCK_SCHEMAS,
    TOOL_DIRS,
    configured_schema,
    installed_skills,
    openspec_content,
    profile_workflows,
    safe_update,
    workspace_folders,
)
from install_overlay import PATCHES  # noqa: E402

KIT_FILES = HERE.parent.parent
KIT_VERSION = (KIT_FILES.parent / "VERSION").read_text(encoding="utf-8").strip() \
    if (KIT_FILES.parent / "VERSION").is_file() else "unknown"
STAMP = Path("openspec") / ".vsdd.json"
SCRIPTS = ("validate_mermaid.py", "install_overlay.py", "merge_diagrams.py",
           "openspec_preflight.py", "vsdd_snapshot.py")
SECTION = "## OpenSpec & Visual Spec-Driven Development"
POINTER_MARK = "vsdd:pointer"
CHECK_CHANGE = "vsdd-install-check"
# A line from each VSDD entry of config.yaml.example, used to tell whether an
# existing config already has it: (top-level key, sub-key, marker text)
CONFIG_MARKERS = (
    ("rules", "diagrams", "## Placement"),
    ("rules", "design", "decisions.md"),
    ("rules", "tasks", "trace the After State"),
    ("operations", "apply", "VSDD:"),
    ("operations", "archive", "merge_diagrams.py"),
    ("operations", "archive", "decisions.md"),
)


class Stop(Exception):
    """A decision is needed (exit 3)."""


class Failed(Exception):
    """A step failed (exit 1)."""


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise Failed(f"`{' '.join(cmd)}` failed:\n{(proc.stderr or proc.stdout).strip()[-1500:]}")
    return proc


def version_tuple(text: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def kit_commit() -> str | None:
    """The kit clone's commit (tag-relative, `-dirty` if edited), or None outside git."""
    proc = run(["git", "describe", "--tags", "--always", "--dirty"], KIT_FILES.parent, check=False)
    return proc.stdout.strip() or None if proc.returncode == 0 else None


class Installer:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.root: Path = args.root.resolve()
        self.tools = [t.strip() for t in args.tools.split(",") if t.strip()]
        self.extra_dirs = [d.expanduser().resolve() for d in args.extra_dir]
        self.tooling = args.tooling_dir.expanduser().resolve() if args.tooling_dir else None
        self.done: list[str] = []
        self.todo: list[str] = []
        self.plan: list[str] = []

    # ---------------------------------------------------------------- checks
    def prerequisites(self) -> None:
        if not (KIT_FILES / "agents" / "AGENTS.vsdd.md").is_file():
            raise SystemExit("error: run this script from the kit (KIT/files/scripts/vsdd/), "
                             "not from a project copy")
        if not self.root.is_dir():
            raise SystemExit(f"error: --root {self.root} is not a directory")
        if shutil.which("openspec") is None:
            raise SystemExit("error: openspec CLI not found - ASK the user to install it: "
                             "npm install -g @fission-ai/openspec@latest")
        self.version = run(["openspec", "--version"], self.root).stdout.strip()
        if version_tuple(self.version) < (1, 2, 0):
            raise SystemExit(f"error: OpenSpec {self.version} is older than 1.2.0 - ASK the user to upgrade")
        if self.tools == ["none"]:
            return
        unknown = [t for t in self.tools if t not in TOOL_DIRS and t not in HOME_TOOLS]
        if not self.tools or unknown:
            raise SystemExit(f"error: --tools needs OpenSpec tool ids; unknown: {', '.join(unknown) or '(none given)'}")

    def inspect(self) -> None:
        """Collect everything that needs a decision. Raises Stop before any change."""
        root, a = self.root, self.args
        self.is_git = run(["git", "rev-parse", "--is-inside-work-tree"], root, check=False).returncode == 0
        stops: list[str] = []
        if self.is_git and not a.allow_dirty:
            dirty = run(["git", "status", "--porcelain"], root).stdout.strip()
            if dirty:
                stops.append("the working tree has uncommitted changes. Recommend committing first; "
                             "to continue anyway, re-run with --allow-dirty")
        for tool in self.tools:
            if tool in HOME_TOOLS:
                folder = Path(HOME_TOOLS[tool]).expanduser().resolve()
                if folder not in self.extra_dirs:
                    stops.append(f"{tool} keeps its skills in {HOME_TOOLS[tool]} (machine-wide). If the user "
                                 f"agrees to patch it, re-run with --extra-dir {HOME_TOOLS[tool]}")
        self.initialised = (root / "openspec").is_dir()
        self.installed = installed_skills(root)
        managed = {d for dirs in TOOL_DIRS.values() for d in dirs}
        installed_all = {w for d, ws in self.installed.items() if d in managed for w in ws}
        self.profile = profile_workflows("claude") or set()
        self.would_remove = sorted(installed_all - self.profile) if self.profile else []
        self.keep_workflows = installed_all | self.profile
        if self.initialised and self.would_remove and not a.update:
            stops.append(f"`openspec update` would DELETE these workflows: {', '.join(self.would_remove)} "
                         "(missing from the global profile). Options: the user adds them with "
                         "`openspec config profile` and you re-run; or --update safe (keep them, global "
                         "config untouched); or --update plain (accept the deletion)")
        self.schema = configured_schema(root)
        self.custom_schema = self.schema is not None and self.schema not in STOCK_SCHEMAS
        if self.custom_schema and not a.custom_schema:
            stops.append(f"the project uses a custom schema '{self.schema}'. Options (Step 3 of docs/SETUP-REFERENCE.md): "
                         "--custom-schema switch (use visual-driven), or --custom-schema keep (you add "
                         "the diagrams artifact to their schema by hand), or stop")
        self.shared_notes = []
        shared = workspace_folders(root, [w.expanduser().resolve() for w in a.workspace])
        self.ws_folders = sorted(workspace_folders(root, [w.expanduser().resolve() for w in a.workspace],
                                                   include_root=True),
                                 key=lambda f: len(f.parts), reverse=True)
        if self.tooling is not None:
            self.T, self.P = self.ws_ref(self.tooling), self.ws_ref(root)
            if not self.ws_folders:
                self.shared_notes.append(
                    "Step 3: no editor workspace was found, so the config names the tooling folder by absolute "
                    "path, which only works on this machine. Pass --workspace <file> and re-run to use "
                    "workspace-relative paths")
        for folder, source in sorted(shared.items()):
            c = openspec_content(folder)
            if not (c["skills"] or c["commands"]):
                continue
            covered = any(folder == d or d.is_relative_to(folder) for d in self.extra_dirs)
            if covered:
                if c["commands"] and self.tools != ["none"]:
                    self.shared_notes.append(
                        f"Step 9 report: the project and the shared folder {folder} both have /opsx commands, "
                        "so agents see two copies (both patched). Suggest `--tools none` next time if the "
                        "shared folder is the one the team uses")
                continue
            if not a.leave_shared:
                stops.append(
                    f"the workspace ({source}) includes {folder}, which has OpenSpec skills or /opsx commands "
                    f"({c['skills']} skills, {c['commands']} commands; VSDD-patched skills: {c['patched_skills']}). "
                    "Stock copies there can bypass VSDD. Ask the user: patch it with --extra-dir "
                    f"{folder} (affects every project that uses it; the VSDD steps are no-ops in projects "
                    "without docs/VSDD.md), and use --tools none if the project should rely on that folder "
                    "instead of its own copies; or leave it with --leave-shared")
        self.agents_mode = a.agents_md or self.default_agents_mode()
        if self.agents_mode is None:
            stops.append("AGENTS.md already exists. Ask the user how VSDD should appear in it: "
                         "--agents-md full (a routing section: /opsx, diagrams, validator, decisions log), "
                         "--agents-md pointer (one line pointing at docs/VSDD.md), or --agents-md skip "
                         "(leave it alone - /opsx still works, but ad-hoc agent work won't know about VSDD)")
        hand = self.hand_edited_skills()
        if hand:
            stops.append("these skills mention diagrams but have no VSDD markers, so they were probably "
                         f"hand-edited: {', '.join(hand)}. Do Step 1b of the kit's docs/SETUP-REFERENCE.md by hand, then re-run")
        if stops:
            raise Stop("\n".join(f"- {s}" for s in stops))

    def ws_ref(self, path: Path) -> str:
        """Name a path by its editor-workspace folder (e.g. spec-core/vsdd), else absolutely."""
        for folder in self.ws_folders:
            if path == folder or path.is_relative_to(folder):
                rel = path.relative_to(folder).as_posix()
                return folder.name if rel == "." else f"{folder.name}/{rel}"
        return str(path)

    def localise(self, text: str) -> str:
        """Point kit paths (docs/, scripts/vsdd/) at the tooling folder, and give scripts --root."""
        if self.tooling is None:
            return text
        text = re.sub(r"(?<![\w/.-])python3 scripts/vsdd/([\w]+\.py)",
                      lambda m: f"python3 {self.T}/scripts/vsdd/{m.group(1)} --root {self.P}", text)
        text = re.sub(r"(?<![\w/.-])scripts/vsdd/", f"{self.T}/scripts/vsdd/", text)
        return re.sub(r"(?<![\w/.-])docs/(VSDD|MERMAID_RULES)\.md", rf"{self.T}/docs/\1.md", text)

    def tooling_context(self) -> str:
        return (f"  VSDD tooling: its docs and scripts are in `{self.T}` (a folder of this workspace), not in this "
                f"project. Read `{self.T}/docs/VSDD.md`; run scripts as `python3 {self.T}/scripts/vsdd/<script>.py "
                f"--root {self.P}`.")

    def portable(self, path: Path) -> str:
        """A path for the committed stamp: ~/..., workspace-relative, or absolute as a last resort."""
        home = Path.home()
        if path.is_relative_to(home) and not any(path.is_relative_to(f) for f in self.ws_folders):
            return f"~/{path.relative_to(home).as_posix()}"
        return self.ws_ref(path)

    def default_agents_mode(self) -> str | None:
        """full for a new AGENTS.md, the existing choice on an upgrade, None = ASK."""
        agents = self.root / "AGENTS.md"
        if not agents.exists():
            return "full"
        text = agents.read_text(encoding="utf-8")
        if SECTION in text:
            return "full"
        if POINTER_MARK in text:
            return "pointer"
        return None

    def hand_edited_skills(self) -> list[str]:
        out = []
        for tool in sorted(p for p in self.root.iterdir() if p.is_dir() and p.name.startswith(".")):
            for name in PATCHES:
                for skill in tool.glob(f"**/{name}/SKILL.md"):
                    text = skill.read_text(encoding="utf-8", errors="replace")
                    if "diagram" in text.lower() and "vsdd:" not in text:
                        out.append(str(skill.relative_to(self.root)))
        return out

    # ----------------------------------------------------------------- steps
    def step0_branch_and_snapshot(self) -> None:
        if self.is_git and not self.args.no_branch:
            current = run(["git", "branch", "--show-current"], self.root).stdout.strip()
            if current.startswith("vsdd-install"):
                self.done.append(f"0 branch: already on {current}")
            else:
                existing = set(run(["git", "branch", "--format=%(refname:short)"], self.root).stdout.split())
                name, n = "vsdd-install", 2
                while name in existing:
                    name, n = f"vsdd-install-{n}", n + 1
                self.plan.append(f"0 create branch {name} (from {current or 'HEAD'})")
                if not self.args.dry_run:
                    run(["git", "switch", "-c", name], self.root)
                    self.done.append(f"0 branch: created {name} from {current or 'HEAD'}")
        reuse = self.install_snapshot()
        if reuse:
            self.snapshot = str(reuse)
            self.done.append(f"0 snapshot: reusing {reuse} (taken when the install branch was created)")
            return
        cmd = [sys.executable, str(HERE / "vsdd_snapshot.py"), "--root", str(self.root), "save"]
        for d in self.extra_dirs:
            cmd += ["--extra-dir", str(d)]
        self.plan.append("0 snapshot untracked install footprint + global OpenSpec config")
        if not self.args.dry_run:
            out = run(cmd, self.root).stdout.strip()
            self.snapshot = next((l.split(":", 1)[1].strip() for l in out.splitlines()
                                  if "snapshot" in l.lower() and ":" in l), out.splitlines()[-1] if out else "")
            self.done.append(f"0 snapshot: {self.snapshot}")

    def install_snapshot(self) -> Path | None:
        """On a re-run on the install branch: the snapshot taken when that branch was created.

        A new snapshot would capture a half-installed state, and rolling back to it would
        keep the install. The earliest snapshot taken on this branch is the pre-install one.
        """
        if not self.is_git:
            return None
        current = run(["git", "branch", "--show-current"], self.root).stdout.strip()
        if not current.startswith("vsdd-install"):
            return None
        for snap in sorted((Path.home() / ".vsdd-snapshots").glob(f"{self.root.name}-*")):
            try:
                m = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if m.get("root") == str(self.root) and (m.get("git") or {}).get("branch") == current:
                return snap
        return None

    def step1_openspec(self) -> None:
        root, tools = self.root, self.tools
        project_tools = [t for t in tools if t not in HOME_TOOLS] or tools
        if not self.initialised:
            self.plan.append(f"1 openspec init --tools {','.join(tools)}")
            if not self.args.dry_run:
                run(["openspec", "init", "--tools", ",".join(tools), str(root)], root)
                self.done.append(f"1 openspec init --tools {','.join(tools)}")
            return
        missing = [t for t in project_tools if t != "none"
                   and not any(f in self.installed for f in TOOL_DIRS.get(t, ()))]
        if missing:
            self.plan.append(f"1 add tools: openspec init --tools {','.join(missing)}")
            if not self.args.dry_run:
                run(["openspec", "init", "--tools", ",".join(missing), str(root)], root)
                self.done.append(f"1 added tools: {','.join(missing)}")
        if self.would_remove and self.args.update == "safe":
            self.plan.append("1 openspec update, keeping every installed workflow (--update safe)")
            if not self.args.dry_run:
                if safe_update(root, self.keep_workflows) != 0:
                    raise Failed("safe update did not keep every workflow (see output above)")
                self.done.append("1 openspec update (safe: no workflows removed)")
        else:
            note = f" - removes {', '.join(self.would_remove)} (user accepted)" if self.would_remove else ""
            self.plan.append(f"1 openspec update{note}")
            if not self.args.dry_run:
                run(["openspec", "update", str(root)], root)
                self.done.append(f"1 openspec update{note}")

    def step2_copy(self) -> None:
        root = self.root
        tools = self.tooling or root
        where = f" into {tools}" if self.tooling else ""
        self.plan.append(f"2 copy schema; docs/VSDD.md, docs/MERMAID_RULES.md (if missing), scripts/vsdd/{where}")
        if self.args.dry_run:
            return
        dest = root / "openspec" / "schemas" / "visual-driven"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(KIT_FILES / "openspec" / "schemas" / "visual-driven", dest)
        in_place = self.tooling is not None and self.tooling == KIT_FILES.resolve()
        if self.tooling:
            left = [p for p in ("docs/VSDD.md", "docs/MERMAID_RULES.md", "scripts/vsdd") if (root / p).exists()]
            if left:
                self.todo.append(f"Step 2: the project still has its own copies of {', '.join(left)}. The tooling "
                                 f"now lives in {self.T}: remove them from the project if the kit put them there")
        if in_place:
            run(["openspec", "schema", "validate", "visual-driven"], root)
            self.done.append(f"2 copied the schema into the project; docs and scripts used in place from the kit "
                             f"({self.T}); schema is valid")
            return
        (tools / "docs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(KIT_FILES / "docs" / "VSDD.md", tools / "docs" / "VSDD.md")
        rules = tools / "docs" / "MERMAID_RULES.md"
        if rules.exists():
            if rules.read_bytes() != (KIT_FILES / "docs" / "MERMAID_RULES.md").read_bytes():
                self.todo.append("Step 2: docs/MERMAID_RULES.md already existed and differs from the kit. "
                                 "Diff it against KIT/files/docs/MERMAID_RULES.md and merge kit additions, "
                                 "keeping the project's own rules")
        else:
            shutil.copy2(KIT_FILES / "docs" / "MERMAID_RULES.md", rules)
        (tools / "scripts" / "vsdd").mkdir(parents=True, exist_ok=True)
        for name in SCRIPTS:
            shutil.copy2(HERE / name, tools / "scripts" / "vsdd" / name)
        run(["openspec", "schema", "validate", "visual-driven"], root)
        self.done.append("2 copied the schema into the project" + (
            f", docs and scripts into {self.T}" if self.tooling else ", docs and scripts") + "; schema is valid")

    def step3_config(self) -> None:
        path = self.root / "openspec" / "config.yaml"
        if not path.exists() and (self.root / "openspec" / "config.yml").exists():
            path = self.root / "openspec" / "config.yml"
        example = (KIT_FILES / "openspec" / "config.yaml.example").read_text(encoding="utf-8")
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        stock = not [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")
                     and not l.startswith("schema:")]
        if stock:
            self.plan.append(f"3 write {path.name} from the kit example")
            keep = self.custom_schema and self.args.custom_schema == "keep"
            if keep:
                self.plan.append(f"3 keep schema: {self.schema}")
            if not self.args.dry_run:
                text = re.sub(r"^schema:.*$", f"schema: {self.schema}", example, count=1, flags=re.M) if keep else example
                path.write_text(text, encoding="utf-8")
                self.done.append(f"3 {path.name}: written from the kit example"
                                 + (f", keeping schema: {self.schema}" if keep else ""))
                if keep:
                    self.todo.append(f"Step 3 (b): add the diagrams artifact to the custom schema "
                                     f"'{self.schema}' by hand, then `openspec schema validate` it")
        else:
            self.plan.append(f"3 merge VSDD keys into the existing {path.name}")
            if not self.args.dry_run:
                self.merge_config(path, text, example)
        if self.args.dry_run:
            return
        if self.tooling:
            text = path.read_text(encoding="utf-8")
            old = re.search(r"VSDD tooling: its docs and scripts are in `([^`]+)`.*?--root ([^`\s]+)`", text)
            if old and (old.group(1), old.group(2)) != (self.T, self.P):
                # The tooling folder moved: repoint every path the previous install wrote.
                text = text.replace(f"{old.group(1)}/", f"{self.T}/").replace(f"--root {old.group(2)}", f"--root {self.P}")
                text = re.sub(r"^  VSDD tooling: .*$", self.tooling_context(), text, count=1, flags=re.M)
            text = self.localise(text)
            if "VSDD tooling:" not in text:
                block = top_level_block(text, "context")
                if block:
                    text = text.replace(block, block.rstrip("\n") + "\n" + self.tooling_context(), 1)
                else:
                    text = text.rstrip("\n") + "\n\ncontext: |\n" + self.tooling_context() + "\n"
            path.write_text(text, encoding="utf-8")
            self.done.append(f"3 config: VSDD paths point at {self.T}; context names the tooling folder")
        final = path.read_text(encoding="utf-8")
        if "<PROJECT_NAME>" in final or not re.search(r"^context:", final, re.M):
            self.todo.append("Step 3: fill in `context:` in openspec/config.yaml from the README, the package "
                             "manifests and the top-level layout (4-8 lines, no invented conventions). "
                             "Leave or fill the optional Pitfalls line")
        self.verify_config()

    def merge_config(self, path: Path, text: str, example: str) -> None:
        notes = []
        if self.custom_schema and self.args.custom_schema == "keep":
            self.todo.append(f"Step 3 (b): add the diagrams artifact to the custom schema '{self.schema}' "
                             "by hand, then `openspec schema validate` it")
        elif re.search(r"^schema:", text, re.M):
            text = re.sub(r"^schema:.*$", "schema: visual-driven", text, count=1, flags=re.M)
            notes.append("schema: visual-driven")
        else:
            text = "schema: visual-driven\n\n" + text
            notes.append("schema line added")
        if re.search(r"^prompts:", text, re.M):
            self.todo.append("Step 3 (ASK): config.yaml has a `prompts:` key, which OpenSpec ignores. Show "
                             "the user its contents and ask whether to rename it to `rules:`")
        for key in ("context", "rules", "operations"):
            if not re.search(rf"^{key}:", text, re.M):
                text = text.rstrip("\n") + "\n\n" + top_level_block(example, key) + "\n"
                notes.append(f"{key} added from the example")
        # Sub-keys the VSDD needs but the user's block lacks entirely: add them from the example.
        for key, sub in sorted({(k, s) for k, s, _ in CONFIG_MARKERS}):
            block = top_level_block(text, key) or ""
            if re.search(rf"^\s+{sub}:", block, re.M):
                continue
            indent = re.search(r"^( +)\S", block.split("\n", 1)[1] if "\n" in block else "", re.M)
            if indent and indent.group(1) != "  ":
                continue  # unusual indentation: leave it to the agent (reported below)
            sub_block = sub_level_block(top_level_block(example, key), sub)
            text = text.replace(block, block.rstrip("\n") + "\n" + sub_block, 1)
            notes.append(f"{key}.{sub} added")
        missing = [f"{k}.{s}" for k, s, marker in CONFIG_MARKERS
                   if marker not in (top_level_block(text, k) or "")]
        if missing:
            self.config_incomplete = True
            self.todo.append("Step 3: these VSDD config entries couldn't be added automatically (the key has "
                             "the project's own entries, or unusual indentation). Add the VSDD lines from "
                             f"KIT/files/openspec/config.yaml.example by hand, keeping theirs: "
                             f"{', '.join(sorted(set(missing)))}. Then check with `openspec instructions "
                             "diagrams --change <any change>` (must show <rules>)")
        path.write_text(text, encoding="utf-8")
        self.done.append(f"3 {path.name}: merged ({'; '.join(notes) or 'no key changes'})")

    def verify_config(self) -> None:
        root = self.root
        if self.custom_schema and self.args.custom_schema == "keep":
            # Their schema has no diagrams artifact until the Step 3 (b) edit is done.
            self.todo.append("Step 3 (b), after the schema edit: check with `openspec new change x && "
                             "openspec instructions diagrams --change x` (must show <rules> and "
                             "MERMAID_RULES), then delete the change")
            self.done.append("3 config check: deferred until the custom schema has a diagrams artifact")
            return
        change_dir = root / "openspec" / "changes" / CHECK_CHANGE
        if change_dir.exists():
            raise Failed(f"{change_dir} already exists - remove it and re-run")
        try:
            run(["openspec", "new", "change", CHECK_CHANGE], root)
            out = run(["openspec", "instructions", "diagrams", "--change", CHECK_CHANGE], root).stdout
            missing = [p for p in ("<rules>", "MERMAID_RULES") if p not in out]
            if missing and getattr(self, "config_incomplete", False):
                self.done.append("3 config check: deferred until the to-do entries below are merged")
                return
            if missing:
                raise Failed(f"config check: `openspec instructions diagrams` lacks {', '.join(missing)} - "
                             "check config.yaml keys and indentation")
        finally:
            shutil.rmtree(change_dir, ignore_errors=True)
        self.done.append("3 config check: rules reach `openspec instructions`")

    def step4_agents(self) -> None:
        root, mode = self.root, self.agents_mode
        agents = root / "AGENTS.md"
        touch_claude = "claude" in self.tools and mode != "skip"
        self.plan.append(f"4 AGENTS.md: {mode}" + (", CLAUDE.md @AGENTS.md" if touch_claude else ""))
        if self.args.dry_run:
            return
        if mode == "skip":
            self.done.append("4 AGENTS.md: left alone (--agents-md skip)")
            self.todo.append("Step 4: AGENTS.md was left alone by request. /opsx carries VSDD on its own; "
                             "mention in the report that ad-hoc agent work won't see the VSDD rules")
            return
        name = "AGENTS.vsdd.md" if mode == "full" else "AGENTS.vsdd-pointer.md"
        snippet = self.localise((KIT_FILES / "agents" / name).read_text(encoding="utf-8")).rstrip("\n") + "\n"
        if agents.exists():
            text = agents.read_text(encoding="utf-8")
            had = "section" if SECTION in text else "pointer" if POINTER_MARK in text else None
            if SECTION in text:
                text = replace_section(text, SECTION, "")
            text = "\n".join(l for l in text.splitlines() if POINTER_MARK not in l)
            text = re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n\n" + snippet
            want = "section" if mode == "full" else "pointer"
            self.done.append(f"4 AGENTS.md: VSDD {want} " + (
                "added" if had is None else "refreshed" if had == want else f"replaces the {had}"))
            if re.search(r"^##+ .*Diagram Standards", text, re.M | re.I):
                self.todo.append("Step 4 (ASK): AGENTS.md still has an older diagram-rules section. Ask "
                                 "before removing it - the VSDD section and docs/VSDD.md replace it")
        else:
            text = f"# AGENTS.md\n\n<!-- TODO(vsdd): one-line description of {root.name} -->\n\n{snippet}"
            self.todo.append("Step 4: replace the TODO line at the top of AGENTS.md with a one-line "
                             "project description")
            self.done.append(f"4 AGENTS.md: created ({mode})")
        agents.write_text(text, encoding="utf-8")
        if touch_claude:
            claude = root / "CLAUDE.md"
            if not claude.exists():
                shutil.copy2(KIT_FILES / "agents" / "CLAUDE.md.example", claude)
                self.done.append("4 CLAUDE.md: created (@AGENTS.md)")
            elif "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
                claude.write_text("@AGENTS.md\n\n" + claude.read_text(encoding="utf-8"), encoding="utf-8")
                self.done.append("4 CLAUDE.md: @AGENTS.md added at the top")

    def step5_overlay(self) -> None:
        self.plan.append("5 skill and command overlay, then --check")
        if self.args.dry_run:
            return
        cmd = [sys.executable, str((self.tooling or self.root) / "scripts" / "vsdd" / "install_overlay.py"),
               "--root", str(self.root)]
        for d in self.extra_dirs:
            cmd += ["--extra-dir", str(d)]
        apply = run(cmd, self.root, check=False)
        check = run(cmd + ["--check"], self.root, check=False)
        if check.returncode != 0:
            raise Failed("overlay incomplete. If it says `anchor not found`, the stock skill text changed: "
                         "follow Step 5 of the kit's docs/SETUP-REFERENCE.md to insert those blocks by hand.\n"
                         + (apply.stdout + apply.stderr + check.stdout + check.stderr).strip()[-2000:])
        changed = sum(1 for l in apply.stdout.splitlines() if l.lstrip().startswith("+"))
        self.done.append(f"5 overlay: {changed} file change(s); check OK")

    def step6_decisions(self) -> None:
        path = self.root / "openspec" / "specs" / "architecture" / "decisions.md"
        if path.exists():
            self.done.append("6 decisions log: already exists")
            return
        self.plan.append("6 create openspec/specs/architecture/decisions.md (header only)")
        if self.args.dry_run:
            return
        example = (KIT_FILES / "openspec" / "specs" / "architecture" / "decisions.md.example").read_text(encoding="utf-8")
        header = example.split("\n## ", 1)[0].rstrip("\n") + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(header, encoding="utf-8")
        self.done.append("6 decisions log: created (no entries)")
        self.decisions_created = True

    def step7_stamp(self) -> None:
        """Record what was installed, so `--status` and a later upgrade can compare."""
        path = self.root / STAMP
        self.plan.append(f"7 record the kit version in {STAMP.as_posix()}")
        if self.args.dry_run:
            return
        stamp = {
            "kit_version": KIT_VERSION,
            "kit_commit": kit_commit(),
            "openspec_version": self.version,
            "tools": self.tools,
            "extra_dirs": [self.portable(d) for d in self.extra_dirs],
            "tooling_dir": self.T if self.tooling else None,
        }
        text = json.dumps(stamp, indent=2) + "\n"
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != text:
            path.write_text(text, encoding="utf-8")
        self.done.append(f"7 {STAMP.as_posix()}: kit {KIT_VERSION}"
                         + (f" ({stamp['kit_commit']})" if stamp["kit_commit"] else ""))

    # ------------------------------------------------------------------ main
    def run_all(self) -> int:
        self.prerequisites()
        self.inspect()
        for step in (self.step0_branch_and_snapshot, self.step1_openspec, self.step2_copy,
                     self.step3_config, self.step4_agents, self.step5_overlay, self.step6_decisions,
                     self.step7_stamp):
            step()
        if not self.args.dry_run:
            self.todo += self.shared_notes
            self.todo += [
                "Step 6: seed openspec/specs/architecture/diagrams.md from the real code (and ASK about "
                "capability-level diagrams)" if not (self.root / "openspec" / "specs" / "architecture"
                                                     / "diagrams.md").exists()
                else "Step 6: openspec/specs/architecture/diagrams.md already exists - check it still matches the code",
                *(["Step 6 item 6 (ASK): offer to turn up to three conventions the project already "
                    "documents into decisions.md entries (Source: install)"]
                  if getattr(self, "decisions_created", False) else []),
                "Step 7 (ASK): CI",
                "Step 8: smoke test",
                "Step 9: report to the user",
            ]
        return 0


def top_level_block(text: str, key: str) -> str | None:
    """The `key:` block of a YAML file, up to the next top-level key (comments kept)."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(rf"^{key}:", l)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines))
                if lines[i] and not lines[i][0].isspace() and not lines[i].startswith("#")), len(lines))
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].startswith("#")):
        end -= 1
    return "\n".join(lines[start:end])


def sub_level_block(block: str, sub: str) -> str:
    """The two-space-indented `sub:` entry of a top-level YAML block."""
    lines = block.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(f"  {sub}:"))
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  \S", lines[i])), len(lines))
    return "\n".join(lines[start:end]).rstrip("\n")


def replace_section(text: str, heading: str, snippet: str) -> str:
    lines = text.splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if re.match(r"^#{1,2} ", lines[i])), len(lines))
    return "\n".join(lines[:start] + snippet.rstrip("\n").splitlines() + ([""] if end < len(lines) else [])
                     + lines[end:]).rstrip("\n") + "\n"


def resolve_ref(ref: str, root: Path, folders: dict[Path, str]) -> Path | None:
    """Undo Installer.portable(): ~/..., a workspace folder name plus path, or absolute."""
    if ref.startswith("~"):
        return Path(ref).expanduser()
    if Path(ref).is_absolute():
        return Path(ref)
    head, _, rest = ref.partition("/")
    for folder in folders:
        if folder.name == head:
            return folder / rest if rest else folder
    return None


def show_status(args: argparse.Namespace) -> int:
    """Compare an install with this kit. Changes nothing."""
    root = args.root.resolve()
    if not (root / "openspec" / "schemas" / "visual-driven").is_dir():
        print(f"VSDD is not installed in {root} (no openspec/schemas/visual-driven).")
        return 2
    stamp_path = root / STAMP
    stamp = json.loads(stamp_path.read_text(encoding="utf-8")) if stamp_path.exists() else {}
    folders = workspace_folders(root, [w.expanduser().resolve() for w in args.workspace], include_root=True)
    due: list[str] = []
    notes: list[str] = []

    installed = stamp.get("kit_version")
    if not installed:
        due.append(f"no {STAMP.as_posix()}: installed by a kit older than 0.1.0")
    elif installed != KIT_VERSION:
        due.append(f"installed with kit {installed}, this kit is {KIT_VERSION}")
    elif stamp.get("kit_commit") and stamp.get("kit_commit") != kit_commit():
        notes.append(f"same kit version, different commit: installed {stamp['kit_commit']}, this kit {kit_commit()}")
    if stamp.get("openspec_version") and stamp["openspec_version"] != run(["openspec", "--version"], root, check=False).stdout.strip():
        notes.append(f"installed with OpenSpec {stamp['openspec_version']}; the CLI has changed since, "
                     "so run the overlay check after any `openspec update`")

    # Files the kit owns: they should match this kit byte for byte.
    schema_src = KIT_FILES / "openspec" / "schemas" / "visual-driven"
    pairs = [(f, root / "openspec" / "schemas" / "visual-driven" / f.relative_to(schema_src))
             for f in sorted(schema_src.rglob("*")) if f.is_file()]
    tooling = args.tooling_dir.expanduser().resolve() if args.tooling_dir else (
        resolve_ref(stamp["tooling_dir"], root, folders) if stamp.get("tooling_dir") else root)
    if tooling is None:
        notes.append(f"can't find the tooling folder `{stamp['tooling_dir']}` (pass --tooling-dir or --workspace); "
                     "docs and scripts not compared")
    elif tooling.resolve() != KIT_FILES.resolve():
        pairs += [(KIT_FILES / "docs" / "VSDD.md", tooling / "docs" / "VSDD.md")]
        pairs += [(HERE / n, tooling / "scripts" / "vsdd" / n) for n in SCRIPTS]
        rules = tooling / "docs" / "MERMAID_RULES.md"
        if rules.is_file() and rules.read_bytes() != (KIT_FILES / "docs" / "MERMAID_RULES.md").read_bytes():
            notes.append("docs/MERMAID_RULES.md differs from the kit (fine if it holds project rules; "
                         "merge kit additions by hand)")
    stale_files = []
    for src, dst in pairs:
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            try:
                stale_files.append(dst.relative_to(root).as_posix())
            except ValueError:
                stale_files.append(str(dst))
    if stale_files:
        due.append(f"files differ from this kit: {', '.join(stale_files)}")

    config = root / "openspec" / "config.yaml"
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    missing = sorted({f"{k}.{s}" for k, s, marker in CONFIG_MARKERS if marker not in (top_level_block(text, k) or "")})
    if missing:
        due.append(f"config.yaml lacks VSDD entries: {', '.join(missing)}")

    extra = [p for p in (resolve_ref(r, root, folders) for r in stamp.get("extra_dirs", [])) if p is not None]
    extra += [d.expanduser().resolve() for d in args.extra_dir]
    cmd = [sys.executable, str(HERE / "install_overlay.py"), "--root", str(root), "--check"]
    for d in extra:
        cmd += ["--extra-dir", str(d)]
    check = run(cmd, root, check=False)
    if check.returncode != 0:
        due.append("overlay missing or stale:\n" + "\n".join(
            f"      {l.strip()}" for l in check.stdout.splitlines() if l.lstrip().startswith(("x", "!"))))

    tools = ",".join(stamp.get("tools") or []) or "<TOOLS>"
    upgrade = [f"python3 {HERE / 'vsdd_install.py'}", f"--root {root}", f"--tools {tools}"]
    upgrade += [f"--extra-dir {d}" for d in extra]
    if stamp.get("tooling_dir") and tooling is not None:
        upgrade.append(f"--tooling-dir {tooling}")
    result = {"status": "upgrade-due" if due else "up-to-date", "kit_version": KIT_VERSION,
              "kit_commit": kit_commit(), "installed": stamp or None, "due": due, "notes": notes,
              "upgrade_command": " ".join(upgrade) if due else None}
    if args.json:
        print(json.dumps(result, indent=2))
        return 1 if due else 0
    print(f"This kit:   {KIT_VERSION}" + (f" ({result['kit_commit']})" if result["kit_commit"] else ""))
    print(f"Installed:  {installed or 'unknown'}" + (f" ({stamp['kit_commit']})" if stamp.get("kit_commit") else ""))
    for n in notes:
        print(f"  note: {n}")
    if not due:
        print("Up to date.")
        return 0
    print("Upgrade due:")
    print("\n".join(f"  - {d}" for d in due))
    print(f"To upgrade (on a branch), re-run the installer:\n  {result['upgrade_command']}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, required=True, help="the project to install into")
    ap.add_argument("--tools",
                    help="comma-separated OpenSpec tool ids, e.g. claude,qwen; `none` when the commands "
                         "come from a shared workspace folder (--extra-dir)")
    ap.add_argument("--extra-dir", type=Path, action="append", default=[],
                    help="a home-folder tool's folder the user approved (e.g. ~/.minimax). Repeatable")
    ap.add_argument("--allow-dirty", action="store_true", help="continue with uncommitted changes")
    ap.add_argument("--no-branch", action="store_true", help="don't create the vsdd-install branch")
    ap.add_argument("--update", choices=("safe", "plain"),
                    help="when `openspec update` would delete workflows: keep them (safe) or accept (plain)")
    ap.add_argument("--custom-schema", choices=("switch", "keep"),
                    help="when the project has a custom schema: switch to visual-driven, or keep it")
    ap.add_argument("--workspace", type=Path, action="append", default=[],
                    help="a .code-workspace file to check for shared folders (default: next to or above --root)")
    ap.add_argument("--tooling-dir", type=Path,
                    help="put the kit's docs and scripts in this folder (e.g. a shared workspace folder) "
                         "instead of the project")
    ap.add_argument("--leave-shared", action="store_true",
                    help="don't patch shared workspace folders that hold OpenSpec commands")
    ap.add_argument("--agents-md", choices=("full", "pointer", "skip"),
                    help="how VSDD appears in an existing AGENTS.md: routing section, one-line pointer, or not at all")
    ap.add_argument("--dry-run", action="store_true", help="check for decisions and print the plan only")
    ap.add_argument("--json", action="store_true", help="machine-readable result")
    ap.add_argument("--status", action="store_true",
                    help="compare the install with this kit and say whether an upgrade is due; changes nothing")
    args = ap.parse_args()
    if args.status:
        return show_status(args)
    if not args.tools:
        ap.error("--tools is required (except with --status)")

    inst = Installer(args)
    status, message = 0, ""
    try:
        inst.run_all()
    except Stop as e:
        status, message = 3, f"Stopped before changing anything - decisions needed:\n{e}"
    except Failed as e:
        status, message = 1, f"A step failed: {e}"
    result = {"status": {0: "ok", 1: "failed", 3: "needs-decision"}[status],
              "openspec_version": getattr(inst, "version", None), "dry_run": args.dry_run,
              "plan": inst.plan, "done": inst.done, "todo": inst.todo, "message": message}
    if args.json:
        print(json.dumps(result, indent=2))
        return status
    if args.dry_run and status == 0:
        print("Plan (dry run, nothing changed):")
        print("\n".join(f"  {p}" for p in inst.plan))
    if inst.done:
        print("Done:")
        print("\n".join(f"  {d}" for d in inst.done))
    if message:
        print(message, file=sys.stderr)
    if inst.todo:
        print("Left for you (the agent), in order:")
        print("\n".join(f"  - {t}" for t in inst.todo))
    if status == 1 and inst.done:
        print("Steps above 'A step failed' completed. Continue from the failed step using the kit's docs/SETUP-REFERENCE.md.",
              file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
