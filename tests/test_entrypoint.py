"""The server started the way a client starts it.

``fmod-studio-mcp`` has two entry points, the console script and ``python -m``.
Both must start the same server, so this drives the real process over stdio and
reads the real handshake. It passes before and after a refactor of the entry
points, which is what makes it a safety net rather than a bug reproduction.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

EXPECTED_TOOL_COUNT = 155
GENERIC_TOOLS = {
    "fmod_get_property",
    "fmod_set_property",
    "fmod_add_relationship",
    "fmod_remove_relationship",
    "fmod_class_names",
    "fmod_describe_class",
    "fmod_create_event",
}


def handshake() -> dict:
    """Start the server, list its tools, and return the parsed replies."""
    payload = "\n".join(
        json.dumps(msg)
        for msg in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
    ) + "\n"

    proc = subprocess.Popen(
        [sys.executable, "-m", "fmod_studio_mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    assert proc.stdin and proc.stdout
    proc.stdin.write(payload)
    proc.stdin.flush()
    # Give the server time to answer before closing its stdin, otherwise it can
    # exit mid-reply and the last response is lost.
    time.sleep(1.5)
    proc.stdin.close()
    out = proc.stdout.read()
    proc.wait(timeout=15)

    replies = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            message = json.loads(line)
            if "id" in message:
                replies[message["id"]] = message
    return replies


def test_python_dash_m_starts_a_server_that_lists_its_tools():
    replies = handshake()
    assert 1 in replies and 2 in replies, f"missing replies: {sorted(replies)}"
    assert replies[1]["result"]["serverInfo"]["name"] == "fmod-studio-mcp"

    tools = replies[2]["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert len(tools) == EXPECTED_TOOL_COUNT
    assert all(name.startswith("fmod_") for name in names)
    assert GENERIC_TOOLS <= names


def test_every_listed_tool_has_a_usable_schema():
    tools = handshake()[2]["result"]["tools"]
    for tool in tools:
        assert tool["description"], tool["name"]
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        for required in schema.get("required", []):
            assert required in schema["properties"], f"{tool['name']} requires unknown {required}"
