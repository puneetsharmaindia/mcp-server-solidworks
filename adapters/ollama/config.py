"""Configuration for the Ollama MCP client adapter.

Loads settings from adapters/ollama/.env by EXPLICIT path (same anchoring
pattern as the Claude adapter — the cwd is unpredictable when launched
by an external host).
"""
import os
from dotenv import load_dotenv

# Anchor .env to this file's directory.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
# Generation temperature — lower = more deterministic, higher = more creative.
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
# Maximum tokens per response from Ollama.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))

# ---------------------------------------------------------------------------
# MCP server (adapters/claude/server.py — model-agnostic despite its dir name)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_SERVER = os.path.normpath(os.path.join(_HERE, "..", "claude", "server.py"))
MCP_SERVER_SCRIPT = os.getenv("MCP_SERVER_SCRIPT", _DEFAULT_SERVER)

# The Python executable used to launch the MCP server subprocess. Defaults to
# the same interpreter running this adapter.
import sys
MCP_SERVER_PYTHON = os.getenv("MCP_SERVER_PYTHON", sys.executable)

# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------
# Maximum number of consecutive tool-call turns before forcing a text response
# (safety valve against infinite loops in weaker models).
MAX_TOOL_TURNS = int(os.getenv("MAX_TOOL_TURNS", "30"))

# Pre-load MCP resources into the system prompt? "core" loads the feature-graph
# schema and recipe index; "all" loads every recipe section too; "none" skips.
RESOURCE_PRELOAD = os.getenv("RESOURCE_PRELOAD", "core")
