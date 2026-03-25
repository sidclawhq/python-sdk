"""Claude Agent SDK tool governance wrappers.

Wraps Claude Agent SDK tool execution with SidClaw policy evaluation, approval
handling, and audit trail recording.

Usage (sync):
    from sidclaw import SidClaw
    from sidclaw.middleware.claude_agent_sdk import govern_claude_agent_tool

    client = SidClaw(api_key="...", agent_id="my-agent")
    governed = govern_claude_agent_tool(client, search_tool)
    result = governed.execute(query="test")

Usage (async):
    from sidclaw import AsyncSidClaw
    from sidclaw.middleware.claude_agent_sdk import govern_claude_agent_tool_async

    client = AsyncSidClaw(api_key="...", agent_id="my-agent")
    governed = govern_claude_agent_tool_async(client, search_tool)
    result = await governed.execute(query="test")
"""
from __future__ import annotations

import copy
import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .._client import AsyncSidClaw, SidClaw
from .._errors import ActionDeniedError, ApprovalExpiredError, ApprovalTimeoutError
from .._types import DataClassification, EvaluateParams, EvaluateResponse
from ._base import record_outcome_async, record_outcome_sync


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class ClaudeAgentGovernanceConfig:
    """Configuration for Claude Agent SDK governance middleware."""

    data_classification: DataClassification = "internal"
    """Data classification for governed tools."""

    resource_scope: str = "claude_agent"
    """Resource scope sent to the policy engine."""

    target_integration: Optional[str] = None
    """Target integration name override. Defaults to the tool name."""

    wait_for_approval: bool = True
    """Whether to wait for human approval when decision is ``approval_required``."""

    approval_timeout_seconds: float = 300.0
    """Timeout in seconds when waiting for approval."""

    approval_poll_interval_seconds: float = 2.0
    """Polling interval in seconds when waiting for approval."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _evaluate_sync(
    client: SidClaw,
    tool_name: str,
    args: Any,
    config: Optional[ClaudeAgentGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance synchronously. Handles allow/deny/approval_required."""
    cfg = config or ClaudeAgentGovernanceConfig()

    decision = client.evaluate(
        EvaluateParams(
            operation=tool_name,
            target_integration=cfg.target_integration or tool_name,
            resource_scope=cfg.resource_scope,
            data_classification=cfg.data_classification,
            context={
                "framework": "claude_agent_sdk",
                "tool_name": tool_name,
                "args": args if isinstance(args, dict) else {"raw": str(args)},
            },
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
    args: Any,
    config: Optional[ClaudeAgentGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance asynchronously. Handles allow/deny/approval_required."""
    cfg = config or ClaudeAgentGovernanceConfig()

    decision = await client.evaluate(
        EvaluateParams(
            operation=tool_name,
            target_integration=cfg.target_integration or tool_name,
            resource_scope=cfg.resource_scope,
            data_classification=cfg.data_classification,
            context={
                "framework": "claude_agent_sdk",
                "tool_name": tool_name,
                "args": args if isinstance(args, dict) else {"raw": str(args)},
            },
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


class GovernedClaudeAgentTool:
    """A governed wrapper around a Claude Agent SDK tool.

    Preserves ``name``, ``description``, and ``parameters`` from the
    original tool, but wraps ``execute`` with governance.
    """

    def __init__(
        self,
        client: SidClaw,
        tool: Any,
        config: Optional[ClaudeAgentGovernanceConfig] = None,
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
        # Merge positional and keyword args for context
        call_args: Any = kwargs if not args else (args[0] if len(args) == 1 else {"args": args, **kwargs})

        decision = _evaluate_sync(self._client, self.name, call_args, self._config)

        try:
            result = self._tool.execute(*args, **kwargs)
            record_outcome_sync(self._client, decision.trace_id)
            return result
        except Exception as e:
            record_outcome_sync(self._client, decision.trace_id, e)
            raise


class GovernedClaudeAgentToolAsync:
    """An async governed wrapper around a Claude Agent SDK tool.

    Preserves ``name``, ``description``, and ``parameters`` from the
    original tool, but wraps ``execute`` with governance.
    """

    def __init__(
        self,
        client: AsyncSidClaw,
        tool: Any,
        config: Optional[ClaudeAgentGovernanceConfig] = None,
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
# Public API: govern_claude_agent_tool
# ---------------------------------------------------------------------------


def govern_claude_agent_tool(
    client: SidClaw,
    tool: Any,
    config: Optional[ClaudeAgentGovernanceConfig] = None,
) -> GovernedClaudeAgentTool:
    """Wrap a Claude Agent SDK tool with SidClaw governance (sync).

    Returns a new tool-like object that evaluates governance before
    executing the original tool. On allow, executes and records success.
    On deny, raises ``ActionDeniedError``. On ``approval_required``, waits
    for approval (configurable).

    Args:
        client: A sync SidClaw client.
        tool: A Claude Agent SDK tool (duck-typed: must have ``name`` and ``execute``).
        config: Optional governance configuration.

    Returns:
        A governed wrapper with the same ``name``, ``description``, and ``parameters``.

    Example::

        from sidclaw import SidClaw
        from sidclaw.middleware.claude_agent_sdk import govern_claude_agent_tool

        client = SidClaw(api_key="...", agent_id="my-agent")
        governed = govern_claude_agent_tool(client, search_tool)
        result = governed.execute(query="test")
    """
    return GovernedClaudeAgentTool(client, tool, config)


def govern_claude_agent_tool_async(
    client: AsyncSidClaw,
    tool: Any,
    config: Optional[ClaudeAgentGovernanceConfig] = None,
) -> GovernedClaudeAgentToolAsync:
    """Wrap a Claude Agent SDK tool with SidClaw governance (async).

    Returns a new tool-like object that evaluates governance before
    executing the original tool asynchronously.

    Args:
        client: An async SidClaw client.
        tool: A Claude Agent SDK tool (duck-typed: must have ``name`` and ``execute``).
        config: Optional governance configuration.

    Returns:
        A governed wrapper with the same ``name``, ``description``, and ``parameters``.

    Example::

        from sidclaw import AsyncSidClaw
        from sidclaw.middleware.claude_agent_sdk import govern_claude_agent_tool_async

        client = AsyncSidClaw(api_key="...", agent_id="my-agent")
        governed = govern_claude_agent_tool_async(client, search_tool)
        result = await governed.execute(query="test")
    """
    return GovernedClaudeAgentToolAsync(client, tool, config)


# ---------------------------------------------------------------------------
# Public API: govern_claude_agent_tools / govern_claude_agent_tools_async
# ---------------------------------------------------------------------------


def govern_claude_agent_tools(
    client: SidClaw,
    tools: Sequence[Any],
    config: Optional[ClaudeAgentGovernanceConfig] = None,
) -> List[GovernedClaudeAgentTool]:
    """Wrap all tools in a sequence with SidClaw governance (sync).

    Uses each tool's name as the target integration unless overridden in config.
    """
    results: List[GovernedClaudeAgentTool] = []
    for tool in tools:
        tool_config = ClaudeAgentGovernanceConfig(
            data_classification=config.data_classification if config else "internal",
            resource_scope=config.resource_scope if config else "claude_agent",
            target_integration=getattr(tool, "name", "unknown"),
            wait_for_approval=config.wait_for_approval if config else True,
            approval_timeout_seconds=config.approval_timeout_seconds if config else 300.0,
            approval_poll_interval_seconds=config.approval_poll_interval_seconds if config else 2.0,
        )
        results.append(GovernedClaudeAgentTool(client, tool, tool_config))
    return results


def govern_claude_agent_tools_async(
    client: AsyncSidClaw,
    tools: Sequence[Any],
    config: Optional[ClaudeAgentGovernanceConfig] = None,
) -> List[GovernedClaudeAgentToolAsync]:
    """Wrap all tools in a sequence with SidClaw governance (async).

    Uses each tool's name as the target integration unless overridden in config.
    """
    results: List[GovernedClaudeAgentToolAsync] = []
    for tool in tools:
        tool_config = ClaudeAgentGovernanceConfig(
            data_classification=config.data_classification if config else "internal",
            resource_scope=config.resource_scope if config else "claude_agent",
            target_integration=getattr(tool, "name", "unknown"),
            wait_for_approval=config.wait_for_approval if config else True,
            approval_timeout_seconds=config.approval_timeout_seconds if config else 300.0,
            approval_poll_interval_seconds=config.approval_poll_interval_seconds if config else 2.0,
        )
        results.append(GovernedClaudeAgentToolAsync(client, tool, tool_config))
    return results
