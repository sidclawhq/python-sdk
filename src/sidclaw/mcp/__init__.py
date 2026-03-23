"""MCP governance proxy for SidClaw."""

from .config import GovernanceMCPServerConfig, ToolMapping
from .interceptor import derive_resource_scope, find_mapping


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "GovernanceMCPServer":
        from .server import GovernanceMCPServer

        return GovernanceMCPServer
    if name == "cli_main":
        from .server import cli_main

        return cli_main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "GovernanceMCPServer",
    "GovernanceMCPServerConfig",
    "ToolMapping",
    "cli_main",
    "derive_resource_scope",
    "find_mapping",
]
