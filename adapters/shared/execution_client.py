"""Reusable HTTP client for the SolidWorks execution layer.

Parameterized version of adapters/claude/execution_client.py — takes an
ExecutionConfig and an AdapterLogger instead of importing module-level globals.

Usage:
    from adapters.shared.config import ExecutionConfig
    from adapters.shared.adapter_log import AdapterLogger
    from adapters.shared.execution_client import ExecutionClient

    cfg = ExecutionConfig.from_env()
    log = AdapterLogger("my_adapter.log")
    client = ExecutionClient(cfg, log)

    # Same API as the Claude adapter's module-level functions:
    state = client.get_state()
    result = client.call_tool("open_new_part", op_id, sv, {})
    ready = client.ensure_ready()
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Callable

import httpx

from .config import ExecutionConfig
from .adapter_log import AdapterLogger


class ExecutionLayerError(Exception):
    """Raised when the execution layer returns an unexpected HTTP error."""
    pass


class ExecutionClient:
    """HTTP bridge to the SolidWorks execution REST layer.

    Thread-safe: the auto-start lock serializes concurrent spawns.
    """

    def __init__(self, config: ExecutionConfig, logger: AdapterLogger | None = None):
        self.cfg = config
        self._log = logger or AdapterLogger()
        self._spawn_lock = threading.Lock()

    # ----- liveness / auto-start -----

    def server_is_up(self) -> bool:
        """Cheap liveness probe — True if /health answers 200."""
        try:
            with httpx.Client(timeout=2.0) as client:
                return client.get(self.cfg.health_endpoint).status_code == 200
        except Exception:
            return False

    def ensure_server_up(self) -> None:
        """Start the execution-server exe if it isn't already answering /health.

        Guarded against duplicate spawns.  Raises ExecutionLayerError if it
        can't be brought up (missing exe, or never came up).
        """
        with self._spawn_lock:
            if self.server_is_up():
                return
            exe = self.cfg.exe_path
            if not exe or not os.path.isfile(exe):
                self._log.write(f"!! cannot auto-start server — exe not found at {exe}")
                raise ExecutionLayerError(
                    f"solidworks-execution is not running and its exe was not found at "
                    f"{exe}. Build the server or set EXECUTION_EXE_PATH."
                )
            self._log.write(f"-> auto-starting execution server: {exe}")
            # DETACHED_PROCESS | CREATE_NO_WINDOW
            creationflags = 0x00000008 | 0x08000000
            try:
                subprocess.Popen(
                    [exe],
                    cwd=os.path.dirname(exe),
                    creationflags=creationflags,
                    close_fds=True,
                )
            except Exception as ex:
                self._log.write(f"!! server spawn failed: {ex}")
                raise ExecutionLayerError(f"Failed to start solidworks-execution: {ex}")

            deadline = time.monotonic() + self.cfg.server_spawn_timeout
            while time.monotonic() < deadline:
                if self.server_is_up():
                    self._log.write("<- execution server is up")
                    return
                time.sleep(0.5)
            self._log.write("!! execution server did not answer /health within timeout")
            raise ExecutionLayerError(
                f"Started solidworks-execution but it did not answer "
                f"{self.cfg.health_endpoint} within {self.cfg.server_spawn_timeout}s."
            )

    def _request_with_autostart(self, do_request: Callable, label: str):
        """Run an httpx request; on ConnectError, auto-start the server once and retry."""
        try:
            return do_request()
        except httpx.ConnectError:
            self._log.write(f"<- {label} CONNECT_ERROR — attempting server auto-start")
            self.ensure_server_up()
            try:
                return do_request()
            except httpx.ConnectError:
                self._log.write(f"<- {label} CONNECT_ERROR after auto-start")
                raise ExecutionLayerError(
                    "Cannot connect to solidworks-execution even after auto-start. "
                    f"Is {self.cfg.health_endpoint} reachable?"
                )

    # ----- public API -----

    def get_health(self) -> dict:
        """GET /health — server status + COM attach state."""
        try:
            with httpx.Client(timeout=self.cfg.http_timeout) as client:
                response = client.get(self.cfg.health_endpoint)
        except httpx.ConnectError:
            self._log.write("<- health CONNECT_ERROR (server down?)")
            raise ExecutionLayerError(
                f"Cannot connect to solidworks-execution. "
                f"Is the server running on {self.cfg.health_endpoint}?"
            )
        except httpx.TimeoutException:
            self._log.write("<- health TIMEOUT")
            raise ExecutionLayerError(
                f"Health request timed out after {self.cfg.http_timeout}s."
            )
        if response.status_code != 200:
            raise ExecutionLayerError(
                f"Unexpected HTTP {response.status_code} from /health: {response.text}"
            )
        body = response.json()
        self._log.write(
            f"<- health status={body.get('status')} "
            f"comAttached={body.get('comAttached')} sv={body.get('stateVersion')}"
        )
        return body

    def get_state(self) -> int:
        """GET /api/tool/state — fetch the current authoritative state_version."""
        self._log.write("-> get_state (resync)")

        def _do():
            with httpx.Client(timeout=self.cfg.http_timeout) as client:
                return client.get(self.cfg.state_endpoint)

        try:
            response = self._request_with_autostart(_do, "get_state")
        except httpx.TimeoutException:
            self._log.write("<- get_state TIMEOUT")
            raise ExecutionLayerError(
                f"Resync request timed out after {self.cfg.http_timeout}s."
            )

        if response.status_code != 200:
            raise ExecutionLayerError(
                f"Unexpected HTTP {response.status_code} from /state: {response.text}"
            )

        sv = int(response.json().get("stateVersion", 0))
        self._log.write(f"<- get_state sv={sv}")
        return sv

    def call_tool(
        self, tool_name: str, operation_id: str, state_version: int, params: dict
    ) -> dict:
        """POST /api/tool/execute on the solidworks-execution layer.

        Returns the parsed JSON response body on HTTP 200.
        Raises ExecutionLayerError on HTTP 400 or unexpected status codes.
        """
        payload = {
            "operationId": operation_id,
            "tool": tool_name,
            "stateVersion": state_version,
            "params": params,
        }
        self._log.write(f"-> {tool_name} op={operation_id} sv={state_version}")

        def _do():
            with httpx.Client(timeout=self.cfg.http_timeout) as client:
                return client.post(self.cfg.execute_endpoint, json=payload)

        try:
            response = self._request_with_autostart(_do, tool_name)
        except httpx.TimeoutException:
            self._log.write(f"<- {tool_name} TIMEOUT after {self.cfg.http_timeout}s")
            raise ExecutionLayerError(
                f"Request timed out after {self.cfg.http_timeout}s."
            )

        if response.status_code == 400:
            body = response.json()
            self._log.write(f"<- {tool_name} HTTP_400 {body.get('error', '')}")
            raise ExecutionLayerError(
                f"Bad request: {body.get('error', response.text)}"
            )

        if response.status_code != 200:
            self._log.write(f"<- {tool_name} HTTP_{response.status_code}")
            raise ExecutionLayerError(
                f"Unexpected HTTP {response.status_code} from execution layer: "
                f"{response.text}"
            )

        body = response.json()
        err = (body.get("error") or {}).get("code")
        self._log.write(
            f"<- {tool_name} {body.get('status')}"
            f"{(' ' + err) if err else ''} sv={body.get('stateVersion')}"
        )
        return body

    def ensure_ready(self) -> dict:
        """POST /ensure_ready — bring the whole stack up and report readiness.

        Auto-starts the execution server if it's down, then asks it to attach
        to SolidWorks.  Returns the parsed readiness dict.
        """
        self._log.write("-> ensure_ready")
        if not self.server_is_up():
            self.ensure_server_up()

        def _do():
            with httpx.Client(timeout=self.cfg.ensure_timeout) as client:
                return client.post(self.cfg.ensure_endpoint)

        try:
            response = self._request_with_autostart(_do, "ensure_ready")
        except httpx.TimeoutException:
            self._log.write("<- ensure_ready TIMEOUT")
            raise ExecutionLayerError(
                f"ensure_ready timed out after {self.cfg.ensure_timeout}s "
                f"(a SolidWorks cold launch can be slow)."
            )

        if response.status_code != 200:
            self._log.write(f"<- ensure_ready HTTP_{response.status_code}")
            raise ExecutionLayerError(
                f"Unexpected HTTP {response.status_code} from /ensure_ready: "
                f"{response.text}"
            )

        body = response.json()
        self._log.write(
            f"<- ensure_ready comAttached={body.get('comAttached')} "
            f"swLaunched={body.get('swLaunched')} doc={body.get('activeDocument')}"
        )
        return body
