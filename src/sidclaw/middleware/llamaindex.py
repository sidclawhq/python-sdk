"""LlamaIndex tool governance wrappers.

Wraps LlamaIndex tools (FunctionTool, QueryEngineTool, etc.) with SidClaw
policy evaluation, approval handling, and audit trail recording.

Uses duck typing — no import from ``llama_index`` is required.

Usage (sync):
    from sidclaw import SidClaw
    from sidclaw.middleware.llamaindex import govern_llamaindex_tools

    client = SidClaw(api_key="...", agent_id="my-agent")
    governed = govern_llamaindex_tools(client, [search_tool, calc_tool])

Usage (async):
    from sidclaw import AsyncSidClaw
    from sidclaw.middleware.llamaindex import govern_llamaindex_tools_async

    client = AsyncSidClaw(api_key="...", agent_id="my-agent")
    governed = govern_llamaindex_tools_async(client, [search_tool, calc_tool])
"""
from __future__ import annotations

from typing import Any, Optional

from .._client import AsyncSidClaw, SidClaw
from .._types import DataClassification
from ._base import (
    evaluate_governance_async,
    evaluate_governance_sync,
    record_outcome_async,
    record_outcome_sync,
)


def govern_llamaindex_tool(
    client: SidClaw,
    tool: Any,
    *,
    target_integration: Optional[str] = None,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
) -> Any:
    """Wrap a LlamaIndex tool with SidClaw governance (sync).

    The tool must have:
    - ``tool.metadata.name`` — the tool name
    - ``tool.metadata.description`` — the tool description
    - ``tool.call(...)`` — the execution method

    The wrapper evaluates governance before execution and records the
    outcome after. On deny or approval_required, raises ``ActionDeniedError``.

    Args:
        client: Sync SidClaw client.
        tool: A LlamaIndex tool instance (FunctionTool, QueryEngineTool, etc.).
        target_integration: Override the target integration name (default: tool name).
        resource_scope: Resource scope for the policy engine (default: "*").
        data_classification: Data classification level (default: "internal").

    Returns:
        The same tool with its ``call`` method wrapped.
    """
    integration = target_integration or tool.metadata.name
    original_call = tool.call

    def governed_call(*args: Any, **kwargs: Any) -> Any:
        decision = evaluate_governance_sync(
            client,
            tool.metadata.name,
            target_integration=integration,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context={
                "input": args[0] if args else kwargs,
                "tool_description": tool.metadata.description,
            },
        )

        try:
            result = original_call(*args, **kwargs)
            record_outcome_sync(client, decision.trace_id)
            return result
        except Exception as e:
            record_outcome_sync(client, decision.trace_id, e)
            raise

    tool.call = governed_call
    return tool


def govern_llamaindex_tools(
    client: SidClaw,
    tools: list[Any],
    *,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
) -> list[Any]:
    """Wrap all LlamaIndex tools in a list with SidClaw governance (sync).

    Uses each tool's ``metadata.name`` as the ``target_integration``.

    Args:
        client: Sync SidClaw client.
        tools: List of LlamaIndex tool instances.
        resource_scope: Resource scope for the policy engine.
        data_classification: Data classification level.

    Returns:
        The same list of tools with their ``call`` methods wrapped.
    """
    return [
        govern_llamaindex_tool(
            client,
            t,
            resource_scope=resource_scope,
            data_classification=data_classification,
        )
        for t in tools
    ]


def govern_llamaindex_tool_async(
    client: AsyncSidClaw,
    tool: Any,
    *,
    target_integration: Optional[str] = None,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
) -> Any:
    """Wrap a LlamaIndex tool with SidClaw governance (async).

    Same as :func:`govern_llamaindex_tool` but uses ``AsyncSidClaw`` and
    replaces ``tool.acall`` (or ``tool.call``) with an async governed version.

    Args:
        client: Async SidClaw client.
        tool: A LlamaIndex tool instance (FunctionTool, QueryEngineTool, etc.).
        target_integration: Override the target integration name (default: tool name).
        resource_scope: Resource scope for the policy engine (default: "*").
        data_classification: Data classification level (default: "internal").

    Returns:
        The same tool with its ``acall`` / ``call`` method wrapped.
    """
    integration = target_integration or tool.metadata.name
    # LlamaIndex tools may have acall (async) or call
    original_acall = getattr(tool, "acall", None)
    original_call = tool.call

    async def governed_acall(*args: Any, **kwargs: Any) -> Any:
        decision = await evaluate_governance_async(
            client,
            tool.metadata.name,
            target_integration=integration,
            resource_scope=resource_scope,
            data_classification=data_classification,
            context={
                "input": args[0] if args else kwargs,
                "tool_description": tool.metadata.description,
            },
        )

        try:
            if original_acall is not None:
                result = await original_acall(*args, **kwargs)
            else:
                # Fallback to sync call
                result = original_call(*args, **kwargs)
            await record_outcome_async(client, decision.trace_id)
            return result
        except Exception as e:
            await record_outcome_async(client, decision.trace_id, e)
            raise

    if original_acall is not None:
        tool.acall = governed_acall
    tool.call = governed_acall  # Override call with async version for async usage
    return tool


def govern_llamaindex_tools_async(
    client: AsyncSidClaw,
    tools: list[Any],
    *,
    resource_scope: str = "*",
    data_classification: DataClassification = "internal",
) -> list[Any]:
    """Wrap all LlamaIndex tools in a list with SidClaw governance (async).

    Uses each tool's ``metadata.name`` as the ``target_integration``.

    Args:
        client: Async SidClaw client.
        tools: List of LlamaIndex tool instances.
        resource_scope: Resource scope for the policy engine.
        data_classification: Data classification level.

    Returns:
        The same list of tools with their call methods wrapped.
    """
    return [
        govern_llamaindex_tool_async(
            client,
            t,
            resource_scope=resource_scope,
            data_classification=data_classification,
        )
        for t in tools
    ]
