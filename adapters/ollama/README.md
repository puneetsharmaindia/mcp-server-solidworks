# SolidPilot — Ollama Adapter

Run SolidPilot with a **local Ollama model** — zero cloud cost, full privacy, offline capable.

This adapter connects a local LLM (via [Ollama](https://ollama.com)) to the same MCP server that Claude Desktop uses, giving any Ollama model with function-calling support full access to SolidPilot's CAD automation tools.

## How It Works

```
                  ┌─────────────────────────────────────────────┐
                  │          ollama_client.py (this adapter)     │
  User ──────────►│                                             │
   CLI            │  Ollama API ◄──► Agentic Loop ◄──► MCP SDK  │
                  │  (local LLM)      (tool calls)    (client)  │
                  └──────────────────────┬──────────────────────┘
                                         │ stdio (MCP)
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │     adapters/claude/server.py (MCP server)   │
                  │     (model-agnostic despite its directory)   │
                  └──────────────────────┬───────────────────────┘
                                         │ REST
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │     execution/solidworks (C# .NET 4.8)       │
                  │     COM ──► SolidWorks                       │
                  └──────────────────────────────────────────────┘
```

The adapter is a **client**, not a server — it reuses the existing MCP server (`adapters/claude/server.py`) with zero modifications.

## Prerequisites

1. **Ollama** — [install Ollama](https://ollama.com/download) and pull a model with function-calling support:

   ```bash
   ollama pull qwen2.5-coder:14b
   ```

2. **SolidWorks 2026** and the **execution layer** built and running (see [main README](../../README.md)).

3. **Python 3.x** with the adapter's dependencies:

   ```bash
   cd adapters/ollama
   pip install -r requirements.txt
   ```

4. The **Claude adapter dependencies** must also be installed (the MCP server subprocess needs them):

   ```bash
   cd adapters/claude
   pip install -r requirements.txt
   ```

## Quick Start

```bash
# 1. Make sure Ollama is running
ollama serve

# 2. Start the Ollama adapter (it launches the MCP server automatically)
cd adapters/ollama
python ollama_client.py
```

You'll see:

```
  ✓ Ollama is reachable at http://localhost:11434
  ✓ MCP server connected
  ✓ Discovered 46 MCP tools
  ✓ Pre-loaded MCP resources (core)

SolidPilot (Ollama)
Model: qwen2.5-coder:14b
Type a request to interact with SolidWorks.  Type exit to quit.

You >
```

Then type a CAD request:

```
You > Open a new part and create a 50mm cube
```

The model will call the appropriate MCP tools (`ensure_ready` → `open_new_part` → `create_sketch` → `add_sketch_entity` → `extrude_feature`) and report the result.

## Configuration

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5-coder:14b` | Model name (must support function calling) |
| `OLLAMA_TEMPERATURE` | `0.1` | Generation temperature (0.0–1.0) |
| `OLLAMA_NUM_CTX` | `32768` | Context window size (tokens) |
| `MCP_SERVER_SCRIPT` | `../claude/server.py` | Path to the MCP server |
| `MCP_SERVER_PYTHON` | Current interpreter | Python for the MCP server subprocess |
| `MAX_TOOL_TURNS` | `30` | Safety limit on consecutive tool-call rounds |
| `RESOURCE_PRELOAD` | `core` | Pre-load level: `core`, `all`, or `none` |

## Recommended Models

| Model | Size | Function Calling | Notes |
|---|---|---|---|
| `qwen2.5-coder:14b` | ~9 GB | ✅ Excellent | Best balance of quality and speed |
| `qwen2.5-coder:7b` | ~4.5 GB | ✅ Good | Lower resources, still capable |
| `llama3.1:8b` | ~4.7 GB | ✅ Good | Broad general capability |
| `llama3.1:70b` | ~40 GB | ✅ Excellent | Best quality, high GPU requirement |
| `mistral:7b` | ~4.1 GB | ✅ Native | Solid general-purpose |
| `deepseek-coder-v2` | ~8.9 GB | ✅ Good | Strong at code generation |

> **Tip**: For Feature Graph IR generation (structured JSON), `qwen2.5-coder` models produce the most reliable output. For general CAD chat, `llama3.1` is a good all-rounder.

## Architecture Notes

- **No server duplication**: This adapter does not copy or fork `server.py`. It launches the existing MCP server as a subprocess and connects over stdio, exactly as Claude Desktop does.
- **Function calling**: Uses Ollama's native OpenAI-compatible function-calling protocol. Models that don't support function calling will not work.
- **Resource injection**: Local models don't autonomously read MCP resources the way Claude does. The adapter pre-loads key resources (the Feature Graph IR schema, recipe index) into the system prompt so the model has the context it needs.
- **Safety valve**: A configurable `MAX_TOOL_TURNS` prevents runaway loops if a weaker model gets stuck in a tool-call cycle.

## Troubleshooting

| Issue | Fix |
|---|---|
| `Cannot reach Ollama` | Run `ollama serve` in another terminal |
| `Model not found` | Run `ollama pull <model-name>` |
| `MCP server won't start` | Check that `adapters/claude/requirements.txt` is installed |
| `Tool calls not working` | Make sure your model supports function calling (see table above) |
| `Context too long` | Increase `OLLAMA_NUM_CTX` or use `RESOURCE_PRELOAD=none` |
| `Slow responses` | Use a smaller model or ensure GPU acceleration is enabled |
