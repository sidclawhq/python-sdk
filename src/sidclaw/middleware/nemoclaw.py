"""NemoClaw governance middleware for NVIDIA NemoClaw sandboxed tool execution.

Wraps tool execution inside NVIDIA NemoClaw sandboxes with SidClaw policy
evaluation, approval handling, and audit trail recording.

Usage (sync):
    from sidclaw import SidClaw
    from sidclaw.middleware.nemoclaw import govern_nemoclaw_tool

    client = SidClaw(api_key="...", agent_id="my-agent")
    governed = govern_nemoclaw_tool(client, sandbox_tool)
    result = governed.execute(code="print('hello')")

Usage (async):
    from sidclaw import AsyncSidClaw
    from sidclaw.middleware.nemoclaw import govern_nemoclaw_tool_async

    client = AsyncSidClaw(api_key="...", agent_id="my-agent")
    governed = govern_nemoclaw_tool_async(client, sandbox_tool)
    result = await governed.execute(code="print('hello')")
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from .._client import AsyncSidClaw, SidClaw
from .._errors import ActionDeniedError, ApprovalExpiredError, ApprovalTimeoutError
from .._types import DataClassification, EvaluateParams, EvaluateResponse
from ._base import record_outcome_async, record_outcome_sync


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class NemoClawGovernanceConfig:
    """Configuration for NemoClaw governance middleware."""

    data_classification: Union[Dict[str, str], str, None] = None
    """Data classification: a dict mapping tool names to classifications,
    a single string for all tools, or None (uses default_classification)."""

    default_classification: str = "internal"
    """Default data classification when no per-tool override is set."""

    resource_scope: str = "nemoclaw_sandbox"
    """Resource scope sent to the policy engine."""

    wait_for_approval: bool = False
    """Whether to wait for human approval when decision is ``approval_required``.
    Defaults to False for NemoClaw (sandbox operations are typically automated)."""

    approval_timeout_seconds: float = 300.0
    """Timeout in seconds when waiting for approval."""

    approval_poll_interval_seconds: float = 2.0
    """Polling interval in seconds when waiting for approval."""

    sandbox_name: Optional[str] = None
    """Optional sandbox name included in governance context."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_classification(
    tool_name: str,
    config: Optional[NemoClawGovernanceConfig],
) -> DataClassification:
    """Resolve the data classification for a tool."""
    if config is None:
        return "internal"

    dc = config.data_classification

    if dc is None:
        return config.default_classification  # type: ignore[return-value]

    if isinstance(dc, str):
        return dc  # type: ignore[return-value]

    # dict: per-tool mapping with fallback to default
    if isinstance(dc, dict):
        if tool_name in dc:
            return dc[tool_name]  # type: ignore[return-value]
        return config.default_classification  # type: ignore[return-value]

    return config.default_classification  # type: ignore[return-value]


def _build_context(
    tool_name: str,
    params: Any,
    config: Optional[NemoClawGovernanceConfig],
) -> dict[str, Any]:
    """Build the governance context dict."""
    ctx: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_params": params if isinstance(params, dict) else {"raw": str(params)},
        "runtime": "nemoclaw",
    }
    if config and config.sandbox_name:
        ctx["sandbox_name"] = config.sandbox_name
    return ctx


def _evaluate_sync(
    client: SidClaw,
    tool_name: str,
    params: Any,
    config: Optional[NemoClawGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance synchronously. Handles allow/deny/approval_required."""
    cfg = config or NemoClawGovernanceConfig()
    classification = _resolve_classification(tool_name, cfg)

    decision = client.evaluate(
        EvaluateParams(
            operation=tool_name,
            target_integration="nemoclaw",
            resource_scope=cfg.resource_scope,
            data_classification=classification,
            context=_build_context(tool_name, params, cfg),
        )
    )

    if decision.decision == "allow":
        return decision

    if decision.decision == "deny":
        raise ActionDeniedError(
            decision.reason,
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    # approval_required
    if not cfg.wait_for_approval or not decision.approval_request_id:
        raise ActionDeniedError(
            f"Approval required: {decision.reason}. Approval ID: {decision.approval_request_id}",
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    status = client.wait_for_approval(
        decision.approval_request_id,
        {"timeout": cfg.approval_timeout_seconds, "poll_interval": cfg.approval_poll_interval_seconds},
    )

    if status.status == "approved":
        return decision

    note_suffix = f": {status.decision_note}" if status.decision_note else ""
    raise ActionDeniedError(
        f"Approval denied{note_suffix}",
        trace_id=decision.trace_id,
        policy_rule_id=decision.policy_rule_id,
    )


async def _evaluate_async(
    client: AsyncSidClaw,
    tool_name: str,
    params: Any,
    config: Optional[NemoClawGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance asynchronously. Handles allow/deny/approval_required."""
    cfg = config or NemoClawGovernanceConfig()
    classification = _resolve_classification(tool_name, cfg)

    decision = await client.evaluate(
        EvaluateParams(
            operation=tool_name,
            target_integration="nemoclaw",
            resource_scope=cfg.resource_scope,
            data_classification=classification,
            context=_build_context(tool_name, params, cfg),
        )
    )

    if decision.decision == "allow":
        return decision

    if decision.decision == "deny":
        raise ActionDeniedError(
            decision.reason,
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    # approval_required
    if not cfg.wait_for_approval or not decision.approval_request_id:
        raise ActionDeniedError(
            f"Approval required: {decision.reason}. Approval ID: {decision.approval_request_id}",
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    status = await client.wait_for_approval(
        decision.approval_request_id,
        {"timeout": cfg.approval_timeout_seconds, "poll_interval": cfg.approval_poll_interval_seconds},
    )

    if status.status == "approved":
        return decision

    note_suffix = f": {status.decision_note}" if status.decision_note else ""
    raise ActionDeniedError(
        f"Approval denied{note_suffix}",
        trace_id=decision.trace_id,
        policy_rule_id=decision.policy_rule_id,
    )


# ---------------------------------------------------------------------------
# Governed tool wrapper (duck-typed)
# ---------------------------------------------------------------------------


class GovernedNemoClawTool:
    """A governed wrapper around a NemoClaw tool.

    Preserves ``name``, ``description``, and ``parameters`` from the
    original tool, but wraps ``execute`` with governance.
    """

    def __init__(
        self,
        client: SidClaw,
        tool: Any,
        config: Optional[NemoClawGovernanceConfig] = None,
    ) -> None:
        self._client = client
        self._tool = tool
        self._config = config
        # Preserve duck-typed attributes
        self.name: str = getattr(tool, "name", "unknown")
        self.description: Optional[str] = getattr(tool, "description", None)
        self.parameters: Any = getattr(tool, "parameters", None)

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool with governance enforcement."""
        call_args: Any = kwargs if not args else (args[0] if len(args) == 1 else {"args": args, **kwargs})

        decision = _evaluate_sync(self._client, self.name, call_args, self._config)

        try:
            result = self._tool.execute(*args, **kwargs)
            record_outcome_sync(self._client, decision.trace_id)
            return result
        except Exception as e:
            record_outcome_sync(self._client, decision.trace_id, e)
            raise


class GovernedNemoClawToolAsync:
    """An async governed wrapper around a NemoClaw tool.

    Preserves ``name``, ``description``, and ``parameters`` from the
    original tool, but wraps ``execute`` with governance.
    """

    def __init__(
        self,
        client: AsyncSidClaw,
        tool: Any,
        config: Optional[NemoClawGovernanceConfig] = None,
    ) -> None:
        self._client = client
        self._tool = tool
        self._config = config
        # Preserve duck-typed attributes
        self.name: str = getattr(tool, "name", "unknown")
        self.description: Optional[str] = getattr(tool, "description", None)
        self.parameters: Any = getattr(tool, "parameters", None)

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool with governance enforcement (async)."""
        call_args: Any = kwargs if not args else (args[0] if len(args) == 1 else {"args": args, **kwargs})

        decision = await _evaluate_async(self._client, self.name, call_args, self._config)

        try:
            result_or_coro = self._tool.execute(*args, **kwargs)
            if hasattr(result_or_coro, "__await__"):
                result = await result_or_coro
            else:
                result = result_or_coro
            await record_outcome_async(self._client, decision.trace_id)
            return result
        except Exception as e:
            await record_outcome_async(self._client, decision.trace_id, e)
            raise


# ---------------------------------------------------------------------------
# Public API: govern_nemoclaw_tool
# ---------------------------------------------------------------------------


def govern_nemoclaw_tool(
    client: SidClaw,
    tool: Any,
    config: Optional[NemoClawGovernanceConfig] = None,
) -> GovernedNemoClawTool:
    """Wrap a NemoClaw tool with SidClaw governance (sync).

    Returns a new tool-like object that evaluates governance before
    executing the original tool. On allow, executes and records success.
    On deny, raises ``ActionDeniedError``. On ``approval_required``, raises
    immediately by default (``wait_for_approval=False``).

    Args:
        client: A sync SidClaw client.
        tool: A NemoClaw tool (duck-typed: must have ``name`` and ``execute``).
        config: Optional governance configuration.

    Returns:
        A governed wrapper with the same ``name``, ``description``, and ``parameters``.

    Example::

        from sidclaw import SidClaw
        from sidclaw.middleware.nemoclaw import govern_nemoclaw_tool

        client = SidClaw(api_key="...", agent_id="my-agent")
        governed = govern_nemoclaw_tool(client, sandbox_tool)
        result = governed.execute(code="print('hello')")
    """
    return GovernedNemoClawTool(client, tool, config)


def govern_nemoclaw_tool_async(
    client: AsyncSidClaw,
    tool: Any,
    config: Optional[NemoClawGovernanceConfig] = None,
) -> GovernedNemoClawToolAsync:
    """Wrap a NemoClaw tool with SidClaw governance (async).

    Returns a new tool-like object that evaluates governance before
    executing the original tool asynchronously.

    Args:
        client: An async SidClaw client.
        tool: A NemoClaw tool (duck-typed: must have ``name`` and ``execute``).
        config: Optional governance configuration.

    Returns:
        A governed wrapper with the same ``name``, ``description``, and ``parameters``.

    Example::

        from sidclaw import AsyncSidClaw
        from sidclaw.middleware.nemoclaw import govern_nemoclaw_tool_async

        client = AsyncSidClaw(api_key="...", agent_id="my-agent")
        governed = govern_nemoclaw_tool_async(client, sandbox_tool)
        result = await governed.execute(code="print('hello')")
    """
    return GovernedNemoClawToolAsync(client, tool, config)


# ---------------------------------------------------------------------------
# Public API: govern_nemoclaw_tools / govern_nemoclaw_tools_async
# ---------------------------------------------------------------------------


def govern_nemoclaw_tools(
    client: SidClaw,
    tools: Sequence[Any],
    config: Optional[NemoClawGovernanceConfig] = None,
) -> List[GovernedNemoClawTool]:
    """Wrap all NemoClaw tools in a sequence with SidClaw governance (sync).

    Uses the shared config for all tools. Per-tool data classification is
    resolved from ``config.data_classification`` if it is a dict.
    """
    return [GovernedNemoClawTool(client, tool, config) for tool in tools]


def govern_nemoclaw_tools_async(
    client: AsyncSidClaw,
    tools: Sequence[Any],
    config: Optional[NemoClawGovernanceConfig] = None,
) -> List[GovernedNemoClawToolAsync]:
    """Wrap all NemoClaw tools in a sequence with SidClaw governance (async).

    Uses the shared config for all tools. Per-tool data classification is
    resolved from ``config.data_classification`` if it is a dict.
    """
    return [GovernedNemoClawToolAsync(client, tool, config) for tool in tools]


# ---------------------------------------------------------------------------
# Public API: create_nemoclaw_proxy
# ---------------------------------------------------------------------------


def create_nemoclaw_proxy(
    *,
    api_key: str,
    agent_id: str,
    upstream_command: str,
    upstream_args: list[str],
    api_url: str = "https://api.sidclaw.com",
    server_name: str = "governed",
) -> dict:
    """Generate an openclaw.json MCP config that routes tools through the SidClaw proxy.

    This creates a configuration dict suitable for MCP clients that routes
    NemoClaw tool calls through the SidClaw governance proxy.

    Args:
        api_key: SidClaw API key.
        agent_id: Agent ID registered in SidClaw.
        upstream_command: The NemoClaw server command to proxy.
        upstream_args: Arguments for the upstream command.
        api_url: SidClaw API URL (defaults to production).
        server_name: Name for the MCP server entry.

    Returns:
        A dict with ``mcpServers`` configuration.

    Example::

        from sidclaw.middleware.nemoclaw import create_nemoclaw_proxy

        config = create_nemoclaw_proxy(
            api_key="sk-...",
            agent_id="my-agent",
            upstream_command="nemoclaw-server",
            upstream_args=["--sandbox", "secure"],
        )
        # Write to openclaw.json
    """
    return {
        "mcpServers": {
            server_name: {
                "command": "npx",
                "args": ["-y", "@sidclaw/sdk", "mcp-proxy"],
                "env": {
                    "SIDCLAW_API_KEY": api_key,
                    "SIDCLAW_AGENT_ID": agent_id,
                    "SIDCLAW_API_URL": api_url,
                    "SIDCLAW_UPSTREAM_CMD": upstream_command,
                    "SIDCLAW_UPSTREAM_ARGS": ",".join(upstream_args),
                },
            }
        }
    }
