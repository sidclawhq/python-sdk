"""Google ADK (Agent Development Kit) tool governance wrappers.

Wraps Google ADK tool execution with SidClaw policy evaluation, approval
handling, and audit trail recording.

Usage (sync):
    from sidclaw import SidClaw
    from sidclaw.middleware.google_adk import govern_google_adk_tool

    client = SidClaw(api_key="...", agent_id="my-agent")
    governed = govern_google_adk_tool(client, tool)
    result = governed(query="hello")

Usage (async):
    from sidclaw import AsyncSidClaw
    from sidclaw.middleware.google_adk import govern_google_adk_tool_async

    client = AsyncSidClaw(api_key="...", agent_id="my-agent")
    governed = govern_google_adk_tool_async(client, tool)
    result = await governed(query="hello")
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .._client import AsyncSidClaw, SidClaw
from .._errors import ActionDeniedError, ApprovalExpiredError, ApprovalTimeoutError
from .._types import DataClassification, EvaluateParams, EvaluateResponse
from ._base import record_outcome_async, record_outcome_sync


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class GoogleADKGovernanceConfig:
    """Configuration for Google ADK governance middleware."""

    data_classification: Dict[str, str] = field(default_factory=dict)
    """Override data classification per tool name (e.g. {"send_email": "confidential"})."""

    default_classification: DataClassification = "internal"
    """Default data classification when no per-tool override is set."""

    resource_scope: str = "google_adk"
    """Resource scope sent to the policy engine."""

    wait_for_approval: bool = True
    """Whether to wait for human approval when decision is ``approval_required``."""

    approval_timeout_seconds: float = 300.0
    """Timeout in seconds when waiting for approval."""

    approval_poll_interval_seconds: float = 2.0
    """Polling interval in seconds when waiting for approval."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_classification(
    tool_name: str,
    config: Optional[GoogleADKGovernanceConfig],
) -> DataClassification:
    if config and tool_name in config.data_classification:
        return config.data_classification[tool_name]  # type: ignore[return-value]
    if config:
        return config.default_classification
    return "internal"


def _evaluate_sync(
    client: SidClaw,
    tool_name: str,
    params: Any,
    config: Optional[GoogleADKGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance synchronously. Handles allow/deny/approval_required."""
    classification = _resolve_classification(tool_name, config)

    decision = client.evaluate(
        EvaluateParams(
            operation=tool_name,
            target_integration="google_adk",
            resource_scope=(config.resource_scope if config else "google_adk"),
            data_classification=classification,
            context={
                "google_adk_tool": tool_name,
                "params": params if isinstance(params, dict) else {"raw": str(params)},
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
    should_wait = config.wait_for_approval if config else True
    if not should_wait or not decision.approval_request_id:
        raise ActionDeniedError(
            f"Approval required: {decision.reason}. Approval ID: {decision.approval_request_id}",
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    timeout = config.approval_timeout_seconds if config else 300.0
    poll_interval = config.approval_poll_interval_seconds if config else 2.0

    status = client.wait_for_approval(
        decision.approval_request_id,
        {"timeout": timeout, "poll_interval": poll_interval},
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
    config: Optional[GoogleADKGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance asynchronously. Handles allow/deny/approval_required."""
    classification = _resolve_classification(tool_name, config)

    decision = await client.evaluate(
        EvaluateParams(
            operation=tool_name,
            target_integration="google_adk",
            resource_scope=(config.resource_scope if config else "google_adk"),
            data_classification=classification,
            context={
                "google_adk_tool": tool_name,
                "params": params if isinstance(params, dict) else {"raw": str(params)},
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
    should_wait = config.wait_for_approval if config else True
    if not should_wait or not decision.approval_request_id:
        raise ActionDeniedError(
            f"Approval required: {decision.reason}. Approval ID: {decision.approval_request_id}",
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    timeout = config.approval_timeout_seconds if config else 300.0
    poll_interval = config.approval_poll_interval_seconds if config else 2.0

    status = await client.wait_for_approval(
        decision.approval_request_id,
        {"timeout": timeout, "poll_interval": poll_interval},
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
# Public API: govern_google_adk_tool (sync)
# ---------------------------------------------------------------------------


def govern_google_adk_tool(
    client: SidClaw,
    tool: Any,
    config: Optional[GoogleADKGovernanceConfig] = None,
) -> Any:
    """Wrap a Google ADK tool with SidClaw governance.

    The tool's callable is intercepted: before execution, SidClaw evaluates the
    policy. On allow, executes. On deny, raises ``ActionDeniedError``. On
    ``approval_required``, waits (configurable).

    Works with both decorated function tools and class-based tools that have a
    ``name`` attribute and are callable.

    Returns an object with the same ``name`` and ``description`` that is callable.

    Example::

        from sidclaw import SidClaw
        from sidclaw.middleware.google_adk import govern_google_adk_tool

        client = SidClaw(api_key="...", agent_id="my-agent")

        @Tool(name="search_docs", description="Search documentation")
        def search_docs(query: str) -> str:
            return do_search(query)

        governed = govern_google_adk_tool(client, search_docs)
        result = governed(query="hello")  # Goes through SidClaw policy first
    """
    tool_name: str = getattr(tool, "name", getattr(tool, "__name__", "unknown_tool"))
    tool_description: str = getattr(tool, "description", getattr(tool, "__doc__", "") or "")

    # The underlying callable: either tool itself if callable, or tool.execute
    if callable(tool) and not hasattr(tool, "execute"):
        original_fn = tool
    elif hasattr(tool, "execute"):
        original_fn = tool.execute
    else:
        original_fn = tool

    @functools.wraps(original_fn)
    def governed_fn(*args: Any, **kwargs: Any) -> Any:
        # Build params context from kwargs or args
        params = kwargs if kwargs else (args[0] if args else {})

        decision = _evaluate_sync(client, tool_name, params, config)

        try:
            result = original_fn(*args, **kwargs)
            record_outcome_sync(client, decision.trace_id)
            return result
        except Exception as e:
            record_outcome_sync(client, decision.trace_id, e)
            raise

    # Preserve tool metadata
    governed_fn.name = tool_name  # type: ignore[attr-defined]
    governed_fn.description = tool_description  # type: ignore[attr-defined]
    governed_fn.__sidclaw_governed = True  # type: ignore[attr-defined]

    return governed_fn


# ---------------------------------------------------------------------------
# Public API: govern_google_adk_tool_async
# ---------------------------------------------------------------------------


def govern_google_adk_tool_async(
    client: AsyncSidClaw,
    tool: Any,
    config: Optional[GoogleADKGovernanceConfig] = None,
) -> Any:
    """Wrap a Google ADK tool with async SidClaw governance.

    Async version of :func:`govern_google_adk_tool`.

    Example::

        from sidclaw import AsyncSidClaw
        from sidclaw.middleware.google_adk import govern_google_adk_tool_async

        client = AsyncSidClaw(api_key="...", agent_id="my-agent")
        governed = govern_google_adk_tool_async(client, search_docs)
        result = await governed(query="hello")
    """
    tool_name: str = getattr(tool, "name", getattr(tool, "__name__", "unknown_tool"))
    tool_description: str = getattr(tool, "description", getattr(tool, "__doc__", "") or "")

    # The underlying callable
    if callable(tool) and not hasattr(tool, "execute"):
        original_fn = tool
    elif hasattr(tool, "execute"):
        original_fn = tool.execute
    else:
        original_fn = tool

    @functools.wraps(original_fn)
    async def governed_fn(*args: Any, **kwargs: Any) -> Any:
        params = kwargs if kwargs else (args[0] if args else {})

        decision = await _evaluate_async(client, tool_name, params, config)

        try:
            result_or_coro = original_fn(*args, **kwargs)
            if hasattr(result_or_coro, "__await__"):
                result = await result_or_coro
            else:
                result = result_or_coro
            await record_outcome_async(client, decision.trace_id)
            return result
        except Exception as e:
            await record_outcome_async(client, decision.trace_id, e)
            raise

    # Preserve tool metadata
    governed_fn.name = tool_name  # type: ignore[attr-defined]
    governed_fn.description = tool_description  # type: ignore[attr-defined]
    governed_fn.__sidclaw_governed = True  # type: ignore[attr-defined]

    return governed_fn


# ---------------------------------------------------------------------------
# Public API: govern_google_adk_tools / govern_google_adk_tools_async
# ---------------------------------------------------------------------------


def govern_google_adk_tools(
    client: SidClaw,
    tools: List[Any],
    config: Optional[GoogleADKGovernanceConfig] = None,
) -> List[Any]:
    """Wrap multiple Google ADK tools with SidClaw governance.

    Convenience function that calls :func:`govern_google_adk_tool` for each tool.
    """
    return [govern_google_adk_tool(client, tool, config) for tool in tools]


def govern_google_adk_tools_async(
    client: AsyncSidClaw,
    tools: List[Any],
    config: Optional[GoogleADKGovernanceConfig] = None,
) -> List[Any]:
    """Wrap multiple Google ADK tools with async SidClaw governance.

    Convenience function that calls :func:`govern_google_adk_tool_async` for each tool.
    """
    return [govern_google_adk_tool_async(client, tool, config) for tool in tools]
