"""Parameterized file logger for MCP adapters.

Writes to a file (not stdout) because MCP servers speak JSON-RPC over stdio —
anything on stdout would corrupt the protocol.

Usage:
    logger = AdapterLogger()                            # logs to ./adapter.log
    logger = AdapterLogger("/path/to/adapter.log")      # custom path
    logger.write("-> ensure_ready")
"""
from __future__ import annotations

import os
import threading
from datetime import datetime


class AdapterLogger:
    """Thread-safe file logger that NEVER raises.

    Logging failures are silently swallowed — a log line must never break
    a tool call.
    """

    def __init__(self, log_path: str | None = None):
        if log_path is None:
            log_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "adapter.log"
            )
        self.log_path = log_path
        self._lock = threading.Lock()

    def write(self, message: str) -> None:
        """Append a timestamped line to the log file."""
        try:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with self._lock:
                with open(self.log_path, "a", encoding="utf-8") as fh:
                    fh.write(f"{stamp}  {message}\n")
        except Exception:
            # logging must never break a tool call
            pass


# Module-level convenience: a default logger writing next to this file.
_default_logger = AdapterLogger()


def write(message: str) -> None:
    """Write to the default logger (backward-compatible function signature)."""
    _default_logger.write(message)
