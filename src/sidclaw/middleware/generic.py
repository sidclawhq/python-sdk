from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from .._client import AsyncSidClaw, SidClaw
from .._errors import ActionDeniedError, ApprovalExpiredError
from .._types import DataClassification, EvaluateParams

P = ParamSpec("P")
R = TypeVar("R")


class GovernanceConfig:
    def __init__(
        self,
        operation: str,
        target_integration: str,
        resource_scope: str = "*",
        data_classification: DataClassification = "internal",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.operation = operation
        self.target_integration = target_integration
        self.resource_scope = resource_scope
        self.data_classification = data_classification
        self.context = context


def with_governance(
    client: SidClaw,
    config: GovernanceConfig,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Sync governance decorator. Wraps a sync function with policy evaluation."""

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            decision = client.evaluate(
                EvaluateParams(
                    operation=config.operation,
                    target_integration=config.target_integration,
                    resource_scope=config.resource_scope,
                    data_classification=config.data_classification,
                    context=config.context or {},
                )
            )

            if decision.decision == "deny":
                raise ActionDeniedError(
                    decision.reason,
                    trace_id=decision.trace_id,
                    policy_rule_id=decision.policy_rule_id,
                )

            if decision.decision == "approval_required":
                if not decision.approval_request_id:
                    raise ActionDeniedError(
                        "Approval required but no request ID",
                        trace_id=decision.trace_id,
                    )
                approval = client.wait_for_approval(decision.approval_request_id)
                if approval.status == "denied":
                    raise ActionDeniedError(
                        f"Denied by reviewer: {approval.decision_note or 'No reason'}",
                        trace_id=decision.trace_id,
                    )
                if approval.status == "expired":
                    raise ApprovalExpiredError(decision.approval_request_id, decision.trace_id)

            try:
                result = fn(*args, **kwargs)
                client.record_outcome(decision.trace_id, {"status": "success"})
                return result
            except Exception as e:
                client.record_outcome(decision.trace_id, {"status": "error", "metadata": {"error": str(e)}})
                raise

        return wrapper

    return decorator


def async_with_governance(
    client: AsyncSidClaw,
    config: GovernanceConfig,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Async governance decorator."""

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            decision = await client.evaluate(
                EvaluateParams(
                    operation=config.operation,
                    target_integration=config.target_integration,
                    resource_scope=config.resource_scope,
                    data_classification=config.data_classification,
                    context=config.context or {},
                )
            )

            if decision.decision == "deny":
                raise ActionDeniedError(
                    decision.reason,
                    trace_id=decision.trace_id,
                    policy_rule_id=decision.policy_rule_id,
                )

            if decision.decision == "approval_required":
                if not decision.approval_request_id:
                    raise ActionDeniedError(
                        "Approval required but no request ID",
                        trace_id=decision.trace_id,
                    )
                approval = await client.wait_for_approval(decision.approval_request_id)
                if approval.status == "denied":
                    raise ActionDeniedError(
                        f"Denied by reviewer: {approval.decision_note or 'No reason'}",
                        trace_id=decision.trace_id,
                    )
                if approval.status == "expired":
                    raise ApprovalExpiredError(decision.approval_request_id, decision.trace_id)

            try:
                result = await fn(*args, **kwargs)
                await client.record_outcome(decision.trace_id, {"status": "success"})
                return result
            except Exception as e:
                await client.record_outcome(decision.trace_id, {"status": "error", "metadata": {"error": str(e)}})
                raise

        return wrapper

    return decorator
