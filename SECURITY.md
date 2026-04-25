# Security

## API Key Handling

This project stores API keys in ~/.claude-mcp-servers/multi-ai-collab/credentials.json. The setup scripts restrict this file to owner-only access (chmod 600 on Unix, ACL on Windows).

**Important:**
- Never commit credentials.json to version control (it is in .gitignore)
- The API key is briefly held in memory during setup -- this is unavoidable for any tool that configures credentials
- On Unix, the key is piped via stdin to the helper script and never appears in the process argument list or environment
- On Windows, the key is piped via PowerShell stdin after masked input

## Supply-Chain Safety

The upstream MCP bridge server is pinned to a specific git commit SHA (b66b56f). This means:
- setup.sh and setup.ps1 always install the same code
- Upstream changes do not automatically propagate
- To update, review the diff and change MCP_SERVER_SHA in both scripts

Python dependencies are pinned to exact versions in requirements.txt.

## Reporting Vulnerabilities

If you discover a security issue, please report it privately via [GitHub Security Advisories](https://github.com/yeaalexx/claude-code-ai-team/security/advisories) rather than opening a public issue.
