"""Tests for sidclaw.middleware.google_adk — Google ADK governance wrappers."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx

from sidclaw import AsyncSidClaw, SidClaw
from sidclaw._errors import ActionDeniedError, ApprovalTimeoutError
from sidclaw.middleware.google_adk import (
    GoogleADKGovernanceConfig,
    govern_google_adk_tool,
    govern_google_adk_tool_async,
    govern_google_adk_tools,
    govern_google_adk_tools_async,
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


def _approval_approved_response():
    return httpx.Response(
        200,
        json={
            "id": "approval-1",
            "status": "approved",
            "decided_at": "2026-03-25T00:00:00Z",
            "approver_name": "admin",
            "decision_note": "Looks good",
        },
    )


def _approval_denied_response():
    return httpx.Response(
        200,
        json={
            "id": "approval-1",
            "status": "denied",
            "decided_at": "2026-03-25T00:00:00Z",
            "approver_name": "admin",
            "decision_note": "Not authorized",
        },
    )


def _outcome_response():
    return httpx.Response(204)


class MockGoogleADKTool:
    """Mock Google ADK tool with name, description, and callable."""

    def __init__(self, name: str = "search_docs", description: str = "Search documentation"):
        self.name = name
        self.description = description
        self.calls: list[dict] = []

    def __call__(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"results": ["doc1", "doc2"]}


class MockGoogleADKToolAsync:
    """Mock async Google ADK tool."""

    def __init__(self, name: str = "search_docs", description: str = "Search documentation"):
        self.name = name
        self.description = description
        self.calls: list[dict] = []

    async def __call__(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"results": ["doc1", "doc2"]}


class MockGoogleADKToolWithExecute:
    """Mock Google ADK tool using .execute() method (TypeScript-style)."""

    def __init__(self, name: str = "search_docs", description: str = "Search documentation"):
        self.name = name
        self.description = description
        self.calls: list[dict] = []

    def execute(self, params: dict) -> dict:
        self.calls.append(params)
        return {"results": ["doc1", "doc2"]}


# ---------------------------------------------------------------------------
# Tests: govern_google_adk_tool (sync)
# ---------------------------------------------------------------------------


class TestGovernGoogleADKToolSync:
    def test_allow_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKTool()
        governed = govern_google_adk_tool(client, tool)

        result = governed(query="hello")

        assert result == {"results": ["doc1", "doc2"]}
        assert tool.calls == [{"query": "hello"}]

    def test_preserves_metadata(self, client: SidClaw, mock_api: respx.MockRouter):
        tool = MockGoogleADKTool(name="create_ticket", description="Create a support ticket")
        governed = govern_google_adk_tool(client, tool)

        assert governed.name == "create_ticket"
        assert governed.description == "Create a support ticket"
        assert getattr(governed, "__sidclaw_governed") is True

    def test_deny_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = MockGoogleADKTool()
        governed = govern_google_adk_tool(client, tool)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed(query="hello")

        assert "Operation not permitted" in str(exc_info.value)
        assert exc_info.value.trace_id == "trace-2"
        assert len(tool.calls) == 0

    def test_approval_required_approved(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKTool()
        config = GoogleADKGovernanceConfig(wait_for_approval=True)
        governed = govern_google_adk_tool(client, tool, config)

        result = governed(query="sensitive data")
        assert result == {"results": ["doc1", "doc2"]}
        assert len(tool.calls) == 1

    def test_approval_required_denied(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_denied_response())

        tool = MockGoogleADKTool()
        config = GoogleADKGovernanceConfig(wait_for_approval=True)
        governed = govern_google_adk_tool(client, tool, config)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed(query="hello")

        assert "Approval denied" in str(exc_info.value)
        assert "Not authorized" in str(exc_info.value)
        assert len(tool.calls) == 0

    def test_approval_required_no_wait(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())

        tool = MockGoogleADKTool()
        config = GoogleADKGovernanceConfig(wait_for_approval=False)
        governed = govern_google_adk_tool(client, tool, config)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed(query="hello")

        assert "Approval required" in str(exc_info.value)
        assert "approval-1" in str(exc_info.value)
        assert len(tool.calls) == 0

    def test_per_tool_classification(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKTool(name="send_email")
        config = GoogleADKGovernanceConfig(
            data_classification={"send_email": "confidential"},
            default_classification="internal",
        )
        governed = govern_google_adk_tool(client, tool, config)
        governed(to="user@example.com")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "confidential"

    def test_default_classification_fallback(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKTool(name="unknown_tool")
        config = GoogleADKGovernanceConfig(default_classification="restricted")
        governed = govern_google_adk_tool(client, tool, config)
        governed()

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "restricted"

    def test_tool_error_records_trace(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        class FailingTool:
            name = "search_docs"
            description = "Search documentation"

            def __call__(self, **kwargs):
                raise RuntimeError("Tool execution error")

        tool = FailingTool()
        governed = govern_google_adk_tool(client, tool)

        with pytest.raises(RuntimeError, match="Tool execution error"):
            governed(query="hello")

    def test_tool_with_execute_method(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKToolWithExecute()
        governed = govern_google_adk_tool(client, tool)

        result = governed({"query": "hello"})
        assert result == {"results": ["doc1", "doc2"]}
        assert len(tool.calls) == 1

    def test_custom_resource_scope(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKTool()
        config = GoogleADKGovernanceConfig(resource_scope="enterprise_data")
        governed = govern_google_adk_tool(client, tool, config)
        governed(query="hello")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["resource_scope"] == "enterprise_data"


# ---------------------------------------------------------------------------
# Tests: govern_google_adk_tool_async
# ---------------------------------------------------------------------------


class TestGovernGoogleADKToolAsync:
    @pytest.mark.anyio
    async def test_allow_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKToolAsync()
        governed = govern_google_adk_tool_async(async_client, tool)

        result = await governed(query="hello")
        assert result == {"results": ["doc1", "doc2"]}
        assert tool.calls == [{"query": "hello"}]

    @pytest.mark.anyio
    async def test_deny_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = MockGoogleADKToolAsync()
        governed = govern_google_adk_tool_async(async_client, tool)

        with pytest.raises(ActionDeniedError):
            await governed(query="hello")

        assert len(tool.calls) == 0

    @pytest.mark.anyio
    async def test_approval_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        tool = MockGoogleADKToolAsync()
        config = GoogleADKGovernanceConfig(wait_for_approval=True)
        governed = govern_google_adk_tool_async(async_client, tool, config)

        result = await governed(query="sensitive")
        assert result == {"results": ["doc1", "doc2"]}

    @pytest.mark.anyio
    async def test_preserves_metadata(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        tool = MockGoogleADKToolAsync(name="create_ticket", description="Create ticket")
        governed = govern_google_adk_tool_async(async_client, tool)

        assert governed.name == "create_ticket"
        assert governed.description == "Create ticket"
        assert getattr(governed, "__sidclaw_governed") is True


# ---------------------------------------------------------------------------
# Tests: govern_google_adk_tools (sync)
# ---------------------------------------------------------------------------


class TestGovernGoogleADKTools:
    def test_wraps_multiple_tools(self, client: SidClaw, mock_api: respx.MockRouter):
        tools = [
            MockGoogleADKTool(name="tool_a"),
            MockGoogleADKTool(name="tool_b"),
            MockGoogleADKTool(name="tool_c"),
        ]

        governed = govern_google_adk_tools(client, tools)

        assert len(governed) == 3
        assert governed[0].name == "tool_a"
        assert governed[1].name == "tool_b"
        assert governed[2].name == "tool_c"
        assert all(getattr(g, "__sidclaw_governed") for g in governed)

    def test_empty_list(self, client: SidClaw, mock_api: respx.MockRouter):
        governed = govern_google_adk_tools(client, [])
        assert governed == []


# ---------------------------------------------------------------------------
# Tests: govern_google_adk_tools_async
# ---------------------------------------------------------------------------


class TestGovernGoogleADKToolsAsync:
    def test_wraps_multiple_tools(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        tools = [
            MockGoogleADKToolAsync(name="tool_a"),
            MockGoogleADKToolAsync(name="tool_b"),
        ]

        governed = govern_google_adk_tools_async(async_client, tools)

        assert len(governed) == 2
        assert governed[0].name == "tool_a"
        assert governed[1].name == "tool_b"
        assert all(getattr(g, "__sidclaw_governed") for g in governed)
