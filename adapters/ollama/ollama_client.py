"""Ollama MCP Client — agentic loop connecting a local Ollama model to SolidPilot.

This is the main entry point.  It:
  1. Launches the existing MCP server (adapters/claude/server.py) as a subprocess.
  2. Connects to it as an MCP client over stdio.
  3. Discovers the tool surface and pre-loads selected resources.
  4. Runs an interactive chat loop:
       user prompt → Ollama (with function calling) → MCP tool calls → results → Ollama → …

Usage:
    cd adapters/ollama
    pip install -r requirements.txt
    python ollama_client.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import (
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_TEMPERATURE,
    OLLAMA_NUM_CTX,
    MCP_SERVER_SCRIPT,
    MCP_SERVER_PYTHON,
    MAX_TOOL_TURNS,
    RESOURCE_PRELOAD,
)
from tool_formatter import mcp_tools_to_ollama, parse_tool_calls
from resource_loader import load_resources
from system_prompt import build_system_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("ollama-mcp")

# ANSI colours for the terminal UI.
_C_RESET = "\033[0m"
_C_BOLD = "\033[1m"
_C_CYAN = "\033[36m"
_C_GREEN = "\033[32m"
_C_YELLOW = "\033[33m"
_C_DIM = "\033[2m"


# ---------------------------------------------------------------------------
# Ollama HTTP helpers
# ---------------------------------------------------------------------------

async def ollama_chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    *,
    model: str = OLLAMA_MODEL,
    temperature: float = OLLAMA_TEMPERATURE,
    num_ctx: int = OLLAMA_NUM_CTX,
) -> dict:
    """Send a chat completion request to the local Ollama server.

    Returns the full response body ({"model", "message", "done", ...}).
    """
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()


async def check_ollama() -> bool:
    """Return True if the Ollama server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# MCP tool execution
# ---------------------------------------------------------------------------

async def execute_tool(session: ClientSession, name: str, arguments: dict) -> str:
    """Call a single MCP tool and return the result as text."""
    log.info("  → tool: %s(%s)", name, json.dumps(arguments, default=str)[:200])
    try:
        result = await session.call_tool(name, arguments)
        # result.content is a list of Content items; join their text.
        text = "\n".join(
            c.text if hasattr(c, "text") else str(c) for c in result.content
        )
        # Truncate very long results for the model context (analysis dumps can be huge).
        if len(text) > 12_000:
            text = text[:12_000] + "\n... [truncated — use a more specific query if needed]"
        log.info("  ← %s: %.120s", name, text.replace("\n", " "))
        return text
    except Exception as exc:
        err = f"Tool error: {type(exc).__name__}: {exc}"
        log.error("  ← %s: %s", name, err)
        return err


# ---------------------------------------------------------------------------
# Agentic conversation loop
# ---------------------------------------------------------------------------

async def agentic_loop(
    session: ClientSession,
    ollama_tools: list[dict],
    system_prompt: str,
) -> None:
    """Run the interactive user ↔ Ollama ↔ MCP tool loop.

    The loop continues until the user types 'exit', 'quit', or Ctrl-C.
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    print(f"\n{_C_BOLD}{_C_CYAN}SolidPilot (Ollama){_C_RESET}")
    print(f"Model: {_C_GREEN}{OLLAMA_MODEL}{_C_RESET}")
    print(f"Type a request to interact with SolidWorks.  "
          f"Type {_C_YELLOW}exit{_C_RESET} to quit.\n")

    while True:
        # ---- User input ----
        try:
            user_input = input(f"{_C_BOLD}You > {_C_RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            break

        messages.append({"role": "user", "content": user_input})

        # ---- Turn loop (model may produce multiple tool-call rounds) ----
        tool_turns = 0
        while True:
            # Call Ollama.
            try:
                response = await ollama_chat(messages, tools=ollama_tools)
            except httpx.HTTPStatusError as exc:
                print(f"\n{_C_YELLOW}Ollama error: {exc}{_C_RESET}\n")
                break
            except httpx.ConnectError:
                print(f"\n{_C_YELLOW}Cannot reach Ollama at {OLLAMA_BASE_URL}. "
                      f"Is it running?{_C_RESET}\n")
                break

            msg = response.get("message", {})
            content = msg.get("content", "")
            tool_calls = parse_tool_calls(msg)

            if not tool_calls:
                # Pure text response — print and break back to user input.
                messages.append({"role": "assistant", "content": content})
                if content:
                    print(f"\n{_C_GREEN}SolidPilot >{_C_RESET} {content}\n")
                break

            # ---- Execute each tool call ----
            tool_turns += 1
            if tool_turns > MAX_TOOL_TURNS:
                safety_msg = (
                    f"[Safety: stopped after {MAX_TOOL_TURNS} consecutive tool rounds. "
                    "Please simplify or break the task into steps.]"
                )
                messages.append({"role": "assistant", "content": safety_msg})
                print(f"\n{_C_YELLOW}{safety_msg}{_C_RESET}\n")
                break

            # Append the assistant message with tool calls.
            messages.append(msg)

            if content:
                print(f"\n{_C_DIM}(thinking: {content[:200]}){_C_RESET}")

            for tc in tool_calls:
                print(f"  {_C_CYAN}⚙ {tc['name']}{_C_RESET}"
                      f"{_C_DIM}({json.dumps(tc['arguments'], default=str)[:120]}){_C_RESET}")

                result_text = await execute_tool(session, tc["name"], tc["arguments"])

                # Feed the tool result back into the conversation.
                messages.append({
                    "role": "tool",
                    "content": result_text,
                })

            # Continue the loop — the model will see the tool results and
            # either produce more tool calls or a final text response.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    """Entry point: launch MCP server, connect, discover tools, run loop."""

    # 1. Check Ollama is reachable.
    if not await check_ollama():
        print(f"ERROR: Cannot reach Ollama at {OLLAMA_BASE_URL}.")
        print("Make sure Ollama is running (ollama serve) and the model is pulled:")
        print(f"  ollama pull {OLLAMA_MODEL}")
        sys.exit(1)

    print(f"  ✓ Ollama is reachable at {OLLAMA_BASE_URL}")

    # 2. Launch the MCP server as a subprocess and connect as a client.
    server_params = StdioServerParameters(
        command=MCP_SERVER_PYTHON,
        args=[MCP_SERVER_SCRIPT],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the MCP session.
            await session.initialize()
            print("  ✓ MCP server connected")

            # 3. Discover the tool surface.
            tools_result = await session.list_tools()
            mcp_tools_raw = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.input_schema,
                }
                for t in tools_result.tools
            ]
            ollama_tools = mcp_tools_to_ollama(mcp_tools_raw)
            print(f"  ✓ Discovered {len(ollama_tools)} MCP tools")

            # 4. Pre-load resources for the system prompt.
            resource_text = await load_resources(session, level=RESOURCE_PRELOAD)
            system_prompt = build_system_prompt(resource_text)
            if resource_text:
                print(f"  ✓ Pre-loaded MCP resources ({RESOURCE_PRELOAD})")

            # 5. Run the interactive loop.
            await agentic_loop(session, ollama_tools, system_prompt)


if __name__ == "__main__":
    asyncio.run(main())
