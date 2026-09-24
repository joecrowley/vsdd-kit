#!/usr/bin/env bash
# End-to-end smoke test for the VSDD kit.
# Creates a throwaway project, runs the SETUP.md steps non-interactively against the
# installed OpenSpec CLI, and checks every Verify condition. Run it after changing the
# kit or upgrading OpenSpec.
#
#   tests/smoke_test.sh            # tools: claude,opencode,qwen
#   TOOLS=claude tests/smoke_test.sh
#   KEEP=1 tests/smoke_test.sh     # keep the temp project for inspection
set -euo pipefail

KIT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="${TOOLS:-claude,opencode,qwen}"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/vsdd-smoke.XXXXXX")"
[ -z "${KEEP:-}" ] && trap 'rm -rf "$ROOT"' EXIT

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
SEC="$(sed -n '/^## Module Hierarchy/,/^## End-to-End/p' openspec/specs/architecture/diagrams.md | sed '1d;$d')"
{ printf '## Diagram needed?\n\nYES - smoke test\n\n## Before State\n\n### Module Hierarchy\n%s\n\n## After State\n\n### Module Hierarchy\n%s\n' "$SEC" "$SEC"; } > "$C"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "valid YES-gate change passes" || fail "valid change rejected"
sed -i.bak 's/^flowchart TD$/flowchart/' "$C" && rm -f "$C.bak"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && fail "missing direction not caught" || pass "missing flowchart direction caught"
printf '## Diagram needed?\n\nmaybe\n' > "$C"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && fail "bad gate not caught" || pass "bad gate caught"
printf '## Diagram needed?\n\nNO - smoke test\n' > "$C"
python3 scripts/vsdd/validate_mermaid.py >/dev/null && pass "NO gate passes" || fail "NO gate rejected"

step "Maintenance: openspec update wipes overlay"
openspec update --force . </dev/null >/dev/null 2>&1 || fail "openspec update"
python3 scripts/vsdd/install_overlay.py --check >/dev/null && fail "wipe not detected" || pass "wipe detected by --check"
python3 scripts/vsdd/install_overlay.py >/dev/null && python3 scripts/vsdd/install_overlay.py --check >/dev/null && pass "overlay restored" || fail "overlay restore"

printf '\n\033[32mAll checks passed.\033[0m\n'
[ -n "${KEEP:-}" ] && echo "Project kept at $ROOT"
exit 0
