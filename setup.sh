#!/usr/bin/env bash
# Claude Code AI Team Setup Script (macOS / Linux)
# Usage: ./setup.sh [--uninstall]
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MCP_SERVER_SHA="b66b56f33fc99cf359cc797c4591589323d0ccc5"

MCP_DIR="$HOME/.claude-mcp-servers/multi-ai-collab"
CLAUDE_DIR="$HOME/.claude"

trap 'echo -e "\n${RED}Setup interrupted. Re-run to complete.${NC}"; exit 1' INT TERM

# -- Functions -----------------------------------------------------------------

configure_provider() {
    local provider="$1" model="$2" key_url="$3"
    read -r -s -p "Enter your API key (from $key_url): " api_key
    echo ""
    if [ -z "$api_key" ]; then
        echo -e "${RED}  No API key entered. Skipping $provider.${NC}"
        return
    fi
    printf '%s' "$api_key" | \
        CREDS_FILE="$CREDS_FILE" PROVIDER="$provider" MODEL="$model" \
        "$PYTHON_CMD" "$SCRIPT_DIR/scripts/update_creds.py"
    chmod 600 "$CREDS_FILE"
    echo -e "${GREEN}  $provider configured with $model${NC}"
}

do_uninstall() {
    echo -e "${BLUE}Claude Code AI Team -- Uninstall${NC}"
    echo ""
    local claude_cmd=""
    if command -v claude &>/dev/null; then
        claude_cmd="claude"
    elif command -v npx &>/dev/null; then
        claude_cmd="npx @anthropic-ai/claude-code"
    fi
    if [ -n "$claude_cmd" ]; then
        $claude_cmd mcp remove multi-ai-collab 2>/dev/null || true
        echo -e "${GREEN}  MCP server registration removed${NC}"
    fi
    if [ -d "$MCP_DIR" ]; then
        rm -rf "$MCP_DIR"
        echo -e "${GREEN}  Removed $MCP_DIR${NC}"
    fi
    if [ -f "$CLAUDE_DIR/ai-team-knowledge.md" ]; then
        read -r -p "Remove global knowledge base (~/.claude/ai-team-knowledge.md)? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            rm -f "$CLAUDE_DIR/ai-team-knowledge.md"
            echo -e "${GREEN}  Removed knowledge base${NC}"
        else
            echo -e "${YELLOW}  Kept knowledge base${NC}"
        fi
    fi
    echo ""
    echo -e "${YELLOW}Note: The AI team section in ~/.claude/CLAUDE.md was not removed.${NC}"
    echo "  Edit that file manually if desired."
    echo ""
    echo -e "${GREEN}Uninstall complete.${NC}"
    exit 0
}

# -- Flag parsing --------------------------------------------------------------
if [[ "${1:-}" == "--uninstall" ]]; then
    do_uninstall
fi

# -- Main setup ----------------------------------------------------------------
echo -e "${BLUE}Claude Code AI Team Setup${NC}"
echo "Make Claude Code and Grok work together with persistent memory."
echo ""

echo "Checking requirements..."

PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}  Python 3 is required. Install from https://www.python.org/downloads/${NC}"
    exit 1
fi
PYTHON_PATH=$(command -v "$PYTHON_CMD")
PYTHON_VERSION=$("$PYTHON_CMD" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if ! "$PYTHON_CMD" -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo -e "${RED}  Python 3.10+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}  Python $PYTHON_VERSION found at $PYTHON_PATH${NC}"

if ! command -v git &>/dev/null; then
    echo -e "${RED}  git is required. Install from https://git-scm.com/${NC}"
    exit 1
fi
echo -e "${GREEN}  git available${NC}"

CLAUDE_CMD=""
if command -v claude &>/dev/null; then
    CLAUDE_CMD="claude"
elif command -v npx &>/dev/null; then
    CLAUDE_CMD="npx @anthropic-ai/claude-code"
    echo -e "${YELLOW}  claude CLI not found. Falling back to npx (will download on first run).${NC}"
else
    echo -e "${RED}  Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code${NC}"
    exit 1
fi
echo -e "${GREEN}  Claude Code CLI available${NC}"

# -- Step 1: Clone MCP bridge server ------------------------------------------
echo ""
echo "Step 1: Installing MCP bridge server..."
if [ -d "$MCP_DIR/.git" ]; then
    echo -e "${YELLOW}  MCP server already installed at $MCP_DIR${NC}"
else
    if [ -d "$MCP_DIR" ]; then
        echo -e "${YELLOW}  Existing directory found (not a git repo). Backing up...${NC}"
        mv "$MCP_DIR" "$MCP_DIR.bak.$(date +%s)"
    fi
    git clone --quiet https://github.com/RaiAnsar/claude_code-multi-AI-MCP.git "$MCP_DIR"
fi
git -C "$MCP_DIR" checkout --quiet "$MCP_SERVER_SHA"
echo -e "${GREEN}  MCP server installed (pinned to ${MCP_SERVER_SHA:0:7})${NC}"

# -- Step 2: Create venv and install dependencies -----------------------------
echo ""
echo "Step 2: Installing Python dependencies into isolated venv..."
VENV_DIR="$MCP_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
"$VENV_PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null || \
    echo -e "${YELLOW}  Warning: pip upgrade failed. Continuing with existing pip.${NC}"

pip_output=$("$VENV_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" 2>&1) || {
    echo -e "${RED}  Failed to install dependencies:${NC}"
    echo "$pip_output"
    exit 1
}
echo -e "${GREEN}  Dependencies installed into $VENV_DIR${NC}"

# -- Step 3: Configure credentials --------------------------------------------
echo ""
echo "Step 3: Configuring AI credentials..."
CREDS_FILE="$MCP_DIR/credentials.json"
if [ -f "$CREDS_FILE" ] && ! grep -q "YOUR_.*_KEY_HERE" "$CREDS_FILE" 2>/dev/null; then
    echo -e "${YELLOW}  Credentials already configured. Skipping.${NC}"
    echo "  Edit $CREDS_FILE to change API keys."
else
    cp "$MCP_DIR/credentials.template.json" "$CREDS_FILE"
    echo ""
    echo -e "${BLUE}Which AI do you want to configure? (You can add more later)${NC}"
    echo "  1) Grok (xAI)     -- \$0.20/M tokens with grok-4-1-fast-reasoning"
    echo "  2) Gemini (Google) -- Free tier available"
    echo "  3) OpenAI (GPT-4o) -- \$2.50/M tokens"
    echo "  4) DeepSeek        -- Budget option"
    echo ""
    read -r -p "Enter your choice (1-4): " choice
    case $choice in
        1) configure_provider "grok" "grok-4-1-fast-reasoning" "https://console.x.ai/" ;;
        2) configure_provider "gemini" "gemini-2.0-flash" "https://aistudio.google.com/apikey" ;;
        3) configure_provider "openai" "gpt-4o" "https://platform.openai.com/api-keys" ;;
        4) configure_provider "deepseek" "deepseek-chat" "https://platform.deepseek.com/" ;;
        *) echo -e "${YELLOW}  Skipped. Edit $CREDS_FILE manually to add API keys.${NC}" ;;
    esac
fi

# -- Step 4: Apply Windows UTF-8 fix ------------------------------------------
if [[ "$(uname -s)" == *MINGW* ]] || [[ "$(uname -s)" == *MSYS* ]] || [[ "$(uname -r)" == *microsoft* ]]; then
    echo ""
    echo "Step 4: Applying Windows UTF-8 fix..."
    SERVER_PY="$MCP_DIR/server.py"
    if grep -q "sys.stdout = os.fdopen" "$SERVER_PY" 2>/dev/null; then
        sed -i "s|sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)|sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')|" "$SERVER_PY"
        sed -i "s|sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 1)|sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')|" "$SERVER_PY"
        echo -e "${GREEN}  UTF-8 fix applied${NC}"
    else
        echo -e "${YELLOW}  UTF-8 fix already applied or not needed${NC}"
    fi
fi

# -- Step 5: Register MCP server globally -------------------------------------
echo ""
echo "Step 5: Registering MCP server..."
$CLAUDE_CMD mcp remove multi-ai-collab 2>/dev/null || true
$CLAUDE_CMD mcp add --scope user --transport stdio multi-ai-collab -- "$VENV_PYTHON" "$MCP_DIR/server.py"
echo -e "${GREEN}  MCP server registered globally (using venv Python)${NC}"

# -- Step 6: Install template files --------------------------------------------
echo ""
echo "Step 6: Installing AI team defaults..."
mkdir -p "$CLAUDE_DIR"

if [ -f "$CLAUDE_DIR/CLAUDE.md" ]; then
    if grep -q "AI Team Collaboration" "$CLAUDE_DIR/CLAUDE.md" 2>/dev/null; then
        echo -e "${YELLOW}  Global CLAUDE.md already has AI team section. Skipping.${NC}"
    else
        echo "" >> "$CLAUDE_DIR/CLAUDE.md"
        cat "$SCRIPT_DIR/defaults/global-CLAUDE.md" >> "$CLAUDE_DIR/CLAUDE.md"
        echo -e "${GREEN}  AI team rules appended to existing CLAUDE.md${NC}"
    fi
else
    cp "$SCRIPT_DIR/defaults/global-CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
    echo -e "${GREEN}  Global CLAUDE.md installed${NC}"
fi

if [ ! -f "$CLAUDE_DIR/ai-team-knowledge.md" ]; then
    cp "$SCRIPT_DIR/defaults/ai-team-knowledge.md" "$CLAUDE_DIR/ai-team-knowledge.md"
    echo -e "${GREEN}  Global knowledge base installed${NC}"
else
    echo -e "${YELLOW}  Global knowledge base already exists. Skipping.${NC}"
fi

# -- Done ---------------------------------------------------------------------
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Restart VS Code (or open a new Claude Code CLI session)"
echo "  2. Try: 'Ask Grok to say hello'"
echo "  3. Claude will auto-create AI_TEAM_SYNERGY.md in each project"
echo ""
echo "Files installed:"
echo "  ~/.claude/CLAUDE.md                            (global rules)"
echo "  ~/.claude/ai-team-knowledge.md                 (global knowledge base)"
echo "  ~/.claude-mcp-servers/multi-ai-collab/         (MCP server)"
echo "  ~/.claude-mcp-servers/multi-ai-collab/.venv/   (isolated Python env)"
echo ""
echo "To add more AI providers later:"
echo "  Edit ~/.claude-mcp-servers/multi-ai-collab/credentials.json"
echo ""
echo "To uninstall:"
echo "  ./setup.sh --uninstall"
