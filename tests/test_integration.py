#!/usr/bin/env python3
"""
Integration tests for the v2 MCP server.
Starts the server as a subprocess, sends JSON-RPC messages, verifies responses.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Server path: installed location, or repo fallback for CI
_installed = Path.home() / ".claude-mcp-servers" / "multi-ai-collab" / "server.py"
_repo = Path(__file__).resolve().parent.parent / "server" / "server.py"
SERVER_PY = str(_installed if _installed.exists() else _repo)
PYTHON = sys.executable

passed = 0
failed = 0
stderr_lines = []


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        failed += 1


def drain_stderr(proc):
    """Background thread to capture stderr."""
    try:
        for line in proc.stderr:
            stderr_lines.append(line.decode("utf-8", errors="replace").strip())
    except Exception:
        pass


def send_rpc(proc, method, params=None, msg_id=1, timeout=10):
    """Send a JSON-RPC request and read the response."""
    request = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        request["params"] = params

    msg = json.dumps(request) + "\n"
    proc.stdin.write(msg.encode("utf-8"))
    proc.stdin.flush()

    # Read response line (byte by byte to handle buffering)
    buf = b""
    start = time.time()
    while time.time() - start < timeout:
        b = proc.stdout.read(1)
        if b == b"\n":
            if buf:
                break
        elif b == b"" or b is None:
            time.sleep(0.05)
        else:
            buf += b

    if not buf:
        return None

    try:
        return json.loads(buf.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"_parse_error": str(e), "_raw": buf[:500].decode("utf-8", errors="replace")}


def send_notification(proc, method, params=None):
    """Send a notification (no response expected)."""
    notif = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        notif["params"] = params
    proc.stdin.write((json.dumps(notif) + "\n").encode("utf-8"))
    proc.stdin.flush()


def run_tests():
    global passed, failed

    print("\n=== Integration Tests (Live MCP Server) ===\n")

    # Use environment to force UTF-8
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        [PYTHON, SERVER_PY],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Drain stderr in background
    t = threading.Thread(target=drain_stderr, args=(proc,), daemon=True)
    t.start()

    try:
        time.sleep(1)

        # Verify server is running
        if proc.poll() is not None:
            print(f"  SERVER CRASHED (exit code {proc.returncode})")
            for line in stderr_lines[:10]:
                print(f"    stderr: {line}")
            test("Server starts successfully", False)
            return failed
        test("Server process started", True)

        # --- Test 1: Initialize ---
        print("\n[1] Server Initialization Handshake")
        resp = send_rpc(
            proc,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "integration-test", "version": "1.0.0"},
            },
            msg_id=1,
        )
        test(
            "Initialize returns response", resp is not None, f"stderr: {stderr_lines[-3:] if stderr_lines else 'none'}"
        )
        if resp and "_parse_error" in resp:
            print(f"    Parse error: {resp['_parse_error']}")
            print(f"    Raw: {resp['_raw']}")
        if not resp or "result" not in resp:
            print("  Server not responding — aborting remaining tests")
            return failed

        result = resp["result"]
        test("Has server info", "serverInfo" in result)
        test("Has capabilities", "capabilities" in result)
        server_name = result.get("serverInfo", {}).get("name", "")
        test("Server identifies itself", len(server_name) > 0, f"'{server_name}'")

        # Send initialized notification
        send_notification(proc, "notifications/initialized")
        time.sleep(0.5)

        # --- Test 2: List Tools ---
        print("\n[2] List Available Tools")
        resp = send_rpc(proc, "tools/list", {}, msg_id=2)
        test("Tools list returns response", resp is not None)
        tools = []
        tool_names = []
        if resp and "result" in resp:
            tools = resp["result"].get("tools", [])
            tool_names = [t["name"] for t in tools]
            test(f"Has {len(tools)} tools", len(tools) >= 10, f"Only {len(tools)}")

            v2_tools = [
                "grok_collaborate",
                "grok_execute_task",
                "grok_memory_sync",
                "grok_session_end",
                "grok_memory_status",
            ]
            for tool in v2_tools:
                test(f"v2: {tool}", tool in tool_names)

            v1_tools = ["ask_grok", "grok_code_review", "grok_debug", "grok_think_deep", "grok_brainstorm"]
            for tool in v1_tools:
                test(f"v1: {tool}", tool in tool_names)

        # --- Test 3: Memory Status ---
        print("\n[3] grok_memory_status")
        resp = send_rpc(proc, "tools/call", {"name": "grok_memory_status", "arguments": {}}, msg_id=3)
        test("Returns response", resp is not None)
        if resp and "result" in resp:
            content = resp["result"].get("content", [])
            text = content[0].get("text", "") if content else ""
            test("Has text content", len(text) > 0)
            test(
                "Contains learnings info",
                "learnings" in text.lower() or "learning" in text.lower(),
                f"Text: {text[:200]}",
            )
            test("Contains corrections info", "correction" in text.lower(), f"Text: {text[:200]}")
            test("Contains last updated", "updated" in text.lower(), f"Text: {text[:200]}")

        # --- Test 4: Memory Sync Push ---
        print("\n[4] grok_memory_sync (push)")
        resp = send_rpc(
            proc,
            "tools/call",
            {
                "name": "grok_memory_sync",
                "arguments": {
                    "action": "push",
                    "learnings": "- [TEST] Integration test: always validate API responses before processing them in production",
                },
            },
            msg_id=4,
        )
        test("Returns response", resp is not None)
        if resp and "result" in resp:
            content = resp["result"].get("content", [])
            text = content[0].get("text", "") if content else ""
            test("Has content", len(text) > 0)

        # --- Test 5: Memory Sync Pull ---
        print("\n[5] grok_memory_sync (pull)")
        resp = send_rpc(proc, "tools/call", {"name": "grok_memory_sync", "arguments": {"action": "pull"}}, msg_id=5)
        test("Returns response", resp is not None)
        if resp and "result" in resp:
            content = resp["result"].get("content", [])
            text = content[0].get("text", "") if content else ""
            test("Has content", len(text) > 0)

        # --- Test 6: Server Status ---
        print("\n[6] server_status")
        resp = send_rpc(proc, "tools/call", {"name": "server_status", "arguments": {}}, msg_id=6)
        test("Returns response", resp is not None)
        if resp and "result" in resp:
            content = resp["result"].get("content", [])
            text = content[0].get("text", "") if content else ""
            test("Has content", len(text) > 0)
            test("Contains version info", "v2.0.0" in text or "2.0.0" in text, f"Text: {text[:200]}")
            test("Contains AI status", "grok" in text.lower(), f"Text: {text[:200]}")

        # --- Test 7: Input Schemas ---
        print("\n[7] Tool Input Schema Validation")
        for tool in tools:
            schema = tool.get("inputSchema", {})
            test(f"{tool['name']} has schema", isinstance(schema, dict) and "type" in schema)

        # --- Test 8: Unknown Tool Handling ---
        print("\n[8] Error Handling — Unknown Tool")
        resp = send_rpc(proc, "tools/call", {"name": "nonexistent_tool_xyz", "arguments": {}}, msg_id=8)
        test("Returns response", resp is not None)
        if resp:
            is_error = "error" in resp or resp.get("result", {}).get("isError", False)
            test("Returns error", is_error, f"Got: {json.dumps(resp)[:300]}")

        # --- Test 9: Unknown Method ---
        print("\n[9] Error Handling — Unknown Method")
        resp = send_rpc(proc, "nonexistent/method", {}, msg_id=9)
        test("Returns response", resp is not None)
        if resp:
            test("Returns method-not-found error", "error" in resp)

    finally:
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

        if stderr_lines:
            err_summary = [line for line in stderr_lines if "Error" in line or "Traceback" in line]
            if err_summary:
                print("\n  [Server errors]:")
                for line in err_summary[:5]:
                    print(f"    {line}")

    print(f"\n--- Integration Tests: {passed} passed, {failed} failed ---")
    return failed


if __name__ == "__main__":
    failures = run_tests()
    sys.exit(1 if failures > 0 else 0)
