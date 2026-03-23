from __future__ import annotations

import re
from typing import Any

from .config import ToolMapping


def find_mapping(tool_name: str, mappings: list[ToolMapping]) -> ToolMapping | None:
    """Match a tool name against mappings using glob-like patterns."""
    for mapping in mappings:
        if mapping.tool_name == tool_name:
            return mapping

    for mapping in mappings:
        if "*" in mapping.tool_name:
            pattern = "^" + re.escape(mapping.tool_name).replace(r"\*", ".*") + "$"
            if re.match(pattern, tool_name):
                return mapping

    return None


def derive_resource_scope(tool_name: str, args: dict[str, Any]) -> str:
    """Derive resource_scope from tool arguments when no explicit mapping exists."""
    scope_keys = ["path", "file", "table", "database", "collection", "bucket", "resource", "url", "endpoint"]
    for key in scope_keys:
        if isinstance(args.get(key), str):
            return args[key]
    return tool_name
