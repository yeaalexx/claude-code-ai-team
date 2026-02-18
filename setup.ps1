# Claude Code AI Team — Setup Script (Windows PowerShell)
# Compatible with PowerShell 5.1+ and PowerShell 7+
# Usage: .\setup.ps1 [-Uninstall]
param(
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"

# Catch Ctrl+C and other interruptions so users know the setup is incomplete.
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    # Only fires on abnormal exit; normal exit is handled by the "Done" block.
} -SupportEvent
trap {
    Write-Host ""
    Write-Host "Setup interrupted. Re-run to complete." -ForegroundColor Red
    exit 1
}

# Read-Host -MaskInput requires PS 7.4+. Fall back to -AsSecureString on older versions.
function Read-HostMasked {
    param([string]$Prompt)
    if ($PSVersionTable.PSVersion -ge [version]"7.4") {
        return (Read-Host $Prompt -MaskInput)
    }
    $secure = Read-Host $Prompt -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

# Pinned commit of the upstream MCP bridge server (RaiAnsar/claude_code-multi-AI-MCP).
# Update this SHA when upgrading to a newer version.
$MCP_SERVER_SHA = "b66b56f33fc99cf359cc797c4591589323d0ccc5"

$mcpDir = Join-Path $env:USERPROFILE ".claude-mcp-servers\multi-ai-collab"
$claudeDir = Join-Path $env:USERPROFILE ".claude"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Uninstall ──────────────────────────────────────────────────────────
if ($Uninstall) {
    Write-Host "Claude Code AI Team — Uninstall" -ForegroundColor Cyan
    Write-Host ""

    # Remove MCP registration
    $claudeCmd = $null
    if (Get-Command "claude" -ErrorAction SilentlyContinue) { $claudeCmd = "claude" }
    elseif (Get-Command "npx" -ErrorAction SilentlyContinue) { $claudeCmd = "npx" }
    if ($claudeCmd) {
        if ($claudeCmd -eq "npx") {
            & npx @anthropic-ai/claude-code mcp remove multi-ai-collab 2>$null
        } else {
            & claude mcp remove multi-ai-collab 2>$null
        }
        Write-Host "  MCP server registration removed" -ForegroundColor Green
    }

    # Remove MCP server directory
    if (Test-Path $mcpDir) {
        Remove-Item $mcpDir -Recurse -Force
        Write-Host "  Removed $mcpDir" -ForegroundColor Green
    }

    # Remove knowledge base (prompt first)
    $knowledgeBase = Join-Path $claudeDir "ai-team-knowledge.md"
    if (Test-Path $knowledgeBase) {
        $confirm = Read-Host "Remove global knowledge base (~/.claude/ai-team-knowledge.md)? [y/N]"
        if ($confirm -match "^[Yy]$") {
            Remove-Item $knowledgeBase -Force
            Write-Host "  Removed knowledge base" -ForegroundColor Green
        } else {
            Write-Host "  Kept knowledge base" -ForegroundColor DarkYellow
        }
    }

    Write-Host ""
    Write-Host "Note: The AI team section in ~/.claude/CLAUDE.md was not removed." -ForegroundColor DarkYellow
    Write-Host "  Edit that file manually to remove the '## AI Team Collaboration' section if desired."
    Write-Host ""
    Write-Host "Uninstall complete." -ForegroundColor Green
    exit 0
}

# ── Main setup ─────────────────────────────────────────────────────────
Write-Host "Claude Code AI Team Setup" -ForegroundColor Cyan
Write-Host "Make Claude Code and Grok work together with persistent memory."
Write-Host ""

# ── Preflight checks ──────────────────────────────────────────────────
Write-Host "Checking requirements..." -ForegroundColor Yellow

# Python
$pythonCmd = $null
$pythonPath = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
        if ($ver) {
            $pythonCmd = $cmd
            $pythonPath = (Get-Command $cmd).Source
            Write-Host "  Python $ver found at $pythonPath" -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $pythonCmd) {
    Write-Host "  Python 3 is required. Install from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# Validate Python version >= 3.10
$pyVerCheck = & $pythonCmd -c "import sys; print(1 if sys.version_info >= (3, 10) else 0)" 2>$null
if ($pyVerCheck -ne "1") {
    Write-Host "  Python 3.10+ required (found $ver)" -ForegroundColor Red
    exit 1
}

# Git
if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    Write-Host "  git is required. Install from https://git-scm.com/" -ForegroundColor Red
    exit 1
}
Write-Host "  git available" -ForegroundColor Green

# Claude Code CLI
$claudeCmd = $null
if (Get-Command "claude" -ErrorAction SilentlyContinue) {
    $claudeCmd = "claude"
} elseif (Get-Command "npx" -ErrorAction SilentlyContinue) {
    $claudeCmd = "npx"
    Write-Host "  claude CLI not found — falling back to npx (will download package on first run)" -ForegroundColor DarkYellow
}
if (-not $claudeCmd) {
    Write-Host "  Claude Code CLI not found. Install: npm install -g @anthropic-ai/claude-code" -ForegroundColor Red
    exit 1
}
Write-Host "  Claude Code CLI available" -ForegroundColor Green

# ── Step 1: Clone MCP bridge server (pinned to known-good commit) ─────
Write-Host ""
Write-Host "Step 1: Installing MCP bridge server..." -ForegroundColor Yellow
if (Test-Path (Join-Path $mcpDir ".git")) {
    Write-Host "  MCP server already installed." -ForegroundColor DarkYellow
} else {
    if (Test-Path $mcpDir) {
        $backupDir = "$mcpDir.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Write-Host "  Existing directory found (not a git repo). Backing up to $backupDir..." -ForegroundColor DarkYellow
        Rename-Item $mcpDir $backupDir
    }
    git clone --quiet https://github.com/RaiAnsar/claude_code-multi-AI-MCP.git $mcpDir
}
# Pin to a known-good commit for reproducibility and supply-chain safety.
git -C $mcpDir checkout --quiet $MCP_SERVER_SHA
$shortSha = $MCP_SERVER_SHA.Substring(0, 7)

# Validate the cloned server has expected files
foreach ($expectedFile in @("server.py", "credentials.template.json")) {
    if (-not (Test-Path (Join-Path $mcpDir $expectedFile))) {
        Write-Host "  Expected file $expectedFile not found in MCP server. The pinned commit may be invalid." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  MCP server installed (pinned to $shortSha)" -ForegroundColor Green

# ── Step 2: Create venv and install Python dependencies ────────────────
Write-Host ""
Write-Host "Step 2: Installing Python dependencies into isolated venv..." -ForegroundColor Yellow
$venvDir = Join-Path $mcpDir ".venv"
if (-not (Test-Path $venvDir)) {
    & $pythonCmd -m venv $venvDir
}
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$reqFile = Join-Path $scriptDir "requirements.txt"

try {
    & $venvPython -m pip install --upgrade pip --quiet 2>$null
} catch {
    Write-Host "  Warning: pip upgrade failed. Continuing with existing pip." -ForegroundColor DarkYellow
}

$pipResult = & $venvPython -m pip install -r $reqFile 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Failed to install dependencies:" -ForegroundColor Red
    Write-Host "  $pipResult" -ForegroundColor Red
    exit 1
}
Write-Host "  Dependencies installed into $venvDir" -ForegroundColor Green

# ── Step 3: Configure credentials ──────────────────────────────────────
Write-Host ""
Write-Host "Step 3: Configuring AI credentials..." -ForegroundColor Yellow
$credsFile = Join-Path $mcpDir "credentials.json"
$templateFile = Join-Path $mcpDir "credentials.template.json"

$needsConfig = $true
if (Test-Path $credsFile) {
    $content = Get-Content $credsFile -Raw
    if ($content -notmatch "YOUR_.*_KEY_HERE") {
        Write-Host "  Credentials already configured. Skipping." -ForegroundColor DarkYellow
        Write-Host "  Edit $credsFile to change API keys."
        $needsConfig = $false
    }
}

if ($needsConfig) {
    Copy-Item $templateFile $credsFile -Force
    Write-Host ""
    Write-Host "Which AI do you want to configure?" -ForegroundColor Cyan
    Write-Host "  1) Grok (xAI)     - Recommended, `$0.20/M tokens with grok-4-1-fast-reasoning"
    Write-Host "  2) Gemini (Google) - Free tier available"
    Write-Host "  3) OpenAI (GPT-4o) - `$2.50/M tokens"
    Write-Host "  4) DeepSeek        - Budget option"
    Write-Host ""

    $choice = Read-Host "Enter your choice (1-4)"
    $apiKey = ""
    $provider = ""
    $model = ""

    switch ($choice) {
        "1" {
            $apiKey = Read-HostMasked "Enter your xAI API key (from https://console.x.ai/)"
            $provider = "grok"
            $model = "grok-4-1-fast-reasoning"
        }
        "2" {
            $apiKey = Read-HostMasked "Enter your Gemini API key (from https://aistudio.google.com/apikey)"
            $provider = "gemini"
            $model = "gemini-2.0-flash"
        }
        "3" {
            $apiKey = Read-HostMasked "Enter your OpenAI API key (from https://platform.openai.com/api-keys)"
            $provider = "openai"
            $model = "gpt-4o"
        }
        "4" {
            $apiKey = Read-HostMasked "Enter your DeepSeek API key (from https://platform.deepseek.com/)"
            $provider = "deepseek"
            $model = "deepseek-chat"
        }
        default {
            Write-Host "  Skipped. Edit $credsFile manually." -ForegroundColor DarkYellow
        }
    }

    if ($apiKey -and $provider) {
        # Pipe the API key via stdin to avoid exposing it in the process environment.
        $updateScript = Join-Path $scriptDir "scripts\update_creds.py"
        $env:CREDS_FILE = $credsFile
        $env:PROVIDER = $provider
        $env:MODEL = $model
        $apiKey | & $pythonCmd $updateScript
        Remove-Item Env:CREDS_FILE -ErrorAction SilentlyContinue
        Remove-Item Env:PROVIDER -ErrorAction SilentlyContinue
        Remove-Item Env:MODEL -ErrorAction SilentlyContinue

        # Restrict credentials file to current user only
        try {
            $acl = Get-Acl $credsFile
            $acl.SetAccessRuleProtection($true, $false)
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                $env:USERNAME, "FullControl", "Allow")
            $acl.SetAccessRule($rule)
            Set-Acl $credsFile $acl
        } catch {
            Write-Host "  Warning: Could not restrict file permissions on credentials.json" -ForegroundColor DarkYellow
        }

        Write-Host "  $provider configured with $model" -ForegroundColor Green
    }
}

# ── Step 4: Apply Windows UTF-8 fix ───────────────────────────────────
Write-Host ""
Write-Host "Step 4: Applying Windows UTF-8 fix..." -ForegroundColor Yellow
$serverPy = Join-Path $mcpDir "server.py"
$serverContent = Get-Content $serverPy -Raw
if ($serverContent -match "sys\.stdout = os\.fdopen\(sys\.stdout\.fileno\(\), 'w', 1\)") {
    $serverContent = $serverContent -replace "sys\.stdout = os\.fdopen\(sys\.stdout\.fileno\(\), 'w', 1\)", "sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')"
    $serverContent = $serverContent -replace "sys\.stderr = os\.fdopen\(sys\.stderr\.fileno\(\), 'w', 1\)", "sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1, encoding='utf-8', errors='replace')"
    Set-Content $serverPy -Value $serverContent -NoNewline
    Write-Host "  UTF-8 fix applied" -ForegroundColor Green
} else {
    Write-Host "  UTF-8 fix already applied or not needed" -ForegroundColor DarkYellow
}

# ── Step 5: Register MCP server globally ───────────────────────────────
Write-Host ""
Write-Host "Step 5: Registering MCP server..." -ForegroundColor Yellow
if ($claudeCmd -eq "npx") {
    & npx @anthropic-ai/claude-code mcp remove multi-ai-collab 2>$null
    & npx @anthropic-ai/claude-code mcp add --scope user --transport stdio multi-ai-collab -- $venvPython $serverPy
} else {
    & claude mcp remove multi-ai-collab 2>$null
    & claude mcp add --scope user --transport stdio multi-ai-collab -- $venvPython $serverPy
}
Write-Host "  MCP server registered globally (using venv Python)" -ForegroundColor Green

# ── Step 6: Install default config files ───────────────────────────────
Write-Host ""
Write-Host "Step 6: Installing AI team defaults..." -ForegroundColor Yellow

if (-not (Test-Path $claudeDir)) { New-Item -ItemType Directory -Path $claudeDir | Out-Null }

$globalClaude = Join-Path $claudeDir "CLAUDE.md"
if (Test-Path $globalClaude) {
    $existing = Get-Content $globalClaude -Raw
    if ($existing -match "AI Team Collaboration") {
        Write-Host "  Global CLAUDE.md already has AI team section. Skipping." -ForegroundColor DarkYellow
    } else {
        Add-Content $globalClaude -Value "`n"
        Get-Content (Join-Path $scriptDir "defaults\global-CLAUDE.md") | Add-Content $globalClaude
        Write-Host "  AI team rules appended to existing CLAUDE.md" -ForegroundColor Green
    }
} else {
    Copy-Item (Join-Path $scriptDir "defaults\global-CLAUDE.md") $globalClaude
    Write-Host "  Global CLAUDE.md installed" -ForegroundColor Green
}

$knowledgeBase = Join-Path $claudeDir "ai-team-knowledge.md"
if (-not (Test-Path $knowledgeBase)) {
    Copy-Item (Join-Path $scriptDir "defaults\ai-team-knowledge.md") $knowledgeBase
    Write-Host "  Global knowledge base installed" -ForegroundColor Green
} else {
    Write-Host "  Global knowledge base already exists. Skipping." -ForegroundColor DarkYellow
}

# ── Done ───────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Restart VS Code (or open a new Claude Code CLI session)"
Write-Host "  2. Try: 'Ask Grok to say hello'"
Write-Host "  3. Claude will auto-create AI_TEAM_SYNERGY.md in each project"
Write-Host ""
Write-Host "Files installed:"
Write-Host "  ~/.claude/CLAUDE.md                            (global rules)"
Write-Host "  ~/.claude/ai-team-knowledge.md                 (global knowledge base)"
Write-Host "  ~/.claude-mcp-servers/multi-ai-collab/         (MCP server)"
Write-Host "  ~/.claude-mcp-servers/multi-ai-collab/.venv/   (isolated Python env)"
Write-Host ""
Write-Host "To add more AI providers later:"
Write-Host "  Edit ~/.claude-mcp-servers/multi-ai-collab/credentials.json"
Write-Host ""
Write-Host "To uninstall:"
Write-Host "  .\setup.ps1 -Uninstall"
