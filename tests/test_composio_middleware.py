"""Tests for sidclaw.middleware.composio — Composio governance wrappers."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import respx

from sidclaw import AsyncSidClaw, SidClaw
from sidclaw._errors import ActionDeniedError, ApprovalTimeoutError
from sidclaw.middleware.composio import (
    ComposioGovernanceConfig,
    create_composio_governance_modifiers,
    create_composio_governance_modifiers_async,
    govern_composio_execution,
    govern_composio_execution_async,
    map_composio_slug,
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


class MockComposioTools:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def execute(self, slug: str, *, user_id: str | None = None, arguments: dict | None = None, **kwargs) -> dict:
        self.calls.append({"slug": slug, "user_id": user_id, "arguments": arguments})
        return {"data": {"id": 123}, "error": None, "successful": True}


class MockComposioToolsAsync:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, slug: str, *, user_id: str | None = None, arguments: dict | None = None, **kwargs) -> dict:
        self.calls.append({"slug": slug, "user_id": user_id, "arguments": arguments})
        return {"data": {"id": 123}, "error": None, "successful": True}


class MockComposio:
    def __init__(self, async_mode: bool = False) -> None:
        self.tools = MockComposioToolsAsync() if async_mode else MockComposioTools()


# ---------------------------------------------------------------------------
# Tests: map_composio_slug
# ---------------------------------------------------------------------------


class TestMapComposioSlug:
    def test_github_create_issue(self):
        assert map_composio_slug("GITHUB_CREATE_ISSUE") == ("create_issue", "github")

    def test_gmail_send_email(self):
        assert map_composio_slug("GMAIL_SEND_EMAIL") == ("send_email", "gmail")

    def test_multi_word_action(self):
        assert map_composio_slug("SLACK_SEND_DIRECT_MESSAGE") == ("send_direct_message", "slack")

    def test_single_word_slug(self):
        assert map_composio_slug("WEBHOOK") == ("webhook", "webhook")

    def test_two_part_slug(self):
        assert map_composio_slug("NOTION_QUERY") == ("query", "notion")


# ---------------------------------------------------------------------------
# Tests: govern_composio_execution (sync)
# ---------------------------------------------------------------------------


class TestGovernComposioExecutionSync:
    def test_allow_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        composio = MockComposio()
        execute = govern_composio_execution(client, composio)

        result = execute("GITHUB_CREATE_ISSUE", user_id="user_123", arguments={"title": "Bug"})

        assert result["successful"] is True
        assert composio.tools.calls[0]["slug"] == "GITHUB_CREATE_ISSUE"

    def test_deny_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        composio = MockComposio()
        execute = govern_composio_execution(client, composio)

        with pytest.raises(ActionDeniedError) as exc_info:
            execute("SALESFORCE_CREATE_LEAD", user_id="u", arguments={})

        assert "Operation not permitted" in str(exc_info.value)
        assert exc_info.value.trace_id == "trace-2"
        assert len(composio.tools.calls) == 0

    def test_approval_required_approved(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        composio = MockComposio()
        execute = govern_composio_execution(client, composio, ComposioGovernanceConfig(wait_for_approval=True))

        result = execute("GMAIL_SEND_EMAIL", user_id="u", arguments={"to": "a@b.com"})
        assert result["successful"] is True
        assert len(composio.tools.calls) == 1

    def test_approval_required_denied(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_denied_response())

        composio = MockComposio()
        execute = govern_composio_execution(client, composio, ComposioGovernanceConfig(wait_for_approval=True))

        with pytest.raises(ActionDeniedError) as exc_info:
            execute("GMAIL_SEND_EMAIL", user_id="u", arguments={})

        assert "Approval denied" in str(exc_info.value)
        assert "Not authorized" in str(exc_info.value)
        assert len(composio.tools.calls) == 0

    def test_approval_required_no_wait(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())

        composio = MockComposio()
        execute = govern_composio_execution(client, composio, ComposioGovernanceConfig(wait_for_approval=False))

        with pytest.raises(ActionDeniedError) as exc_info:
            execute("GMAIL_SEND_EMAIL", user_id="u", arguments={})

        assert "Approval required" in str(exc_info.value)
        assert "approval-1" in str(exc_info.value)
        assert len(composio.tools.calls) == 0

    def test_per_toolkit_classification(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        composio = MockComposio()
        config = ComposioGovernanceConfig(
            data_classification={"SALESFORCE": "confidential"},
            default_classification="internal",
        )
        execute = govern_composio_execution(client, composio, config)
        execute("SALESFORCE_CREATE_LEAD", user_id="u", arguments={})

        # Verify the request body
        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "confidential"

    def test_default_classification_fallback(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        composio = MockComposio()
        config = ComposioGovernanceConfig(default_classification="restricted")
        execute = govern_composio_execution(client, composio, config)
        execute("NOTION_CREATE_PAGE", user_id="u", arguments={})

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "restricted"

    def test_composio_error_records_trace(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        composio = MockComposio()
        # Make execute raise
        composio.tools.execute = MagicMock(side_effect=RuntimeError("Composio API error"))  # type: ignore[assignment]

        execute = govern_composio_execution(client, composio)

        with pytest.raises(RuntimeError, match="Composio API error"):
            execute("GITHUB_CREATE_ISSUE", user_id="u", arguments={})

        # Outcome should still be recorded


# ---------------------------------------------------------------------------
# Tests: govern_composio_execution_async
# ---------------------------------------------------------------------------


class TestGovernComposioExecutionAsync:
    @pytest.mark.anyio
    async def test_allow_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        composio = MockComposio(async_mode=True)
        execute = govern_composio_execution_async(async_client, composio)

        result = await execute("GITHUB_CREATE_ISSUE", user_id="user_123", arguments={"title": "Bug"})
        assert result["successful"] is True

    @pytest.mark.anyio
    async def test_deny_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        composio = MockComposio(async_mode=True)
        execute = govern_composio_execution_async(async_client, composio)

        with pytest.raises(ActionDeniedError):
            await execute("SALESFORCE_CREATE_LEAD", user_id="u", arguments={})

    @pytest.mark.anyio
    async def test_approval_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_approval_required_response())
        mock_api.get("/api/v1/approvals/approval-1/status").mock(return_value=_approval_approved_response())
        mock_api.post("/api/v1/traces/trace-3/outcome").mock(return_value=_outcome_response())

        composio = MockComposio(async_mode=True)
        execute = govern_composio_execution_async(
            async_client, composio, ComposioGovernanceConfig(wait_for_approval=True)
        )

        result = await execute("GMAIL_SEND_EMAIL", user_id="u", arguments={"to": "a@b.com"})
        assert result["successful"] is True


# ---------------------------------------------------------------------------
# Tests: create_composio_governance_modifiers (sync)
# ---------------------------------------------------------------------------


class TestComposioGovernanceModifiers:
    def test_before_execute_blocks_on_deny(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        modifiers = create_composio_governance_modifiers(client)

        with pytest.raises(ActionDeniedError):
            modifiers["before_execute"]("SALESFORCE_DELETE_RECORD", "SALESFORCE", {"id": "123"})

    def test_before_and_after_execute_flow(self, client: SidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        modifiers = create_composio_governance_modifiers(client)

        params = modifiers["before_execute"]("GITHUB_CREATE_ISSUE", "GITHUB", {"title": "Bug"})
        assert params == {"title": "Bug"}

        result = modifiers["after_execute"]("GITHUB_CREATE_ISSUE", "GITHUB", {"data": {"id": 1}})
        assert result == {"data": {"id": 1}}

    def test_after_execute_no_inflight(self, client: SidClaw, mock_api: respx.MockRouter):
        modifiers = create_composio_governance_modifiers(client)
        result = modifiers["after_execute"]("UNKNOWN_TOOL", "UNKNOWN", {"data": {}})
        assert result == {"data": {}}

    def test_data_classification_config(self, client: SidClaw, mock_api: respx.MockRouter):
        route = mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())

        config = ComposioGovernanceConfig(data_classification={"GMAIL": "confidential"})
        modifiers = create_composio_governance_modifiers(client, config)
        modifiers["before_execute"]("GMAIL_SEND_EMAIL", "GMAIL", {})

        import json
        body = json.loads(route.calls[0].request.content)
        assert body["data_classification"] == "confidential"


# ---------------------------------------------------------------------------
# Tests: create_composio_governance_modifiers_async
# ---------------------------------------------------------------------------


class TestComposioGovernanceModifiersAsync:
    @pytest.mark.anyio
    async def test_before_execute_blocks_on_deny(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_deny_response())

        modifiers = create_composio_governance_modifiers_async(async_client)

        with pytest.raises(ActionDeniedError):
            await modifiers["before_execute"]("SALESFORCE_DELETE_RECORD", "SALESFORCE", {"id": "123"})

    @pytest.mark.anyio
    async def test_before_and_after_execute_flow(self, async_client: AsyncSidClaw, mock_api: respx.MockRouter):
        mock_api.post("/api/v1/evaluate").mock(return_value=_allow_response())
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=_outcome_response())

        modifiers = create_composio_governance_modifiers_async(async_client)

        params = await modifiers["before_execute"]("GITHUB_CREATE_ISSUE", "GITHUB", {"title": "Bug"})
        assert params == {"title": "Bug"}

        result = await modifiers["after_execute"]("GITHUB_CREATE_ISSUE", "GITHUB", {"data": {"id": 1}})
        assert result == {"data": {"id": 1}}
