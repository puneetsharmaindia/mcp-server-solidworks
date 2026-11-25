"""Base configuration for the SolidWorks execution layer.

This module provides the SHARED config that every adapter needs — endpoints,
timeouts, and the exe path for auto-start.  Adapter-specific settings (model
name, API keys, etc.) belong in each adapter's own config module.

Usage:
    cfg = ExecutionConfig()                          # all defaults
    cfg = ExecutionConfig(base_url="http://...:5001") # override
    cfg = ExecutionConfig.from_env()                  # load from env vars
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field


@dataclass
class ExecutionConfig:
    """Configuration for the execution layer connection."""

    base_url: str = "http://localhost:5000"
    http_timeout: float = 30.0
    ensure_timeout: float = 120.0
    server_spawn_timeout: float = 20.0
    exe_path: str = ""

    @property
    def execute_endpoint(self) -> str:
        return f"{self.base_url}/api/tool/execute"

    @property
    def state_endpoint(self) -> str:
        return f"{self.base_url}/api/tool/state"

    @property
    def health_endpoint(self) -> str:
        return f"{self.base_url}/health"

    @property
    def ensure_endpoint(self) -> str:
        return f"{self.base_url}/ensure_ready"

    @classmethod
    def from_env(cls, dotenv_path: str | None = None) -> "ExecutionConfig":
        """Load config from environment variables.

        Optionally loads a .env file first. Variable names match the Claude
        adapter's convention for backward compatibility.
        """
        if dotenv_path:
            try:
                from dotenv import load_dotenv
                load_dotenv(dotenv_path)
            except ImportError:
                pass  # dotenv not installed — fine, rely on real env

        base_url = os.getenv("EXECUTION_BASE_URL", "http://localhost:5000")
        return cls(
            base_url=base_url,
            http_timeout=float(os.getenv("HTTP_TIMEOUT", "30")),
            ensure_timeout=float(os.getenv("ENSURE_TIMEOUT", "120")),
            server_spawn_timeout=float(os.getenv("SERVER_SPAWN_TIMEOUT", "20")),
            exe_path=os.getenv("EXECUTION_EXE_PATH", ""),
        )
