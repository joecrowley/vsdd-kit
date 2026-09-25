#!/usr/bin/env bash
# End-to-end smoke test for the VSDD kit.
# Creates a throwaway project, runs the SETUP.md steps non-interactively against the
# installed OpenSpec CLI, and checks every Verify condition. Run it after changing the
# kit or upgrading OpenSpec.
#
#   tests/smoke_test.sh            # tools: claude,opencode,qwen
#   TOOLS=claude tests/smoke_test.sh
#   KEEP=1 tests/smoke_test.sh     # keep the temp project for inspection
#   GLOBAL_PROFILE=1 tests/smoke_test.sh   # use your global OpenSpec profile instead of
#                                          # an isolated one with every workflow enabled
set -euo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="${TOOLS:-claude,opencode,qwen}"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke.XXXXXX")"
XDG="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-cfg.XXXXXX")"
[ -z "${KEEP:-}" ] && trap 'rm -rf "$ROOT" "$XDG"' EXIT

# Isolated OpenSpec global config with every workflow, so the result doesn't depend
# on the machine's profile and every overlay patch is exercised. Unknown workflow ids
# are ignored by older CLIs.
if [ -z "${GLOBAL_PROFILE:-}" ]; then
  mkdir -p "$XDG/openspec"
  cat > "$XDG/openspec/config.json" <<'JSON'
{"featureFlags":{},"profile":"custom","delivery":"both","telemetry":{"noticeSeen":true},
 "workflows":["propose","explore","new","continue","update","ff","apply","sync","archive","bulk-archive","verify","onboard"]}
JSON
  export XDG_CONFIG_HOME="$XDG"
fi

pass() { printf '  \033[32mok\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; exit 1; }
step() { printf '\n== %s\n' "$1"; }

step "Preflight"
command -v openspec >/dev/null || fail "openspec CLI not installed (npm i -g @fission-ai/openspec)"
command -v python3 >/dev/null || fail "python3 not installed"
echo "  openspec $(openspec --version), $(python3 --version), tools=$TOOLS, root=$ROOT"
HAVE_MMDC=0; command -v mmdc >/dev/null && HAVE_MMDC=1

cd "$ROOT"; git init -q

step "1. openspec init"
openspec init --tools "$TOOLS" . </dev/null >/dev/null 2>&1 || fail "openspec init"
ls -d .*/skills/openspec-propose >/dev/null 2>&1 && pass "stock skills generated" || fail "no stock skills"
echo "  info  skills per tool: $(ls -d .claude/skills/openspec-* .opencode/skills/openspec-* .qwen/skills/openspec-* 2>/dev/null | wc -l | tr -d ' ') total"

step "2. copy kit files"
mkdir -p openspec/schemas docs scripts/vsdd
cp -R "$KIT"/files/openspec/schemas/visual-driven openspec/schemas/
cp "$KIT"/files/docs/VSDD.md "$KIT"/files/docs/MERMAID_RULES.md docs/
cp "$KIT"/files/scripts/vsdd/*.py scripts/vsdd/
openspec schema validate visual-driven 2>&1 | grep -q "is valid" && pass "schema valid" || fail "schema invalid"
openspec schemas 2>/dev/null | grep -q visual-driven && pass "schema listed" || fail "schema not listed"

step "3. config.yaml"
cp "$KIT"/files/openspec/config.yaml.example openspec/config.yaml
openspec new change vsdd-smoke-test >/dev/null 2>&1 || fail "openspec new change"
grep -q "schema: visual-driven" openspec/changes/vsdd-smoke-test/.openspec.yaml && pass "change uses visual-driven" || fail "wrong schema on change"
OUT="$(openspec instructions diagrams --change vsdd-smoke-test 2>/dev/null)"
for pat in "<project_context>" "<rules>" "MERMAID_RULES"; do
  grep -q "$pat" <<<"$OUT" && pass "diagrams instructions contain $pat" || fail "missing $pat in instructions"
done
openspec instructions design --change vsdd-smoke-test 2>/dev/null | grep -q "decisions.md" \
  && pass "design instructions point at decisions.md" || fail "design instructions miss decisions.md"
if openspec instructions --help 2>&1 | grep -q archive; then
  openspec instructions archive --change vsdd-smoke-test --json 2>/dev/null | grep -q "VSDD" \
    && pass "operations.archive guidance delivered by CLI" || fail "operations.archive guidance missing"
  openspec instructions apply --change vsdd-smoke-test --json 2>/dev/null | grep -q "VSDD" \
    && pass "operations.apply guidance delivered by CLI" || fail "operations.apply guidance missing"
else
  echo "  skip  operations guidance (this OpenSpec has no 'instructions archive')"
fi

step "4. agent files"
cp "$KIT"/files/agents/AGENTS.vsdd.md AGENTS.md
grep -q "docs/VSDD.md" AGENTS.md && pass "AGENTS.md routes to docs/VSDD.md" || fail "AGENTS.md snippet"
grep -q "decisions.md" AGENTS.md && pass "AGENTS.md routes to decisions.md" || fail "AGENTS.md misses decisions.md"

step "5. overlay"
python3 scripts/vsdd/install_overlay.py --check >/dev/null && fail "--check should fail before overlay" || pass "--check detects missing overlay"
python3 scripts/vsdd/install_overlay.py >/dev/null || fail "overlay apply"
python3 scripts/vsdd/install_overlay.py --check >/dev/null && pass "overlay applied" || fail "overlay check after apply"
before="$(cat .*/skills/openspec-archive-change/SKILL.md | cksum)"
python3 scripts/vsdd/install_overlay.py >/dev/null
[ "$before" = "$(cat .*/skills/openspec-archive-change/SKILL.md | cksum)" ] && pass "overlay idempotent" || fail "overlay not idempotent"
grep -q "vsdd:wrapper" .*/command*/opsx*archive* .*/commands/opsx/archive.md 2>/dev/null && pass "commands wrapped" || fail "commands not wrapped"
grep -q "vsdd:archive-decisions" .*/skills/openspec-archive-change/SKILL.md && grep -q "vsdd:gen-decisions" .*/skills/openspec-propose/SKILL.md \
  && pass "decisions steps patched into propose and archive" || fail "decisions steps missing"
for s in propose apply-change verify-change archive-change continue-change ff-change update-change bulk-archive-change; do
  for f in .*/skills/openspec-$s/SKILL.md; do
    [ -e "$f" ] || continue
    grep -q "vsdd:" "$f" && pass "patched $f" || fail "not patched: $f"
  done
done

step "6. seed Source of Truth"
mkdir -p openspec/specs/architecture
cp "$KIT"/files/openspec/specs/architecture/diagrams.md.example openspec/specs/architecture/diagrams.md
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "seed diagrams lint clean" || fail "seed diagrams lint"
DEC=openspec/specs/architecture/decisions.md
cp "$KIT"/files/openspec/specs/architecture/decisions.md.example "$DEC"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "decisions log validates" || fail "decisions log rejected"
sed -i.bak '/\*\*Rule:\*\*/d' "$DEC" && rm -f "$DEC.bak"
grep -q "needs \*\*Rule:\*\*" <<<"$(python3 scripts/vsdd/validate_mermaid.py 2>&1 || true)" && pass "decision without a Rule caught" || fail "decision without a Rule not caught"
rm -f "$DEC"
if [ "$HAVE_MMDC" = 1 ]; then
  python3 scripts/vsdd/validate_mermaid.py --render >/dev/null && pass "seed diagrams render" || fail "seed diagrams render"
else
  echo "  skip  render check (mmdc not installed)"
fi

step "7. CI workflow"
python3 - "$KIT/files/ci/github/vsdd.yml" <<'EOF' && pass "workflow YAML parses" || fail "workflow YAML"
import sys
try:
    import yaml
except ImportError:
    print("  skip  PyYAML not installed"); sys.exit(0)
yaml.safe_load(open(sys.argv[1]))
EOF

step "8. change validation"
C=openspec/changes/vsdd-smoke-test/diagrams.md
SOT=openspec/specs/architecture/diagrams.md
SEC="$(sed -n '/^## Module Hierarchy/,/^## End-to-End/p' $SOT | sed '1d;$d')"
AFTER="$(printf '%s\n' "$SEC" | sed 's/^    DOMAIN --> CORE\(.*\)$/    DOMAIN --> CORE\1\n    UI --> CORE/')"
write_change() {  # $1 = action for Module Hierarchy, $2 = include After (1/0), $3 = Before text
  {
    printf '## Diagram needed?\n\nYES - smoke test\n\n## Placement\n\n'
    printf '| Stable name | Source of Truth file | Action |\n|---|---|---|\n'
    printf '| Module Hierarchy | specs/architecture/diagrams.md | %s |\n' "$1"
    printf '| Smoke Flow | specs/smoke-cap/diagrams.md | add |\n\n'
    printf '## Before State\n\n### Module Hierarchy\n%s\n\n## After State\n\n' "$3"
    [ "$2" = 1 ] && printf '### Module Hierarchy\n%s\n\n' "$AFTER"
    printf '### Smoke Flow\nSmoke test flow.\n\n```mermaid\nflowchart LR\n    S["smoke"] --> T["test"]\n```\n'
  } > "$C"
}
write_change update 1 "$SEC"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "valid YES-gate change (update + add) passes" || fail "valid change rejected"
sed -i.bak 's/^flowchart TD$/flowchart/' "$C" && rm -f "$C.bak"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && fail "missing direction not caught" || pass "missing flowchart direction caught"
write_change update 1 "$(printf '%s\n' "$SEC" | sed 's/^Dependency direction/Dependency-direction/')"
grep -q "not a verbatim copy" <<<"$(python3 scripts/vsdd/validate_mermaid.py 2>&1 || true)" && pass "non-verbatim Before caught" || fail "non-verbatim Before not caught"
write_change remove 1 "$SEC"
grep -q "must not have an After" <<<"$(python3 scripts/vsdd/validate_mermaid.py 2>&1 || true)" && pass "remove with After section caught" || fail "remove with After not caught"
printf '## Diagram needed?\n\nYES - x\n\n## Before State\n\n## After State\n' > "$C"
grep -q "requires '## Placement'" <<<"$(python3 scripts/vsdd/validate_mermaid.py 2>&1 || true)" && pass "missing Placement caught" || fail "missing Placement not caught"
printf '## Diagram needed?\n\nmaybe\n' > "$C"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && fail "bad gate not caught" || pass "bad gate caught"
printf '## Diagram needed?\n\nNO - smoke test\n' > "$C"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "NO gate passes" || fail "NO gate rejected"
write_owner() {  # $1 = Why here text ('' = none): the change creates smoke-cap but adds its flow to architecture
  mkdir -p openspec/changes/vsdd-smoke-test/specs/smoke-cap
  printf '## Diagram needed?\n\nYES - ownership\n\n## Placement\n\n| Stable name | Source of Truth file | Action | Why here |\n|---|---|---|---|\n'  > "$C"
  printf '| Smoke Flow | specs/architecture/diagrams.md | add | %s |\n\n## Before State\n\n## After State\n\n' "$1" >> "$C"
  printf '### Smoke Flow\nSmoke test flow.\n\n```mermaid\nflowchart LR\n    S["smoke"] --> T["test"]\n```\n' >> "$C"
}
write_owner ""
grep -q "Why here" <<<"$(python3 scripts/vsdd/validate_mermaid.py 2>&1 || true)" && pass "architecture add without a reason caught" || fail "architecture add without a reason not caught"
write_owner "spans smoke-cap and reading"
OUT="$(python3 scripts/vsdd/validate_mermaid.py 2>&1)" && grep -q "warning: this change creates smoke-cap" <<<"$OUT" \
  && pass "new-capability flow in architecture file passes with a warning" || fail "ownership warning missing, or reason not accepted"
rm -rf openspec/changes/vsdd-smoke-test/specs

step "8b. archive merge (merge_diagrams.py)"
cp "$SOT" "$ROOT/sot.bak"
write_change update 1 "$SEC"
python3 scripts/vsdd/merge_diagrams.py openspec/changes/vsdd-smoke-test --dry-run >/dev/null && cmp -s "$SOT" "$ROOT/sot.bak" \
  && pass "dry run writes nothing" || fail "dry run changed files"
python3 scripts/vsdd/merge_diagrams.py openspec/changes/vsdd-smoke-test >/dev/null || fail "merge failed"
grep -q "UI --> CORE" "$SOT" && pass "update merged into architecture" || fail "update not merged"
grep -q "^## End-to-End Data Flow" "$SOT" && pass "untouched section kept" || fail "untouched section lost"
[ -f openspec/specs/smoke-cap/diagrams.md ] && grep -q "^## Smoke Flow" openspec/specs/smoke-cap/diagrams.md \
  && pass "add created the capability diagrams file" || fail "add did not create the file"
python3 scripts/vsdd/merge_diagrams.py openspec/changes/vsdd-smoke-test | grep -q "already merged" \
  && pass "second merge is a no-op" || fail "second merge not idempotent"
MH="$(sed -n '/^## Module Hierarchy/,/^## End-to-End/p' $SOT | sed '1d;$d')"
{ printf '## Diagram needed?\n\nYES - move\n\n## Placement\n\n| Stable name | Source of Truth file | Action |\n|---|---|---|\n'
  printf '| Module Hierarchy | specs/smoke-cap/diagrams.md | move from specs/architecture/diagrams.md |\n| Smoke Flow | specs/smoke-cap/diagrams.md | remove |\n\n'
  printf '## Before State\n\n### Module Hierarchy\n%s\n\n### Smoke Flow\n%s\n\n## After State\n\n### Module Hierarchy\n%s\n' \
    "$MH" "$(sed -n '/^## Smoke Flow/,$p' openspec/specs/smoke-cap/diagrams.md | sed '1d')" "$MH"; } > "$C"
python3 scripts/vsdd/merge_diagrams.py openspec/changes/vsdd-smoke-test >/dev/null || fail "move/remove merge failed"
! grep -q "^## Module Hierarchy" "$SOT" && grep -q "^## Module Hierarchy" openspec/specs/smoke-cap/diagrams.md \
  && ! grep -q "^## Smoke Flow" openspec/specs/smoke-cap/diagrams.md \
  && pass "move and remove applied" || fail "move/remove not applied"
cp "$ROOT/sot.bak" "$SOT"; rm -rf openspec/specs/smoke-cap
write_change update 1 "$SEC"
sed -i.bak 's/^Dependency direction/Dependency-direction/' "$SOT" && rm -f "$SOT.bak"
python3 scripts/vsdd/merge_diagrams.py openspec/changes/vsdd-smoke-test >/dev/null 2>&1 && fail "conflict not refused" || pass "conflict refused (Source of Truth changed after proposal)"
cp "$ROOT/sot.bak" "$SOT"; rm -f "$ROOT/sot.bak"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "Source of Truth restored and valid" || fail "restore failed"

step "Maintenance: openspec update wipes overlay"
openspec update --force . </dev/null >/dev/null 2>&1 || fail "openspec update"
python3 scripts/vsdd/install_overlay.py --check >/dev/null && fail "wipe not detected" || pass "wipe detected by --check"
python3 scripts/vsdd/install_overlay.py >/dev/null && python3 scripts/vsdd/install_overlay.py --check >/dev/null && pass "overlay restored" || fail "overlay restore"

step "Existing OpenSpec: preflight, safe update, adding a tool"
ROOT2="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-existing.XXXXXX")"
XFULL="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-full.XXXXXX")"
XLESS="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-less.XXXXXX")"
[ -z "${KEEP:-}" ] && trap 'rm -rf "$ROOT" "$XDG" "$ROOT2" "$XFULL" "$XLESS"' EXIT
mkdir -p "$XFULL/openspec" "$XLESS/openspec"
printf '{"profile":"custom","telemetry":{"noticeSeen":true},"workflows":["propose","explore","new","continue","update","ff","apply","sync","archive","bulk-archive","verify","onboard"]}\n' > "$XFULL/openspec/config.json"
printf '{"profile":"custom","telemetry":{"noticeSeen":true},"workflows":["propose","explore","apply","sync","archive","verify"]}\n' > "$XLESS/openspec/config.json"
PRE="$KIT/files/scripts/vsdd/openspec_preflight.py"
cd "$ROOT2"; git init -q
XDG_CONFIG_HOME="$XFULL" openspec init --tools claude . </dev/null >/dev/null 2>&1 || fail "init (full profile)"
printf 'schema: team-schema\ncontext: |\n  existing project\n' > openspec/config.yaml
mkdir -p openspec/changes/old-change && printf 'schema: spec-driven\ncreated: 2026-01-01\n' > openspec/changes/old-change/.openspec.yaml
BEFORE_N=$(ls -d .claude/skills/openspec-* | wc -l | tr -d ' ')
cp openspec/config.yaml "$ROOT2/config.bak"
REPORT="$(XDG_CONFIG_HOME="$XLESS" python3 "$PRE" --tools claude,opencode --json || true)"
field() { python3 -c "import json,sys;d=json.loads(sys.argv[1]);print(d$2)" "$REPORT"; }
PREDICTED="$(field "$REPORT" "['update_would_remove']")"
[ "$PREDICTED" != "[]" ] && pass "preflight predicts deletions: $PREDICTED" || fail "preflight predicted no deletions"
[ "$(field "$REPORT" "['tools_to_add']")" = "['opencode']" ] && pass "preflight reports tool to add: opencode" || fail "tools_to_add wrong"
[ "$(field "$REPORT" "['custom_schema']")" = "True" ] && pass "preflight flags custom schema" || fail "custom schema not flagged"
[ "$(field "$REPORT" "['in_flight_changes'][0]['schema']")" = "spec-driven" ] && pass "preflight lists in-flight change with its schema" || fail "in-flight change not reported"
XDG_CONFIG_HOME="$XLESS" python3 "$PRE" --safe-update >/dev/null || fail "safe update failed"
[ "$(ls -d .claude/skills/openspec-* | wc -l | tr -d ' ')" = "$BEFORE_N" ] && pass "--safe-update kept all $BEFORE_N workflows" || fail "--safe-update lost workflows"
cmp -s openspec/config.yaml "$ROOT2/config.bak" && pass "--safe-update left config.yaml (custom schema) alone" || fail "config.yaml changed by update"
XDG_CONFIG_HOME="$XLESS" openspec init --tools opencode . </dev/null >/dev/null 2>&1 || fail "init --tools opencode"
[ -d .opencode/skills/openspec-propose ] && [ "$(ls -d .claude/skills/openspec-* | wc -l | tr -d ' ')" = "$BEFORE_N" ] \
  && cmp -s openspec/config.yaml "$ROOT2/config.bak" \
  && pass "init on existing project added opencode, kept claude skills and config" || fail "init --tools changed existing setup"
XDG_CONFIG_HOME="$XLESS" openspec update . </dev/null >/dev/null 2>&1 || fail "plain update"
GONE="$(python3 -c "
import sys; from pathlib import Path
sys.path.insert(0, '$KIT/files/scripts/vsdd'); from openspec_preflight import installed_skills
left = installed_skills(Path('.')).get('.claude', set())
print(sorted(set($PREDICTED) - left) == sorted($PREDICTED) and not (set($PREDICTED) & left))")"
[ "$GONE" = "True" ] && pass "plain update deleted exactly the predicted workflows (the risk is real)" || fail "prediction did not match plain update"
cd "$ROOT"

step "Rollback: branch + snapshot restores everything"
ROOT3="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-rollback.XXXXXX")"
XR="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-rbcfg.XXXXXX")"
SNAP="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-snap.XXXXXX")/snap"
[ -z "${KEEP:-}" ] && trap 'rm -rf "$ROOT" "$XDG" "$ROOT2" "$XFULL" "$XLESS" "$ROOT3" "$XR" "$(dirname "$SNAP")"' EXIT
mkdir -p "$XR/openspec"
printf '{"profile":"custom","telemetry":{"noticeSeen":true},"workflows":["propose","explore","apply","sync","archive","verify"]}\n' > "$XR/openspec/config.json"
SNAPPY="$KIT/files/scripts/vsdd/vsdd_snapshot.py"
cd "$ROOT3"; git init -q -b main
printf '.claude/\n' > .gitignore
XDG_CONFIG_HOME="$XR" openspec init --tools claude . </dev/null >/dev/null 2>&1 || fail "init (rollback project)"
git add -A && git -c user.name=t -c user.email=t@t commit -qm base
state() { (cd "$ROOT3" && find . -path ./.git -prune -o -type f -print0 | sort -z | xargs -0 shasum | shasum; shasum "$XR/openspec/config.json" | cut -c1-40); }
BEFORE="$(state)"
git switch -q -c vsdd-install
XDG_CONFIG_HOME="$XR" python3 "$SNAPPY" save --out "$SNAP" >/dev/null && [ -f "$SNAP/manifest.json" ] \
  && pass "snapshot saved (untracked .claude + global config)" || fail "snapshot save"
mkdir -p openspec/schemas docs scripts/vsdd
cp -R "$KIT"/files/openspec/schemas/visual-driven openspec/schemas/
cp "$KIT"/files/docs/VSDD.md "$KIT"/files/docs/MERMAID_RULES.md docs/
cp "$KIT"/files/scripts/vsdd/*.py scripts/vsdd/
cp "$KIT"/files/openspec/config.yaml.example openspec/config.yaml
cp "$KIT"/files/agents/AGENTS.vsdd.md AGENTS.md; printf '@AGENTS.md\n' > CLAUDE.md
python3 scripts/vsdd/install_overlay.py >/dev/null || fail "overlay (rollback project)"
git add -A && git -c user.name=t -c user.email=t@t commit -qm "install VSDD"
printf '{"profile":"core"}\n' > "$XR/openspec/config.json"
[ "$(state)" != "$BEFORE" ] && pass "install changed tracked, untracked and global state" || fail "install changed nothing?"
git switch -q main
XDG_CONFIG_HOME="$XR" python3 "$SNAPPY" restore "$SNAP" --yes --restore-global >/dev/null || fail "snapshot restore"
git branch -q -D vsdd-install
[ "$(state)" = "$BEFORE" ] && pass "rollback is byte-identical (working tree + global config)" || fail "rollback left differences"
XDG_CONFIG_HOME="$XR" python3 "$SNAPPY" restore "$SNAP" --dry-run | grep -q "nothing to restore" \
  && pass "second restore: nothing to restore" || fail "restore not idempotent"
cd "$ROOT"

step "All OpenSpec tools: overlay + preflight (sandboxed HOME)"
ROOT4="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-alltools.XXXXXX")"
FH="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-home.XXXXXX")"
[ -z "${KEEP:-}" ] && trap 'rm -rf "$ROOT" "$XDG" "$ROOT2" "$XFULL" "$XLESS" "$ROOT3" "$XR" "$(dirname "$SNAP")" "$ROOT4" "$FH"' EXIT
mkdir -p "$FH/.config/openspec"
cp "$XFULL/openspec/config.json" "$FH/.config/openspec/config.json"
cd "$ROOT4"; git init -q
if HOME="$FH" XDG_CONFIG_HOME="$FH/.config" CODEX_HOME="$FH/.codex" openspec init --tools all . </dev/null >/dev/null 2>&1; then
  NTOOLS=$(find . -path ./.git -prune -o -type d -name openspec-propose -print | wc -l | tr -d ' ')
  pass "openspec init --tools all: $NTOOLS project tool folders"
  HOME="$FH" python3 "$KIT/files/scripts/vsdd/install_overlay.py" --extra-dir "$FH/.minimax" >/dev/null || fail "overlay (all tools)"
  HOME="$FH" python3 "$KIT/files/scripts/vsdd/install_overlay.py" --check --extra-dir "$FH/.minimax" >/dev/null \
    && pass "overlay --check passes for every tool (incl. home-folder MiniMax)" || fail "overlay --check (all tools)"
  # The 8 commands whose skills VSDD patches (explore/sync/new/onboard stay stock).
  WRAPPED_RE='(opsx-|/opsx/)(propose|continue|ff|update|apply|verify|archive|bulk-archive)\.(md|prompt\.md|prompt|toml)$'
  CMDS=$(find . -path ./.git -prune -o -type f -print | grep -E "$WRAPPED_RE")
  NCMD=$(printf '%s\n' "$CMDS" | grep -c . || true)
  UNWRAPPED=0
  while read -r f; do
    if [ -n "$f" ] && ! grep -q "vsdd:wrapper" "$f"; then UNWRAPPED=$((UNWRAPPED + 1)); fi
  done <<<"$CMDS"
  [ "$UNWRAPPED" = 0 ] && [ "$NCMD" -gt 0 ] && pass "all $NCMD VSDD command files are wrappers" || fail "$UNWRAPPED of $NCMD command files not wrapped"
  HOME="$FH" XDG_CONFIG_HOME="$FH/.config" python3 "$KIT/files/scripts/vsdd/openspec_preflight.py" | grep -q "not an OpenSpec tool folder" \
    && fail "preflight mislabels an OpenSpec tool folder" || pass "preflight recognises every tool folder"
else
  echo "  skip  this OpenSpec has no '--tools all'"
fi
cd "$ROOT"

step "One-shot installer (vsdd_install.py)"
ROOT5="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-inst.XXXXXX")"
IH="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-ihome.XXXXXX")"
[ -z "${KEEP:-}" ] && trap 'rm -rf "$ROOT" "$XDG" "$ROOT2" "$XFULL" "$XLESS" "$ROOT3" "$XR" "$(dirname "$SNAP")" "$ROOT4" "$FH" "$ROOT5" "$IH"' EXIT
INST="$KIT/files/scripts/vsdd/vsdd_install.py"
cd "$ROOT5"; git init -q; echo "# demo" > README.md; git add -A; git -c user.email=s@t -c user.name=smoke commit -qm base
echo "stray" > stray.txt
rc=0; HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" >/dev/null 2>&1 || rc=$?
[ "$rc" = 3 ] && [ ! -d openspec ] && pass "stops on a dirty tree before changing anything (exit 3)" || fail "dirty tree: exit $rc"
rm stray.txt
HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" --dry-run >/dev/null 2>&1 && [ ! -d openspec ] \
  && [ "$(git branch --show-current)" != vsdd-install ] && pass "dry run changes nothing" || fail "dry run changed something"
OUT="$(HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" 2>&1)" && pass "fresh install (exit 0)" || { echo "$OUT"; fail "installer failed"; }
[ "$(git branch --show-current)" = vsdd-install ] && pass "installed on the vsdd-install branch" || fail "no install branch"
python3 scripts/vsdd/install_overlay.py --check >/dev/null && pass "installer: overlay OK" || fail "installer: overlay check"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "installer: validator OK" || fail "installer: validator"
CLAUDE_OK=1; [[ "$TOOLS" == *claude* ]] && ! grep -q "@AGENTS.md" CLAUDE.md 2>/dev/null && CLAUDE_OK=0
[ -f openspec/specs/architecture/decisions.md ] && [ ! -d openspec/changes/vsdd-install-check ] && [ "$CLAUDE_OK" = 1 ] \
  && pass "installer: decisions log, no leftover check change, CLAUDE.md" || fail "installer: files"
grep -q "fill in \`context:\`" <<<"$OUT" && grep -q "Step 6: seed" <<<"$OUT" \
  && pass "installer lists the judgement steps left (context, baseline diagrams)" || fail "installer to-do list"
git add -A; git -c user.email=s@t -c user.name=smoke commit -qm install
NSNAP=$(ls "$IH/.vsdd-snapshots" | wc -l)
HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" >/dev/null 2>&1 && [ -z "$(git status --porcelain)" ] \
  && pass "re-run (upgrade) is idempotent" || fail "re-run changed files: $(git status --porcelain | head -3)"
[ "$(ls "$IH/.vsdd-snapshots" | wc -l)" = "$NSNAP" ] && pass "re-run on the install branch reuses the pre-install snapshot" \
  || fail "re-run took a new snapshot of a half-installed state"
HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" --agents-md pointer >/dev/null 2>&1 \
  && grep -q "vsdd:pointer" AGENTS.md && ! grep -q "^## OpenSpec & Visual" AGENTS.md \
  && pass "--agents-md pointer replaces the section with one line" || fail "--agents-md pointer"
git add -A; git -c user.email=s@t -c user.name=smoke commit -qm pointer
HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" >/dev/null 2>&1 && [ -z "$(git status --porcelain)" ] \
  && pass "re-run keeps the pointer choice" || fail "re-run changed the pointer choice"
ROOT6="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-agents.XXXXXX")"
cd "$ROOT6"; git init -q; printf '# Team rules\n' > AGENTS.md; git add -A; git -c user.email=s@t -c user.name=smoke commit -qm base
rc=0; HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" >/dev/null 2>&1 || rc=$?
[ "$rc" = 3 ] && [ ! -d openspec ] && pass "existing AGENTS.md: asks first (exit 3)" || fail "existing AGENTS.md: exit $rc"
HOME="$IH" python3 "$INST" --root . --tools "$TOOLS" --agents-md skip >/dev/null 2>&1 && [ "$(cat AGENTS.md)" = "# Team rules" ] \
  && pass "--agents-md skip leaves AGENTS.md untouched" || fail "--agents-md skip changed AGENTS.md"
cd "$ROOT"; rm -rf "$ROOT6"
ROOT7="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-custom.XXXXXX")"
cd "$ROOT7"; git init -q; openspec init --tools claude . </dev/null >/dev/null 2>&1
openspec schema fork spec-driven team </dev/null >/dev/null 2>&1 || fail "openspec schema fork"
sed -i.bak 's/^schema: .*/schema: team/' openspec/config.yaml && rm -f openspec/config.yaml.bak
git add -A; git -c user.email=s@t -c user.name=smoke commit -qm base
HOME="$IH" python3 "$INST" --root . --tools claude --custom-schema keep --agents-md skip >/dev/null 2>&1 \
  && grep -q "^schema: team" openspec/config.yaml \
  && pass "--custom-schema keep: installs without a diagrams artifact, schema kept" || fail "--custom-schema keep install"
cd "$ROOT"; rm -rf "$ROOT7"
cd "$ROOT"

step "Shared workspace folder (VS Code multi-root)"
WS="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke-ws.XXXXXX")"
[ -z "${KEEP:-}" ] && trap 'rm -rf "$ROOT" "$XDG" "$ROOT2" "$XFULL" "$XLESS" "$ROOT3" "$XR" "$(dirname "$SNAP")" "$ROOT4" "$FH" "$ROOT5" "$IH" "$WS"' EXIT
mkdir -p "$WS/app" "$WS/shared"
(cd "$WS/shared" && git init -q && openspec init --tools claude . </dev/null >/dev/null 2>&1 && rm -rf openspec)
printf '{\n  // team workspace\n  "folders": [ { "path": "app" }, { "path": "shared" }, ],\n}\n' > "$WS/team.code-workspace"
cd "$WS/app"; git init -q; echo "# app" > README.md; git add -A; git -c user.email=s@t -c user.name=smoke commit -qm base
rc=0; OUT="$(python3 "$KIT/files/scripts/vsdd/openspec_preflight.py" 2>&1)" || rc=$?
[ "$rc" = 1 ] && grep -q "Shared folder: .*STOCK" <<<"$OUT" && pass "preflight finds the stock shared folder via .code-workspace (with comments)" || fail "preflight missed the shared folder"
rc=0; HOME="$IH" python3 "$INST" --root . --tools claude >/dev/null 2>&1 || rc=$?
[ "$rc" = 3 ] && [ ! -d openspec ] && pass "installer asks before patching a shared folder (exit 3)" || fail "shared folder: exit $rc"
HOME="$IH" python3 "$INST" --root . --tools none --extra-dir ../shared >/dev/null 2>&1 && [ ! -d .claude ] \
  && pass "--tools none --extra-dir: OpenSpec without project command copies" || fail "--tools none install"
grep -q "vsdd:guard" ../shared/.claude/skills/openspec-archive-change/SKILL.md && grep -q "vsdd:archive-decisions" ../shared/.claude/skills/openspec-archive-change/SKILL.md \
  && pass "shared skills patched, with the guard" || fail "shared skills not patched"
grep -q 'shared/.claude/skills/openspec-propose/SKILL.md` (in the `shared` folder of this workspace)' ../shared/.claude/commands/opsx/propose.md \
  && pass "shared wrappers name the skill by workspace folder, not an absolute path" || fail "shared wrapper path"
python3 "$KIT/files/scripts/vsdd/openspec_preflight.py" 2>&1 | grep -q "Shared folder: .*VSDD-patched" \
  && pass "preflight reports the shared folder as patched" || fail "preflight after patch"
git add -A; git -c user.email=s@t -c user.name=smoke commit -qm vsdd
HOME="$IH" python3 "$INST" --root . --tools none --extra-dir ../shared --tooling-dir ../shared/vsdd >/dev/null 2>&1 \
  && [ -f ../shared/vsdd/scripts/vsdd/validate_mermaid.py ] && [ -f ../shared/vsdd/docs/VSDD.md ] \
  && grep -q "VSDD tooling: .*shared/vsdd" openspec/config.yaml && grep -q "python3 shared/vsdd/scripts/vsdd/merge_diagrams.py --root app" openspec/config.yaml \
  && pass "--tooling-dir: docs and scripts in the shared folder, config paths workspace-relative" || fail "--tooling-dir"
rm -rf docs scripts
python3 ../shared/vsdd/scripts/vsdd/validate_mermaid.py --root . >/dev/null && python3 ../shared/vsdd/scripts/vsdd/install_overlay.py --root . --extra-dir ../shared --check >/dev/null \
  && pass "--tooling-dir: checks run from the tooling folder with no kit files in the project" || fail "--tooling-dir checks"
KITNAME="$(basename "$KIT")"
printf '{ "folders": [ {"path": "app"}, {"path": "shared"}, {"path": "%s"} ] }\n' "$KIT" > "$WS/team.code-workspace"
KITSTATE="$(git -C "$KIT" status --porcelain -- files)"
git add -A; git -c user.email=s@t -c user.name=smoke commit -qm tooling
HOME="$IH" python3 "$INST" --root . --tools none --extra-dir ../shared --tooling-dir "$KIT/files" >/dev/null 2>&1 \
  && grep -q "python3 $KITNAME/files/scripts/vsdd/merge_diagrams.py --root app" openspec/config.yaml \
  && ! grep -q "shared/vsdd" openspec/config.yaml && [ "$(git -C "$KIT" status --porcelain -- files)" = "$KITSTATE" ] \
  && pass "--tooling-dir <kit>/files: used in place, config repointed from the old tooling folder" || fail "--tooling-dir kit in place"
cd "$ROOT"

printf '\n\033[32mAll checks passed.\033[0m\n'
[ -n "${KEEP:-}" ] && echo "Project kept at $ROOT"
exit 0
