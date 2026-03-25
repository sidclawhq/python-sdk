"""Composio tool governance wrappers.

Wraps Composio tool execution with SidClaw policy evaluation, approval
handling, and audit trail recording.

Usage (sync):
    from sidclaw import SidClaw
    from sidclaw.middleware.composio import govern_composio_execution

    client = SidClaw(api_key="...", agent_id="my-agent")
    composio = Composio(api_key="...")
    execute = govern_composio_execution(client, composio)
    result = execute("GITHUB_CREATE_ISSUE", user_id="u", arguments={...})

Usage (async):
    from sidclaw import AsyncSidClaw
    from sidclaw.middleware.composio import govern_composio_execution_async

    client = AsyncSidClaw(api_key="...", agent_id="my-agent")
    composio = Composio(api_key="...")
    execute = govern_composio_execution_async(client, composio)
    result = await execute("GITHUB_CREATE_ISSUE", user_id="u", arguments={...})
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

import anyio

from .._client import AsyncSidClaw, SidClaw
from .._errors import ActionDeniedError, ApprovalExpiredError, ApprovalTimeoutError
from .._types import DataClassification, EvaluateParams, EvaluateResponse
from ._base import record_outcome_async, record_outcome_sync


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class ComposioGovernanceConfig:
    """Configuration for Composio governance middleware."""

    data_classification: Dict[str, str] = field(default_factory=dict)
    """Override data classification per Composio toolkit slug (e.g. {"SALESFORCE": "confidential"})."""

    default_classification: DataClassification = "internal"
    """Default data classification when no per-toolkit override is set."""

    resource_scope: str = "composio_managed"
    """Resource scope sent to the policy engine."""

    wait_for_approval: bool = True
    """Whether to wait for human approval when decision is ``approval_required``."""

    approval_timeout_seconds: float = 300.0
    """Timeout in seconds when waiting for approval."""

    approval_poll_interval_seconds: float = 2.0
    """Polling interval in seconds when waiting for approval."""


# ---------------------------------------------------------------------------
# Slug mapping
# ---------------------------------------------------------------------------


def map_composio_slug(slug: str) -> Tuple[str, str]:
    """Map a Composio tool slug to ``(operation, target_integration)``.

    Convention:
    - First segment = toolkit (target_integration), lowercased.
    - Remaining segments = action (operation), joined with ``_``, lowercased.

    Examples::

        GITHUB_CREATE_ISSUE  -> ("create_issue", "github")
        GMAIL_SEND_EMAIL     -> ("send_email", "gmail")
        WEBHOOK              -> ("webhook", "webhook")
    """
    parts = slug.split("_")
    if len(parts) < 2:
        lower = slug.lower()
        return lower, lower
    toolkit = parts[0].lower()
    action = "_".join(parts[1:]).lower()
    return action, toolkit


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_classification(
    toolkit_slug: str,
    config: Optional[ComposioGovernanceConfig],
) -> DataClassification:
    upper = toolkit_slug.upper()
    if config and upper in config.data_classification:
        return config.data_classification[upper]  # type: ignore[return-value]
    if config:
        return config.default_classification
    return "internal"


def _evaluate_sync(
    client: SidClaw,
    slug: str,
    params: Any,
    config: Optional[ComposioGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance synchronously. Handles allow/deny/approval_required."""
    operation, target_integration = map_composio_slug(slug)
    classification = _resolve_classification(target_integration, config)

    decision = client.evaluate(
        EvaluateParams(
            operation=operation,
            target_integration=target_integration,
            resource_scope=(config.resource_scope if config else "composio_managed"),
            data_classification=classification,
            context={
                "composio_slug": slug,
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
    slug: str,
    params: Any,
    config: Optional[ComposioGovernanceConfig],
) -> EvaluateResponse:
    """Evaluate governance asynchronously. Handles allow/deny/approval_required."""
    operation, target_integration = map_composio_slug(slug)
    classification = _resolve_classification(target_integration, config)

    decision = await client.evaluate(
        EvaluateParams(
            operation=operation,
            target_integration=target_integration,
            resource_scope=(config.resource_scope if config else "composio_managed"),
            data_classification=classification,
            context={
                "composio_slug": slug,
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
# Public API: govern_composio_execution (sync)
# ---------------------------------------------------------------------------


def govern_composio_execution(
    client: SidClaw,
    composio_client: Any,
    config: Optional[ComposioGovernanceConfig] = None,
) -> Callable[..., Any]:
    """Return a governed wrapper around ``composio.tools.execute()``.

    The returned callable has the signature::

        execute(slug: str, *, user_id: str, arguments: dict, **kwargs) -> dict

    It evaluates governance before execution and records the outcome after.
    """

    def execute(slug: str, *, user_id: str | None = None, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        params = {"user_id": user_id, "arguments": arguments or {}, **kwargs}
        decision = _evaluate_sync(client, slug, params, config)

        try:
            result = composio_client.tools.execute(slug, user_id=user_id, arguments=arguments or {}, **kwargs)
            record_outcome_sync(client, decision.trace_id)
            return result
        except Exception as e:
            record_outcome_sync(client, decision.trace_id, e)
            raise

    return execute


# ---------------------------------------------------------------------------
# Public API: govern_composio_execution_async
# ---------------------------------------------------------------------------


def govern_composio_execution_async(
    client: AsyncSidClaw,
    composio_client: Any,
    config: Optional[ComposioGovernanceConfig] = None,
) -> Callable[..., Any]:
    """Return an async governed wrapper around ``composio.tools.execute()``.

    The returned coroutine has the signature::

        await execute(slug: str, *, user_id: str, arguments: dict, **kwargs) -> dict
    """

    async def execute(slug: str, *, user_id: str | None = None, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        params = {"user_id": user_id, "arguments": arguments or {}, **kwargs}
        decision = await _evaluate_async(client, slug, params, config)

        try:
            # Support both sync and async execute on the composio client
            result_or_coro = composio_client.tools.execute(slug, user_id=user_id, arguments=arguments or {}, **kwargs)
            if hasattr(result_or_coro, "__await__"):
                result = await result_or_coro
            else:
                result = result_or_coro
            await record_outcome_async(client, decision.trace_id)
            return result
        except Exception as e:
            await record_outcome_async(client, decision.trace_id, e)
            raise

    return execute


# ---------------------------------------------------------------------------
# Public API: create_composio_governance_modifiers
# ---------------------------------------------------------------------------


def create_composio_governance_modifiers(
    client: SidClaw,
    config: Optional[ComposioGovernanceConfig] = None,
) -> Dict[str, Any]:
    """Create ``before_execute`` and ``after_execute`` modifier functions.

    These can be used with Composio's modifier/interceptor system::

        modifiers = create_composio_governance_modifiers(client)
        result = composio.tools.execute("GITHUB_CREATE_ISSUE", ..., **modifiers)
    """
    inflight: Dict[str, str] = {}  # toolSlug -> trace_id

    def before_execute(tool: str, toolkit: str, params: Any) -> Any:
        decision = _evaluate_sync(client, tool, params, config)
        inflight[tool] = decision.trace_id
        return params

    def after_execute(tool: str, toolkit: str, response: Any) -> Any:
        trace_id = inflight.pop(tool, None)
        if trace_id:
            record_outcome_sync(client, trace_id)
        return response

    return {"before_execute": before_execute, "after_execute": after_execute}


def create_composio_governance_modifiers_async(
    client: AsyncSidClaw,
    config: Optional[ComposioGovernanceConfig] = None,
) -> Dict[str, Any]:
    """Create async ``before_execute`` and ``after_execute`` modifier functions."""
    inflight: Dict[str, str] = {}

    async def before_execute(tool: str, toolkit: str, params: Any) -> Any:
        decision = await _evaluate_async(client, tool, params, config)
        inflight[tool] = decision.trace_id
        return params

    async def after_execute(tool: str, toolkit: str, response: Any) -> Any:
        trace_id = inflight.pop(tool, None)
        if trace_id:
            await record_outcome_async(client, trace_id)
        return response

    return {"before_execute": before_execute, "after_execute": after_execute}
