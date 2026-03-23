"""OpenAI Agents SDK governance wrapper.

Usage:
    from sidclaw.middleware.openai_agents import govern_function_tool
    result = govern_function_tool(tool_def, handler, client=client)
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from .._client import AsyncSidClaw
from .._types import DataClassification
from ._base import evaluate_governance_async, record_outcome_async


class FunctionDef(TypedDict, total=False):
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool


class OpenAIFunctionTool(TypedDict):
    type: str  # "function"
    function: FunctionDef


ToolHandler = Callable[..., Any]


def govern_function_tool(
    tool: OpenAIFunctionTool,
    handler: ToolHandler,
    *,
    client: AsyncSidClaw,
    target_integration: str | None = None,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
) -> tuple[OpenAIFunctionTool, ToolHandler]:
    """Wrap an OpenAI function tool handler with governance.

    Returns the original tool definition and a governed handler.
    """
    tool_name = tool["function"]["name"]
    integration = target_integration or tool_name

    async def governed_handler(args: Any) -> Any:
        decision = await evaluate_governance_async(
            client,
            tool_name,
            target_integration=integration,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context={"input": str(args), "tool_description": tool["function"].get("description", "")},
        )

        try:
            result = await handler(args)
            await record_outcome_async(client, decision.trace_id)
            return result
        except Exception as e:
            await record_outcome_async(client, decision.trace_id, e)
            raise

    return tool, governed_handler
