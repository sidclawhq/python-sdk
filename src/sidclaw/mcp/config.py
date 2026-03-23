from __future__ import annotations

from dataclasses import dataclass, field

from .._types import DataClassification


@dataclass
class ToolMapping:
    """Tool-specific governance overrides."""

    tool_name: str
    """Tool name to match. Supports glob patterns: 'db_*', '*_query'."""

    operation: str | None = None
    """Override the operation name sent to the policy engine."""

    target_integration: str | None = None
    """Override the target integration name."""

    resource_scope: str | None = None
    """Override the resource scope."""

    data_classification: DataClassification | None = None
    """Override the data classification."""

    skip_governance: bool = False
    """If True, forward this tool without governance evaluation."""


@dataclass
class GovernanceMCPServerConfig:
    """Configuration for the MCP governance proxy."""

    api_key: str
    agent_id: str
    api_url: str = "https://api.sidclaw.com"
    upstream_command: str | None = None
    upstream_args: list[str] = field(default_factory=list)
    upstream_env: dict[str, str] | None = None
    tool_mappings: list[ToolMapping] = field(default_factory=list)
    default_data_classification: DataClassification = "internal"
    default_resource_scope: str = "*"
    approval_wait_mode: str = "error"
    """'error' returns immediately, 'block' waits for approval."""
    approval_block_timeout: float = 30.0
    """Max wait time in seconds when approval_wait_mode is 'block'."""
