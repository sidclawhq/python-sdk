"""Tests for sidclaw.middleware.llamaindex — LlamaIndex governance wrappers."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from sidclaw import AsyncSidClaw, SidClaw
from sidclaw._errors import ActionDeniedError
from sidclaw.middleware.llamaindex import (
    govern_llamaindex_tool,
    govern_llamaindex_tool_async,
    govern_llamaindex_tools,
    govern_llamaindex_tools_async,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _allow_response():
    return httpx.Response(
        200,
        json={
            "decision": "allow",
            "trace_id": "trace-1",
            "approval_request_id": None,
            "reason": "Allowed by policy",
            "policy_rule_id": "rule-1",
        },
    )


def _deny_response():
    return httpx.Response(
        200,
        json={
            "decision": "deny",
            "trace_id": "trace-2",
            "approval_request_id": None,
            "reason": "Operation not permitted",
            "policy_rule_id": "rule-2",
        },
    )


def _approval_required_response():
    return httpx.Response(
        200,
        json={
            "decision": "approval_required",
            "trace_id": "trace-3",
            "approval_request_id": "approval-1",
            "reason": "Requires human approval",
            "policy_rule_id": "rule-3",
        },
    )


def _outcome_response():
    return httpx.Response(204)


def _make_mock_tool(name: str = "search_docs", description: str = "Search the documentation"):
    """Create a duck-typed LlamaIndex-style tool with metadata + call."""
    tool = SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            description=description,
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        ),
        call=MagicMock(return_value="search result"),
    )
    return tool


def _make_mock_async_tool(name: str = "search_docs", description: str = "Search the documentation"):
    """Create a duck-typed LlamaIndex-style tool with metadata + async acall/call."""

    async def _acall(*args, **kwargs):
        return "async search result"

    tool = SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            description=description,
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        ),
        call=MagicMock(return_value="search result"),
        acall=_acall,
    )
    return tool


# ---------------------------------------------------------------------------
# Tests: govern_llamaindex_tool (sync)
# ---------------------------------------------------------------------------


class TestGovernLlamaIndexToolSync:
    def test_allow_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = _make_mock_tool()
        original_call = tool.call  # Save reference before wrapping replaces it
        governed = govern_llamaindex_tool(client, tool)

        result = governed.call({"query": "test"})

        assert result == "search result"
        original_call.assert_called_once()  # Original call should have been invoked

    def test_deny_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = _make_mock_tool()
        original_call = tool.call
        governed = govern_llamaindex_tool(client, tool)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.call({"query": "test"})

        assert "Operation not permitted" in str(exc_info.value)
        assert exc_info.value.trace_id == "trace-2"
        original_call.assert_not_called()

    def test_approval_required(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())

        tool = _make_mock_tool()
        original_call = tool.call
        governed = govern_llamaindex_tool(client, tool)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.call({"query": "test"})

        assert "Approval required" in str(exc_info.value)
        assert "approval-1" in str(exc_info.value)
        original_call.assert_not_called()

    def test_tool_error_records_outcome(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = _make_mock_tool()
        tool.call = MagicMock(side_effect=RuntimeError("Tool failed"))
        governed = govern_llamaindex_tool(client, tool)

        with pytest.raises(RuntimeError, match="Tool failed"):
            governed.call({"query": "test"})

    def test_preserves_metadata(self, client: SidClaw, mock_api: respx.MockRouter):
        tool = _make_mock_tool("calculator", "Perform calculations")
        governed = govern_llamaindex_tool(client, tool)

        assert governed.metadata.name == "calculator"
        assert governed.metadata.description == "Perform calculations"

    def test_custom_config(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = _make_mock_tool()
        governed = govern_llamaindex_tool(
            client,
            tool,
            target_integration="custom-integration",
            resource_scope="/api/data",
            data_classification="pii",
        )
        governed.call({"query": "test"})

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["target_integration"] == "custom-integration"
        assert body["resource_scope"] == "/api/data"
        assert body["data_classification"] == "pii"

    def test_default_target_integration_is_tool_name(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = _make_mock_tool("my_tool", "My tool")
        governed = govern_llamaindex_tool(client, tool)
        governed.call({"query": "test"})

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["target_integration"] == "my_tool"
        assert body["operation"] == "my_tool"


# ---------------------------------------------------------------------------
# Tests: govern_llamaindex_tools (sync)
# ---------------------------------------------------------------------------


class TestGovernLlamaIndexToolsSync:
    def test_wraps_all_tools(self, client: SidClaw, mock_api: respx.MockRouter):
        tool1 = _make_mock_tool("search_docs", "Search")
        tool2 = _make_mock_tool("calculator", "Calculate")

        governed = govern_llamaindex_tools(client, [tool1, tool2])

        assert len(governed) == 2
        assert governed[0].metadata.name == "search_docs"
        assert governed[1].metadata.name == "calculator"

    def test_uses_tool_name_as_integration(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool1 = _make_mock_tool("search_docs", "Search")
        tool2 = _make_mock_tool("calculator", "Calculate")

        governed = govern_llamaindex_tools(client, [tool1, tool2])
        governed[0].call("q1")
        governed[1].call("q2")

        import json
        body1 = json.loads(route.calls[0].request.content)
        body2 = json.loads(route.calls[1].request.content)
        assert body1["target_integration"] == "search_docs"
        assert body2["target_integration"] == "calculator"

    def test_empty_list(self, client: SidClaw, mock_api: respx.MockRouter):
        governed = govern_llamaindex_tools(client, [])
        assert governed == []

    def test_shared_config(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = _make_mock_tool()
        governed = govern_llamaindex_tools(
            client,
            [tool],
            data_classification="confidential",
            resource_scope="/enterprise",
        )
        governed[0].call("q1")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "confidential"
        assert body["resource_scope"] == "/enterprise"


# ---------------------------------------------------------------------------
# Tests: govern_llamaindex_tool_async
# ---------------------------------------------------------------------------


class TestGovernLlamaIndexToolAsync:
    @pytest.mark.anyio
    async def test_allow_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = _make_mock_async_tool()
        governed = govern_llamaindex_tool_async(async_client, tool)

        result = await governed.call({"query": "test"})
        assert result == "async search result"

    @pytest.mark.anyio
    async def test_deny_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = _make_mock_async_tool()
        governed = govern_llamaindex_tool_async(async_client, tool)

        with pytest.raises(ActionDeniedError) as exc_info:
            await governed.call({"query": "test"})

        assert "Operation not permitted" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_approval_required(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())

        tool = _make_mock_async_tool()
        governed = govern_llamaindex_tool_async(async_client, tool)

        with pytest.raises(ActionDeniedError) as exc_info:
            await governed.call({"query": "test"})

        assert "Approval required" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Tests: govern_llamaindex_tools_async
# ---------------------------------------------------------------------------


class TestGovernLlamaIndexToolsAsync:
    @pytest.mark.anyio
    async def test_wraps_all_tools(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool1 = _make_mock_async_tool("search_docs", "Search")
        tool2 = _make_mock_async_tool("calculator", "Calculate")

        governed = govern_llamaindex_tools_async(async_client, [tool1, tool2])

        assert len(governed) == 2
        result1 = await governed[0].call("q1")
        result2 = await governed[1].call("q2")
        assert result1 == "async search result"
        assert result2 == "async search result"

    @pytest.mark.anyio
    async def test_empty_list(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        governed = govern_llamaindex_tools_async(async_client, [])
        assert governed == []
