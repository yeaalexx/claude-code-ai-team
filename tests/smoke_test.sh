#!/usr/bin/env bash
# Smoke tests -- validates repo structure and script syntax.
# Run: bash tests/smoke_test.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

# Detect working Python (python3 may be a non-functional shim on Windows)
PYTHON_CMD=""
for _try_cmd in python3 python; do
    if "$_try_cmd" -c "import sys" >/dev/null 2>&1; then
        PYTHON_CMD="$_try_cmd"
        break
    fi
done

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "Running smoke tests..."
echo ""

# Repo structure
check "setup.sh exists and is executable"    test -x "$SCRIPT_DIR/setup.sh"
check "setup.ps1 exists"                     test -f "$SCRIPT_DIR/setup.ps1"
check "requirements.txt exists"              test -f "$SCRIPT_DIR/requirements.txt"
check "scripts/update_creds.py exists"       test -f "$SCRIPT_DIR/scripts/update_creds.py"
check "defaults/global-CLAUDE.md exists"     test -f "$SCRIPT_DIR/defaults/global-CLAUDE.md"
check "defaults/ai-team-knowledge.md exists" test -f "$SCRIPT_DIR/defaults/ai-team-knowledge.md"
check "defaults/AI_TEAM_SYNERGY.md exists"   test -f "$SCRIPT_DIR/defaults/AI_TEAM_SYNERGY.md"
check "CHANGELOG.md exists"                  test -f "$SCRIPT_DIR/CHANGELOG.md"
check "SECURITY.md exists"                   test -f "$SCRIPT_DIR/SECURITY.md"
check "LICENSE exists"                       test -f "$SCRIPT_DIR/LICENSE"

# v2 server module structure
check "server/__init__.py exists"            test -f "$SCRIPT_DIR/server/__init__.py"
check "server/server.py exists"              test -f "$SCRIPT_DIR/server/server.py"
check "server/memory.py exists"              test -f "$SCRIPT_DIR/server/memory.py"
check "server/sessions.py exists"            test -f "$SCRIPT_DIR/server/sessions.py"
check "server/context_builder.py exists"     test -f "$SCRIPT_DIR/server/context_builder.py"
check "server/credentials.template.json"     test -f "$SCRIPT_DIR/server/credentials.template.json"

# Script syntax
check "setup.sh has valid bash syntax"       bash -n "$SCRIPT_DIR/setup.sh"

# Python syntax (run directly to avoid quoting issues with check function)
if [ -n "$PYTHON_CMD" ]; then
    for pyfile in scripts/update_creds.py server/memory.py server/sessions.py server/context_builder.py; do
        if (cd "$SCRIPT_DIR" && "$PYTHON_CMD" -m py_compile "$pyfile") >/dev/null 2>&1; then
            echo "  PASS: $pyfile has valid Python syntax"
            PASS=$((PASS + 1))
        else
            echo "  FAIL: $pyfile has valid Python syntax"
            FAIL=$((FAIL + 1))
        fi
    done
else
    echo "  SKIP: Python syntax checks (no working Python found)"
fi

# requirements.txt pins exact versions (no >= or < ranges)
check "requirements.txt uses pinned versions" bash -c "! grep -E '>|<' '$SCRIPT_DIR/requirements.txt'"

# .gitignore includes credentials
check ".gitignore blocks credentials.json"   grep -q "credentials.json" "$SCRIPT_DIR/.gitignore"

# Defaults contain expected content
check "global-CLAUDE.md has AI Team section" grep -q "AI Team Collaboration" "$SCRIPT_DIR/defaults/global-CLAUDE.md"
check "global-CLAUDE.md has memory sync"     grep -q "grok_memory_sync" "$SCRIPT_DIR/defaults/global-CLAUDE.md"
check "global-CLAUDE.md has grok_collaborate" grep -q "grok_collaborate" "$SCRIPT_DIR/defaults/global-CLAUDE.md"
check "AI_TEAM_SYNERGY.md has Protocol"      grep -q "Protocol" "$SCRIPT_DIR/defaults/AI_TEAM_SYNERGY.md"
check "AI_TEAM_SYNERGY.md has v2 tools"      grep -q "grok_execute_task" "$SCRIPT_DIR/defaults/AI_TEAM_SYNERGY.md"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
