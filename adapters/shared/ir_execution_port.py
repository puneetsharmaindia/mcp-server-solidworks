"""Reusable bridge from the deterministic pycompiler to the live execution layer.

Parameterized version of adapters/claude/ir_execution_port.py — takes an
ExecutionClient instance instead of importing module-level functions.

Usage:
    from adapters.shared.execution_client import ExecutionClient
    from adapters.shared.ir_execution_port import IRExecutionBridge

    client = ExecutionClient(cfg, log)
    bridge = IRExecutionBridge(client)
    result = bridge.run_feature_graph(graph_dict)
"""
from __future__ import annotations

import os
import sys
import uuid


def _ensure_pycompiler_importable() -> None:
    """Make sure pycompiler is importable.

    Prefers an installed copy (pip install -e compiler/solidworks); falls back
    to a sys.path insert of the repo tree.
    """
    try:
        from pycompiler.compiler import compile_and_run  # noqa: F401
        return
    except ImportError:
        pass
    # Walk up from adapters/shared/ → adapters/ → repo root → compiler/solidworks
    here = os.path.dirname(os.path.abspath(__file__))
    compiler_root = os.path.normpath(
        os.path.join(here, "..", "..", "compiler", "solidworks")
    )
    if compiler_root not in sys.path:
        sys.path.insert(0, compiler_root)


def _is_state_mismatch(resp: dict) -> bool:
    if resp.get("status") != "FAILED":
        return False
    return (resp.get("error") or {}).get("code") == "INVALID_STATE_VERSION"


class IRExecutionBridge:
    """Bridges the pycompiler to a live ExecutionClient.

    Implements pycompiler's ExecutionPort protocol over the shared
    ExecutionClient, with one resync+retry on INVALID_STATE_VERSION.
    """

    def __init__(self, client):
        """
        Parameters
        ----------
        client : ExecutionClient
            A configured shared.execution_client.ExecutionClient instance.
        """
        self._client = client

    def run_feature_graph(self, graph: dict):
        """Compile + run a Feature Graph IR against the live execution layer.

        Returns a pycompiler CompileResult.  Raises ImportError if the
        pycompiler package is not installed or reachable.
        """
        _ensure_pycompiler_importable()
        from pycompiler.compiler import compile_and_run
        from pycompiler.execution_port import ExecutionPort

        port = _SharedExecutionPort(self._client)
        return compile_and_run(port, graph)


class _SharedExecutionPort:
    """Concrete ExecutionPort over the shared ExecutionClient.

    Mirrors the Claude adapter's AdapterExecutionPort but parameterized.
    """

    def __init__(self, client):
        self._client = client

    def execute(self, tool, params, state_version):
        resp = self._client.call_tool(tool, str(uuid.uuid4()), state_version, params)
        if _is_state_mismatch(resp):
            fresh = self._client.get_state()
            resp = self._client.call_tool(tool, str(uuid.uuid4()), fresh, params)
        return resp

    def get_state(self):
        return self._client.get_state()
