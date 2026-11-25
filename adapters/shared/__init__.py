"""Shared adapter core — reusable bridge components for SolidPilot MCP adapters.

This package contains model-agnostic utilities extracted from the Claude adapter:

  - execution_client : HTTP bridge to the SolidWorks execution layer
  - response_mapper  : execution response → text mapping
  - adapter_log      : file-based logger safe for stdio MCP servers
  - ir_execution_port: bridge from pycompiler to the live execution layer
  - config           : base configuration for the execution layer

The Claude adapter (`adapters/claude/`) was the first and remains self-contained.
This shared package provides PARAMETERIZED versions of the same logic so that
additional adapters (Ollama, OpenAI, etc.) can reuse them without copying code.

Import pattern for a new adapter:

    from adapters.shared.execution_client import ExecutionClient
    from adapters.shared.response_mapper import map_response
    from adapters.shared.adapter_log import AdapterLogger
"""
