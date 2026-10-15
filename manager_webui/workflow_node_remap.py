from __future__ import annotations

from typing import Any


def remap_workflow_node_names(
    nodes: list[dict[str, Any]],
    references: list[Any],
) -> list[dict[str, Any]]:
    replacements = {
        reference.previous_name: reference.name
        for reference in references
        if reference.previous_name and reference.previous_name != reference.name
    }
    remapped = []
    for node in nodes:
        if node.get("type") != "workflow":
            remapped.append(node)
            continue
        arguments = node.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        previous_name = arguments.get("workflow_name")
        next_name = replacements.get(previous_name)
        remapped.append(
            {
                **node,
                "arguments": {**arguments, **({"workflow_name": next_name} if next_name else {})},
            }
        )
    return remapped