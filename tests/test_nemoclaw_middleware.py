"""Tests for sidclaw.middleware.nemoclaw — NemoClaw governance wrappers."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx

from sidclaw import AsyncSidClaw, SidClaw
from sidclaw._errors import ActionDeniedError
from sidclaw.middleware.nemoclaw import (
    NemoClawGovernanceConfig,
    create_nemoclaw_proxy,
    govern_nemoclaw_tool,
    govern_nemoclaw_tool_async,
    govern_nemoclaw_tools,
    govern_nemoclaw_tools_async,
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
            "decided_at": "2026-03-27T00:00:00Z",
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
            "decided_at": "2026-03-27T00:00:00Z",
            "approver_name": "admin",
            "decision_note": "Not authorized",
        },
    )


def _outcome_response():
    return httpx.Response(204)


class MockNemoClawTool:
    """Duck-typed NemoClaw tool for testing."""

    def __init__(self, name: str = "code_exec", description: str = "Execute code in sandbox") -> None:
        self.name = name
        self.description = description
        self.parameters = {"type": "object", "properties": {"code": {"type": "string"}}}
        self.calls: list[dict] = []

    def execute(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return f"result for {kwargs}"


class MockNemoClawToolAsync:
    """Async duck-typed NemoClaw tool for testing."""

    def __init__(self, name: str = "code_exec", description: str = "Execute code in sandbox") -> None:
        self.name = name
        self.description = description
        self.parameters = {"type": "object", "properties": {"code": {"type": "string"}}}
        self.calls: list[dict] = []

    async def execute(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return f"result for {kwargs}"


# ---------------------------------------------------------------------------
# Tests: govern_nemoclaw_tool (sync)
# ---------------------------------------------------------------------------


class TestGovernNemoClawToolSync:
    def test_allow_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        governed = govern_nemoclaw_tool(client, tool)

        result = governed.execute(code="print('hello')")

        assert result == "result for {'code': \"print('hello')\"}"
        assert governed.name == "code_exec"
        assert governed.description == "Execute code in sandbox"
        assert len(tool.calls) == 1
        assert tool.calls[0] == {"code": "print('hello')"}

    def test_deny_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = MockNemoClawTool()
        governed = govern_nemoclaw_tool(client, tool)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.execute(code="rm -rf /")

        assert "Operation not permitted" in str(exc_info.value)
        assert exc_info.value.trace_id == "trace-2"
        assert len(tool.calls) == 0

    def test_approval_required_wait_approved(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        config = NemoClawGovernanceConfig(wait_for_approval=True)
        governed = govern_nemoclaw_tool(client, tool, config)

        result = governed.execute(code="deploy()")
        assert "result for" in result
        assert len(tool.calls) == 1

    def test_approval_required_wait_denied(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_denied_response())

        tool = MockNemoClawTool()
        config = NemoClawGovernanceConfig(wait_for_approval=True)
        governed = govern_nemoclaw_tool(client, tool, config)

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.execute(code="deploy()")

        assert "Approval denied" in str(exc_info.value)
        assert "Not authorized" in str(exc_info.value)
        assert len(tool.calls) == 0

    def test_approval_required_no_wait_default(self, client: SidClaw, mock_api: respx.MockRouter):
        """NemoClaw defaults to wait_for_approval=False."""
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())

        tool = MockNemoClawTool()
        governed = govern_nemoclaw_tool(client, tool)  # default config

        with pytest.raises(ActionDeniedError) as exc_info:
            governed.execute(code="deploy()")

        assert "Approval required" in str(exc_info.value)
        assert "approval-1" in str(exc_info.value)
        assert len(tool.calls) == 0

    def test_target_integration_is_nemoclaw(self, client: SidClaw, mock_api: respx.MockRouter):
        """target_integration should always be 'nemoclaw'."""
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        governed = govern_nemoclaw_tool(client, tool)
        governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["target_integration"] == "nemoclaw"

    def test_default_resource_scope(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        governed = govern_nemoclaw_tool(client, tool)
        governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["resource_scope"] == "nemoclaw_sandbox"

    def test_per_tool_data_classification_dict(self, client: SidClaw, mock_api: respx.MockRouter):
        """data_classification as dict maps tool names to classifications."""
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool(name="send_email")
        config = NemoClawGovernanceConfig(
            data_classification={"send_email": "confidential", "read_docs": "public"},
        )
        governed = govern_nemoclaw_tool(client, tool, config)
        governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "confidential"

    def test_per_tool_data_classification_dict_fallback(self, client: SidClaw, mock_api: respx.MockRouter):
        """Unmapped tool names fall back to default_classification."""
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool(name="unknown_tool")
        config = NemoClawGovernanceConfig(
            data_classification={"send_email": "confidential"},
            default_classification="restricted",
        )
        governed = govern_nemoclaw_tool(client, tool, config)
        governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "restricted"

    def test_single_string_data_classification(self, client: SidClaw, mock_api: respx.MockRouter):
        """data_classification as a single string applies to all tools."""
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        config = NemoClawGovernanceConfig(data_classification="confidential")
        governed = govern_nemoclaw_tool(client, tool, config)
        governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "confidential"

    def test_sandbox_name_in_context(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        config = NemoClawGovernanceConfig(sandbox_name="secure-sandbox-42")
        governed = govern_nemoclaw_tool(client, tool, config)
        governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["context"]["sandbox_name"] == "secure-sandbox-42"

    def test_context_includes_runtime(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        governed = govern_nemoclaw_tool(client, tool)
        governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["context"]["runtime"] == "nemoclaw"
        assert body["context"]["tool_name"] == "code_exec"
        assert body["context"]["tool_params"] == {"code": "test"}

    def test_tool_error_records_outcome(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        outcome_route = mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawTool()
        tool.execute = MagicMock(side_effect=RuntimeError("Sandbox crashed"))  # type: ignore[assignment]

        governed = govern_nemoclaw_tool(client, tool)

        with pytest.raises(RuntimeError, match="Sandbox crashed"):
            governed.execute(code="bad code")

        # Verify outcome was recorded (with error)
        import json
        outcome_body = json.loads(outcome_route.calls[0].request.content)
        assert outcome_body["status"] == "error"

    def test_preserves_tool_attributes(self, client: SidClaw, mock_api: respx.MockRouter):
        tool = MockNemoClawTool(name="custom-sandbox-tool", description="Custom sandbox tool")
        governed = govern_nemoclaw_tool(client, tool)

        assert governed.name == "custom-sandbox-tool"
        assert governed.description == "Custom sandbox tool"
        assert governed.parameters == {"type": "object", "properties": {"code": {"type": "string"}}}


# ---------------------------------------------------------------------------
# Tests: govern_nemoclaw_tool_async
# ---------------------------------------------------------------------------


class TestGovernNemoClawToolAsync:
    @pytest.mark.anyio
    async def test_allow_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawToolAsync()
        governed = govern_nemoclaw_tool_async(async_client, tool)

        result = await governed.execute(code="print('hello')")
        assert "result for" in result
        assert len(tool.calls) == 1

    @pytest.mark.anyio
    async def test_deny_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        tool = MockNemoClawToolAsync()
        governed = govern_nemoclaw_tool_async(async_client, tool)

        with pytest.raises(ActionDeniedError):
            await governed.execute(code="test")

        assert len(tool.calls) == 0

    @pytest.mark.anyio
    async def test_approval_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawToolAsync()
        config = NemoClawGovernanceConfig(wait_for_approval=True)
        governed = govern_nemoclaw_tool_async(async_client, tool, config)

        result = await governed.execute(code="deploy()")
        assert "result for" in result

    @pytest.mark.anyio
    async def test_target_integration_is_nemoclaw(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool = MockNemoClawToolAsync()
        governed = govern_nemoclaw_tool_async(async_client, tool)
        await governed.execute(code="test")

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["target_integration"] == "nemoclaw"


# ---------------------------------------------------------------------------
# Tests: govern_nemoclaw_tools (sync)
# ---------------------------------------------------------------------------


class TestGovernNemoClawToolsSync:
    def test_wraps_all_tools(self, client: SidClaw):
        tool1 = MockNemoClawTool(name="code_exec")
        tool2 = MockNemoClawTool(name="file_write")

        governed = govern_nemoclaw_tools(client, [tool1, tool2])

        assert len(governed) == 2
        assert governed[0].name == "code_exec"
        assert governed[1].name == "file_write"

    def test_executes_wrapped_tools(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool1 = MockNemoClawTool(name="tool-alpha")
        governed = govern_nemoclaw_tools(client, [tool1])
        result = governed[0].execute(code="test")

        assert "result for" in result
        assert len(tool1.calls) == 1


# ---------------------------------------------------------------------------
# Tests: govern_nemoclaw_tools_async
# ---------------------------------------------------------------------------


class TestGovernNemoClawToolsAsync:
    @pytest.mark.anyio
    async def test_wraps_all_tools(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        tool1 = MockNemoClawToolAsync(name="code_exec")
        tool2 = MockNemoClawToolAsync(name="file_write")

        governed = govern_nemoclaw_tools_async(async_client, [tool1, tool2])

        assert len(governed) == 2
        assert governed[0].name == "code_exec"
        assert governed[1].name == "file_write"

        result = await governed[0].execute(code="test")
        assert "result for" in result


# ---------------------------------------------------------------------------
# Tests: create_nemoclaw_proxy
# ---------------------------------------------------------------------------


class TestCreateNemoClawProxy:
    def test_default_config(self):
        result = create_nemoclaw_proxy(
            api_key="sk-test-123",
            agent_id="agent-1",
            upstream_command="nemoclaw-server",
            upstream_args=["--sandbox", "secure"],
        )

        assert "mcpServers" in result
        server = result["mcpServers"]["governed"]
        assert server["command"] == "npx"
        assert server["args"] == ["-y", "@sidclaw/sdk", "mcp-proxy"]
        assert server["env"]["SIDCLAW_API_KEY"] == "sk-test-123"
        assert server["env"]["SIDCLAW_AGENT_ID"] == "agent-1"
        assert server["env"]["SIDCLAW_API_URL"] == "https://api.sidclaw.com"
        assert server["env"]["SIDCLAW_UPSTREAM_CMD"] == "nemoclaw-server"
        assert server["env"]["SIDCLAW_UPSTREAM_ARGS"] == "--sandbox,secure"

    def test_custom_api_url(self):
        result = create_nemoclaw_proxy(
            api_key="sk-test",
            agent_id="agent-1",
            upstream_command="nemoclaw",
            upstream_args=[],
            api_url="https://custom.api.com",
        )

        server = result["mcpServers"]["governed"]
        assert server["env"]["SIDCLAW_API_URL"] == "https://custom.api.com"

    def test_custom_server_name(self):
        result = create_nemoclaw_proxy(
            api_key="sk-test",
            agent_id="agent-1",
            upstream_command="nemoclaw",
            upstream_args=["--flag"],
            server_name="nemoclaw-governed",
        )

        assert "nemoclaw-governed" in result["mcpServers"]
        assert "governed" not in result["mcpServers"]
