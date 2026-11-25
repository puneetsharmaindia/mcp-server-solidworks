"""Configuration for the local LLM planner.

Loads settings from .env by explicit path (same anchoring pattern as the adapters).
"""
import os
from pathlib import Path

# Anchor paths relative to this file.
_HERE = Path(__file__).resolve().parent
_CAD_PLANNER_DIR = _HERE.parent
_REPO_ROOT = _CAD_PLANNER_DIR.parent

# Try to load .env if python-dotenv is available.
try:
    from dotenv import load_dotenv
    load_dotenv(_HERE / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# A code-oriented model is best for structured JSON generation.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.05"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "32768"))

# ---------------------------------------------------------------------------
# Contracts (paths to the IR schema and recipe rules)
# ---------------------------------------------------------------------------
FEATURE_GRAPH_SCHEMA_PATH = Path(os.getenv(
    "FEATURE_GRAPH_SCHEMA_PATH",
    str(_CAD_PLANNER_DIR / "contracts" / "feature-graph.schema.json"),
))
RECIPE_USAGE_PATH = Path(os.getenv(
    "RECIPE_USAGE_PATH",
    str(_CAD_PLANNER_DIR / "recipe-usage.md"),
))

# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------
# Maximum number of retries when the model produces invalid IR.
MAX_RETRIES = int(os.getenv("PLANNER_MAX_RETRIES", "3"))
