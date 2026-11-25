"""Prompt templates for the local LLM planner.

These prompts are specifically optimized for Feature Graph IR generation —
more focused and constrained than the general-purpose system prompt in the
Ollama adapter, because this planner has exactly one job: produce valid IR.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_schema_summary(schema_path: Path) -> str:
    """Load the Feature Graph schema and extract its key structure.

    Returns a condensed text summary suitable for inclusion in a system prompt.
    Rather than injecting the full 35 KB schema, we extract the essential
    structure the model needs.
    """
    try:
        with open(schema_path, "r", encoding="utf-8-sig") as fh:
            schema = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return f"[Schema unavailable: {exc}]"

    parts = []
    parts.append(f"Schema version: {schema.get('_meta', {}).get('version', '?')}")

    # Graph structure
    graph = schema.get("graph", {})
    parts.append(f"\nGraph structure: {json.dumps(graph, indent=2)}")

    # Node common fields
    node_common = schema.get("node_common", {})
    parts.append(f"\nNode common fields: {json.dumps(node_common, indent=2)}")

    # Reference model
    ref_model = schema.get("reference_model", {})
    parts.append(f"\nReference model: {json.dumps(ref_model, indent=2)}")

    # Covered subset — the node types the compiler actually accepts
    covered = schema.get("covered_subset", {})
    node_types = covered.get("node_types")
    if node_types:
        parts.append(f"\nSupported node types: {json.dumps(node_types)}")

    return "\n".join(parts)


def load_recipe_forward(recipe_path: Path) -> str:
    """Load the 'forward' section from recipe-usage.md.

    The forward section contains the rules for generating IR from design intent
    (as opposed to mapping from an analyzed existing part).
    """
    try:
        with open(recipe_path, "r", encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError as exc:
        return f"[Recipe unavailable: {exc}]"

    # Parse the forward section
    sections: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and " — " in line:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            slug, _, _title = line[3:].partition(" — ")
            current = slug.strip()
            lines = [line]
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()

    return sections.get("forward", "[No 'forward' section found in recipe-usage.md]")


SYSTEM_PROMPT_TEMPLATE = """\
You are a **Feature Graph IR generator** for SolidPilot, a CAD automation system.

Your ONLY job is to produce a valid **Feature Graph IR** (JSON) from a user's
description of a part.  You do NOT interact with SolidWorks, you do NOT call
tools — you ONLY output a JSON Feature Graph that the deterministic compiler
can lower into CAD operations.

## Output format

Return ONLY the Feature Graph JSON — no markdown fences, no explanation, no
preamble.  The JSON must be directly parseable.

## Rules

- **Units**: all lengths in METERS, all angles in RADIANS.
- **Node order**: nodes build in array order (tree order is law).
- **Sketch consumption**: extrude/revolve/rib/sweep/sheet_metal/sketched_bend
  consume the IMMEDIATELY preceding sketch node.
- **Node IDs**: use sequential IDs like "n1", "n2", "n3", ...
- **References**: use datum references ("front", "top", "right") for initial
  features.  Use node references for features on existing geometry.
- **Material**: if the user mentions a material, include it at graph level:
  {{"name": "exact material name", "library": "SolidWorks Materials"}}

## Feature Graph Schema

{schema_summary}

## Forward IR Generation Rules

{forward_rules}
"""


def build_system_prompt(schema_path: Path, recipe_path: Path) -> str:
    """Build the full system prompt with schema summary and recipe rules."""
    schema_summary = load_schema_summary(schema_path)
    forward_rules = load_recipe_forward(recipe_path)
    return SYSTEM_PROMPT_TEMPLATE.format(
        schema_summary=schema_summary,
        forward_rules=forward_rules,
    )


def build_user_prompt(intent: str) -> str:
    """Build the user prompt from a design intent string.

    Parameters
    ----------
    intent : str
        The user's description of what they want to build.
        E.g. "A bracket with two mounting holes, 50mm wide, 30mm tall, 3mm thick"

    Returns
    -------
    str
        Formatted user prompt.
    """
    return (
        f"Generate a Feature Graph IR for the following part:\n\n"
        f"{intent}\n\n"
        f"Return ONLY the JSON. No explanation."
    )
