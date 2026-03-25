"""Tests for sidclaw.middleware.claude_agent_sdk — Claude Agent SDK governance wrappers."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx

from sidclaw import AsyncSidClaw, SidClaw
from sidclaw._errors import ActionDeniedError, ApprovalTimeoutError
from sidclaw.middleware.claude_agent_sdk import (
    ClaudeAgentGovernanceConfig,
    govern_claude_agent_tool,
    govern_claude_agent_tool_async,
    govern_claude_agent_tools,
    govern_claude_agent_tools_async,
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


class MockClaudeAgentTool:
    """Duck-typed Claude Agent SDK tool for testing."""

    def __init__(self, name: str = "search", description: str = "Search the knowledge base") -> None:
        self.name = name
        self.description = description
        self.parameters = {"type": "object", "properties": {"query": {"type": "string"}}}
        self.calls: list[dict] = []

    def execute(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return f"result for {kwargs}"


class MockClaudeAgentToolAsync:
    """Async duck-typed Claude Agent SDK tool for testing."""

    def __init__(self, name: str = "search", description: str = "Search the knowledge base") -> None:
        self.name = name
        self.description = description
        self.parameters = {"type": "object", "properties": {"query": {"type": "string"}}}
        self.calls: list[dict] = []

    async def execute(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return f"result for {kwargs}"


# ---------------------------------------------------------------------------
# Tests: govern_claude_agent_tool (sync)
# ---------------------------------------------------------------------------


class TestGovernClaudeAgentToolSync:
    def test_allow_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentTool()
        governed = govern_claude_agent_tool(client, tool)

        result = governed.execute(query="test")

        assert result == "result for {'query': 'test'}"
        assert governed.name == "search"
        assert governed.description == "Search the knowledge base"
        assert len(tool.calls) == 1
        assert tool.calls[0] == {"query": "test"}

    def test_deny_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = MockClaudeAgentTool()
        governed = govern_claude_agent_tool(client, tool)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.execute(query="test")

        assert "Operation not permitted" in str(exc_info.value)
        assert exc_info.value.trace_id == "trace-2"
        assert len(tool.calls) == 0

    def test_approval_required_approved(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentTool()
        governed = govern_claude_agent_tool(client, tool, ClaudeAgentGovernanceConfig(wait_for_approval=True))

        result = governed.execute(query="test")
        assert "result for" in result
        assert len(tool.calls) == 1

    def test_approval_required_denied(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_denied_response())

        tool = MockClaudeAgentTool()
        governed = govern_claude_agent_tool(client, tool, ClaudeAgentGovernanceConfig(wait_for_approval=True))

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.execute(query="test")

        assert "Approval denied" in str(exc_info.value)
        assert "Not authorized" in str(exc_info.value)
        assert len(tool.calls) == 0

    def test_approval_required_no_wait(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())

        tool = MockClaudeAgentTool()
        governed = govern_claude_agent_tool(client, tool, ClaudeAgentGovernanceConfig(wait_for_approval=False))

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.execute(query="test")

        assert "Approval required" in str(exc_info.value)
        assert "approval-1" in str(exc_info.value)
        assert len(tool.calls) == 0

    def test_custom_data_classification(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentTool()
        config = ClaudeAgentGovernanceConfig(data_classification="confidential")
        governed = govern_claude_agent_tool(client, tool, config)
        governed.execute(query="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "confidential"

    def test_custom_resource_scope(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentTool()
        config = ClaudeAgentGovernanceConfig(resource_scope="enterprise_data")
        governed = govern_claude_agent_tool(client, tool, config)
        governed.execute(query="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["resource_scope"] == "enterprise_data"

    def test_custom_target_integration(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentTool()
        config = ClaudeAgentGovernanceConfig(target_integration="knowledge_base")
        governed = govern_claude_agent_tool(client, tool, config)
        governed.execute(query="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["target_integration"] == "knowledge_base"

    def test_tool_error_records_outcome(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentTool()
        tool.execute = MagicMock(side_effect=RuntimeError("Tool execution failed"))  # type: ignore[assignment]

        governed = govern_claude_agent_tool(client, tool)

        with pytest.raises(RuntimeError, match="Tool execution failed"):
            governed.execute(query="test")

    def test_preserves_tool_attributes(self, client: SidClaw, mock_api: respx.MockRouter):
        tool = MockClaudeAgentTool(name="custom-tool", description="A custom tool")
        governed = govern_claude_agent_tool(client, tool)

        assert governed.name == "custom-tool"
        assert governed.description == "A custom tool"
        assert governed.parameters == {"type": "object", "properties": {"query": {"type": "string"}}}

    def test_context_includes_framework(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentTool()
        governed = govern_claude_agent_tool(client, tool)
        governed.execute(query="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["context"]["framework"] == "claude_agent_sdk"
        assert body["context"]["tool_name"] == "search"


# ---------------------------------------------------------------------------
# Tests: govern_claude_agent_tool_async
# ---------------------------------------------------------------------------


class TestGovernClaudeAgentToolAsync:
    @pytest.mark.anyio
    async def test_allow_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentToolAsync()
        governed = govern_claude_agent_tool_async(async_client, tool)

        result = await governed.execute(query="test")
        assert "result for" in result
        assert len(tool.calls) == 1

    @pytest.mark.anyio
    async def test_deny_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = MockClaudeAgentToolAsync()
        governed = govern_claude_agent_tool_async(async_client, tool)

        with pytest.raises(ActionDeniedError):
            await governed.execute(query="test")

        assert len(tool.calls) == 0

    @pytest.mark.anyio
    async def test_approval_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        tool = MockClaudeAgentToolAsync()
        governed = govern_claude_agent_tool_async(
            async_client, tool, ClaudeAgentGovernanceConfig(wait_for_approval=True)
        )

        result = await governed.execute(query="test")
        assert "result for" in result


# ---------------------------------------------------------------------------
# Tests: govern_claude_agent_tools (sync)
# ---------------------------------------------------------------------------


class TestGovernClaudeAgentToolsSync:
    def test_wraps_all_tools(self, client: SidClaw):
        tool1 = MockClaudeAgentTool(name="search")
        tool2 = MockClaudeAgentTool(name="write")

        governed = govern_claude_agent_tools(client, [tool1, tool2])

        assert len(governed) == 2
        assert governed[0].name == "search"
        assert governed[1].name == "write"

    def test_uses_each_tool_name_as_target(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool1 = MockClaudeAgentTool(name="tool-alpha")
        governed = govern_claude_agent_tools(client, [tool1])
        governed[0].execute(query="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["target_integration"] == "tool-alpha"


# ---------------------------------------------------------------------------
# Tests: govern_claude_agent_tools_async
# ---------------------------------------------------------------------------


class TestGovernClaudeAgentToolsAsync:
    @pytest.mark.anyio
    async def test_wraps_all_tools(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool1 = MockClaudeAgentToolAsync(name="search")
        tool2 = MockClaudeAgentToolAsync(name="write")

        governed = govern_claude_agent_tools_async(async_client, [tool1, tool2])

        assert len(governed) == 2
        assert governed[0].name == "search"
        assert governed[1].name == "write"

        result = await governed[0].execute(query="test")
        assert "result for" in result
