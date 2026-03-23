"""Pydantic AI governance integration.

Usage:
    from sidclaw.middleware.pydantic_ai import governance_dependency

    @agent.tool
    async def my_tool(ctx: RunContext[Deps]) -> str:
        gov = governance_dependency(ctx.deps.sidclaw_client)
        await gov.check("my_tool", target_integration="my-service")
        return do_something()
"""
from __future__ import annotations

from typing import Any

from .._client import AsyncSidClaw
from .._errors import ActionDeniedError
from .._types import DataClassification, EvaluateParams, EvaluateResponse


class GovernanceDependency:
    """Governance helper for use inside Pydantic AI tool functions."""

    def __init__(
        self,
        client: AsyncSidClaw,
        *,
        default_data_classification: DataClassification = "internal",
    ) -> None:
        self._client = client
        self._default_classification = default_data_classification

    async def check(
        self,
        operation: str,
        *,
        target_integration: str | None = None,
        resource_scope: str = "*",
        data_classification: DataClassification | None = None,
        context: dict[str, Any] | None = None,
    ) -> EvaluateResponse:
        """Evaluate governance and raise ActionDeniedError if denied or approval required."""
        decision = await self._client.evaluate(
            EvaluateParams(
                operation=operation,
                target_integration=target_integration or operation,
                resource_scope=resource_scope,
                data_classification=data_classification or self._default_classification,
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

    async def record_success(self, trace_id: str) -> None:
        """Record successful execution."""
        await self._client.record_outcome(trace_id, {"status": "success"})

    async def record_error(self, trace_id: str, error: Exception) -> None:
        """Record failed execution."""
        await self._client.record_outcome(trace_id, {"status": "error", "metadata": {"error": str(error)}})


def governance_dependency(
    client: AsyncSidClaw,
    *,
    default_data_classification: DataClassification = "internal",
) -> GovernanceDependency:
    """Create a governance dependency for use in Pydantic AI tools."""
    return GovernanceDependency(client, default_data_classification=default_data_classification)
