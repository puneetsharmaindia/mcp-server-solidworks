"""Convert MCP tool schemas to the Ollama function-calling format.

Ollama uses the OpenAI-compatible function-calling convention:
  { "type": "function", "function": { "name", "description", "parameters" } }

The MCP SDK's `list_tools()` returns `Tool` objects with `.name`, `.description`,
and `.parameters` (a JSON Schema dict).  This module converts them 1:1.
"""
from __future__ import annotations
import copy
import json
from typing import Any


def mcp_tool_to_ollama(tool: dict) -> dict:
    """Convert a single MCP tool dict to the Ollama/OpenAI function-calling shape.

    Input: {"name": ..., "description": ..., "inputSchema": {...}}
           (the JSON that MCP's tools/list returns per tool).
    Output: {"type": "function", "function": {"name", "description", "parameters"}}
    """
    parameters = copy.deepcopy(tool.get("inputSchema") or tool.get("parameters") or {})
    # Strip Pydantic/MCP artefacts that Ollama doesn't understand.
    parameters.pop("title", None)
    parameters.pop("additionalProperties", None)
    for prop in (parameters.get("properties") or {}).values():
        if isinstance(prop, dict):
            prop.pop("title", None)

    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": parameters,
        },
    }


def mcp_tools_to_ollama(tools: list[dict]) -> list[dict]:
    """Convert a list of MCP tool dicts to the Ollama/OpenAI function-calling format."""
    return [mcp_tool_to_ollama(t) for t in tools]


def parse_tool_calls(message: dict) -> list[dict]:
    """Extract tool calls from an Ollama response message.

    Ollama returns tool calls in the message dict under the "tool_calls" key,
    each shaped as:
        {"function": {"name": "...", "arguments": {...}}}

    Returns a list of {"name": str, "arguments": dict}.
    """
    raw = message.get("tool_calls") or []
    calls = []
    for tc in raw:
        fn = tc.get("function") or {}
        name = fn.get("name", "")
        args = fn.get("arguments", {})
        # Ollama may return arguments as a JSON string or a dict.
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                args = {}
        calls.append({"name": name, "arguments": args})
    return calls
