"""CrewAI tool governance wrapper.

Usage:
    from sidclaw.middleware.crewai import govern_crewai_tool
    governed = govern_crewai_tool(my_tool, client=client)
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .._client import AsyncSidClaw, SidClaw
from .._types import DataClassification
from ._base import evaluate_governance_sync, record_outcome_sync


@runtime_checkable
class CrewAIToolLike(Protocol):
    name: str
    description: str

    def _run(self, *args: Any, **kwargs: Any) -> Any: ...


def govern_crewai_tool(
    tool: CrewAIToolLike,
    *,
    client: SidClaw | AsyncSidClaw,
    target_integration: str | None = None,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
) -> CrewAIToolLike:
    """Wrap a CrewAI tool with SidClaw governance."""
    integration = target_integration or tool.name
    original_run = tool._run

    def governed_run(*args: Any, **kwargs: Any) -> Any:
        assert isinstance(client, SidClaw), "Use SidClaw for sync"
        decision = evaluate_governance_sync(
            client,
            tool.name,
            target_integration=integration,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context={"args": str(args), "kwargs": str(kwargs), "tool_description": tool.description},
        )

        try:
            result = original_run(*args, **kwargs)
            record_outcome_sync(client, decision.trace_id)
            return result
        except Exception as e:
            record_outcome_sync(client, decision.trace_id, e)
            raise

    tool._run = governed_run  # type: ignore[assignment]
    return tool
