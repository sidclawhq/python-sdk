"""LangChain tool governance wrappers.

Usage:
    from sidclaw.middleware.langchain import govern_tools
    governed = govern_tools(my_tools, client=client)
"""
from __future__ import annotations

from typing import Any

from .._client import AsyncSidClaw, SidClaw
from .._types import DataClassification
from ._base import evaluate_governance_async, evaluate_governance_sync, record_outcome_async, record_outcome_sync

try:
    from langchain_core.tools import BaseTool
except ImportError as e:
    raise ImportError("Install langchain-core: pip install sidclaw[langchain]") from e


def govern_tool(
    tool: BaseTool,
    *,
    client: SidClaw | AsyncSidClaw,
    target_integration: str | None = None,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
) -> BaseTool:
    """Wrap a LangChain tool with SidClaw governance."""
    integration = target_integration or tool.name
    original_invoke = tool.invoke
    original_ainvoke = tool.ainvoke

    def governed_invoke(input: Any, config: Any = None, **kwargs: Any) -> Any:
        assert isinstance(client, SidClaw), "Use SidClaw for sync or AsyncSidClaw for async"
        decision = evaluate_governance_sync(
            client,
            tool.name,
            target_integration=integration,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context={"input": str(input), "tool_description": tool.description or ""},
        )

        try:
            result = original_invoke(input, config, **kwargs)
            record_outcome_sync(client, decision.trace_id)
            return result
        except Exception as e:
            record_outcome_sync(client, decision.trace_id, e)
            raise

    async def governed_ainvoke(input: Any, config: Any = None, **kwargs: Any) -> Any:
        assert isinstance(client, AsyncSidClaw), "Use AsyncSidClaw for async or SidClaw for sync"
        decision = await evaluate_governance_async(
            client,
            tool.name,
            target_integration=integration,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context={"input": str(input), "tool_description": tool.description or ""},
        )

        try:
            result = await original_ainvoke(input, config, **kwargs)
            await record_outcome_async(client, decision.trace_id)
            return result
        except Exception as e:
            await record_outcome_async(client, decision.trace_id, e)
            raise

    tool.invoke = governed_invoke  # type: ignore[assignment]
    tool.ainvoke = governed_ainvoke  # type: ignore[assignment]
    return tool


def govern_tools(
    tools: list[BaseTool],
    *,
    client: SidClaw | AsyncSidClaw,
    data_classification: DataClassification = "internal",
) -> list[BaseTool]:
    """Wrap all tools in a list with governance."""
    return [govern_tool(t, client=client, data_classification=data_classification) for t in tools]
