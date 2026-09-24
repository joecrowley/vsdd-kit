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

step "5. overlay"
python3 scripts/vsdd/install_overlay.py --check >/dev/null && fail "--check should fail before overlay" || pass "--check detects missing overlay"
python3 scripts/vsdd/install_overlay.py >/dev/null || fail "overlay apply"
python3 scripts/vsdd/install_overlay.py --check >/dev/null && pass "overlay applied" || fail "overlay check after apply"
before="$(cat .*/skills/openspec-archive-change/SKILL.md | cksum)"
python3 scripts/vsdd/install_overlay.py >/dev/null
[ "$before" = "$(cat .*/skills/openspec-archive-change/SKILL.md | cksum)" ] && pass "overlay idempotent" || fail "overlay not idempotent"
grep -q "vsdd:wrapper" .*/command*/opsx*archive* .*/commands/opsx/archive.md 2>/dev/null && pass "commands wrapped" || fail "commands not wrapped"
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

printf '\n\033[32mAll checks passed.\033[0m\n'
[ -n "${KEEP:-}" ] && echo "Project kept at $ROOT"
exit 0
