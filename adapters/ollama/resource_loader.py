"""Pre-load MCP resources into the system prompt for local models.

Cloud-hosted models (Claude) autonomously read MCP resources when they need
them.  Local models generally don't, so we inject the most important resources
into the system prompt up front.

This module connects to the MCP server over the client session, lists
resources, reads selected ones, and returns the combined text suitable for
inclusion in a system prompt.
"""
from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger(__name__)

# Resources to load at different preload levels.
# "core" — the essentials a model needs to do useful work.
# "all"  — core + every recipe section.
_CORE_URIS = [
    "schema://feature-graph",
    "recipe://usage/index",
]


async def load_resources(session, level: str = "core") -> str:
    """Read MCP resources and return them as a formatted string block.

    Parameters
    ----------
    session : mcp.ClientSession
        An active MCP client session (already initialized).
    level : str
        "none"  — skip entirely.
        "core"  — load the feature-graph schema + recipe index.
        "all"   — load core + every recipe://usage/* section.

    Returns
    -------
    str
        Markdown-formatted block of resource contents, ready for
        system-prompt injection.
    """
    if level == "none":
        return ""

    # Discover available resources.
    try:
        resources_response = await session.list_resources()
        available = {r.uri: r for r in resources_response.resources}
    except Exception as exc:
        log.warning("Could not list MCP resources: %s", exc)
        return ""

    # Decide which URIs to fetch.
    if level == "all":
        uris = [uri for uri in available if str(uri).startswith(("schema://", "recipe://"))]
    else:
        uris = [uri for uri in _CORE_URIS if uri in available]

    if not uris:
        return ""

    parts: list[str] = [
        "# Pre-loaded MCP Resources",
        "(These resources are from the SolidPilot MCP server. "
        "Use them as reference when working with the Feature Graph IR.)\n",
    ]

    for uri in sorted(str(u) for u in uris):
        try:
            result = await session.read_resource(uri)
            # result.contents is a list of ResourceContents; join their text.
            body = "\n".join(
                c.text if hasattr(c, "text") else str(c)
                for c in result.contents
            )
            parts.append(f"## Resource: `{uri}`\n")
            parts.append(body)
            parts.append("")  # blank line separator
        except Exception as exc:
            log.warning("Could not read resource %s: %s", uri, exc)

    return "\n".join(parts)
