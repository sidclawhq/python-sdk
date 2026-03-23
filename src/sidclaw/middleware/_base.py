from __future__ import annotations

from typing import Any

from .._client import AsyncSidClaw, SidClaw
from .._errors import ActionDeniedError
from .._types import DataClassification, EvaluateParams, EvaluateResponse


def evaluate_governance_sync(
    client: SidClaw,
    operation: str,
    *,
    target_integration: str | None = None,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
    context: dict[str, Any] | None = None,
) -> EvaluateResponse:
    """Evaluate an action and raise on deny/approval_required."""
    decision = client.evaluate(
        EvaluateParams(
            operation=operation,
            target_integration=target_integration or operation,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context=context or {},
        )
    )

    if decision.decision == "deny":
        raise ActionDeniedError(
            decision.reason,
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    if decision.decision == "approval_required":
        raise ActionDeniedError(
            f"Approval required: {decision.reason}. Approval ID: {decision.approval_request_id}",
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    return decision


async def evaluate_governance_async(
    client: AsyncSidClaw,
    operation: str,
    *,
    target_integration: str | None = None,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
    context: dict[str, Any] | None = None,
) -> EvaluateResponse:
    """Async version: evaluate an action and raise on deny/approval_required."""
    decision = await client.evaluate(
        EvaluateParams(
            operation=operation,
            target_integration=target_integration or operation,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context=context or {},
        )
    )

    if decision.decision == "deny":
        raise ActionDeniedError(
            decision.reason,
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    if decision.decision == "approval_required":
        raise ActionDeniedError(
            f"Approval required: {decision.reason}. Approval ID: {decision.approval_request_id}",
            trace_id=decision.trace_id,
            policy_rule_id=decision.policy_rule_id,
        )

    return decision


def record_outcome_sync(client: SidClaw, trace_id: str, error: Exception | None = None) -> None:
    """Record success or error outcome."""
    if error:
        client.record_outcome(trace_id, {"status": "error", "metadata": {"error": str(error)}})
    else:
        client.record_outcome(trace_id, {"status": "success"})


async def record_outcome_async(client: AsyncSidClaw, trace_id: str, error: Exception | None = None) -> None:
    """Async: record success or error outcome."""
    if error:
        await client.record_outcome(trace_id, {"status": "error", "metadata": {"error": str(error)}})
    else:
        await client.record_outcome(trace_id, {"status": "success"})
