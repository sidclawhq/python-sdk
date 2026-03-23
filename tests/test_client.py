import httpx
import pytest
import respx

from sidclaw import SidClaw
from sidclaw._errors import (
    ActionDeniedError,
    APIError,
    ApprovalExpiredError,
    ApprovalTimeoutError,
    AuthenticationError,
    PlanLimitError,
    RateLimitError,
)


class TestEvaluate:
    def test_evaluate_allow(self, client, mock_api):
        mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "trace_id": "trace-1",
                    "approval_request_id": None,
                    "reason": "Policy allows",
                    "policy_rule_id": "rule-1",
                },
            )
        )
        result = client.evaluate(
            {
                "operation": "read_docs",
                "target_integration": "knowledge_base",
                "resource_scope": "internal_docs",
                "data_classification": "internal",
            }
        )
        assert result.decision == "allow"
        assert result.trace_id == "trace-1"
        assert result.reason == "Policy allows"

    def test_evaluate_deny(self, client, mock_api):
        mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "deny",
                    "trace_id": "trace-2",
                    "approval_request_id": None,
                    "reason": "Policy denies PII export",
                    "policy_rule_id": "rule-2",
                },
            )
        )
        result = client.evaluate(
            {
                "operation": "export_data",
                "target_integration": "data_service",
                "resource_scope": "customer_pii",
                "data_classification": "restricted",
            }
        )
        assert result.decision == "deny"
        assert result.trace_id == "trace-2"

    def test_evaluate_approval_required(self, client, mock_api):
        mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "approval_required",
                    "trace_id": "trace-3",
                    "approval_request_id": "approval-1",
                    "reason": "Sensitive operation",
                    "policy_rule_id": "rule-3",
                },
            )
        )
        result = client.evaluate(
            {
                "operation": "send_email",
                "target_integration": "email_service",
                "resource_scope": "outbound_email",
                "data_classification": "confidential",
            }
        )
        assert result.decision == "approval_required"
        assert result.approval_request_id == "approval-1"

    def test_evaluate_sends_agent_id(self, client, mock_api):
        route = mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "trace_id": "t",
                    "approval_request_id": None,
                    "reason": "ok",
                    "policy_rule_id": None,
                },
            )
        )
        client.evaluate(
            {
                "operation": "test",
                "target_integration": "test",
                "resource_scope": "*",
                "data_classification": "public",
            }
        )
        request = route.calls[0].request
        import json

        body = json.loads(request.content)
        assert body["agent_id"] == "test-agent"

    def test_evaluate_401_raises_auth_error(self, client, mock_api):
        mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                401,
                json={"error": "unauthorized", "message": "Invalid API key", "status": 401},
            )
        )
        with pytest.raises(AuthenticationError) as exc_info:
            client.evaluate(
                {
                    "operation": "test",
                    "target_integration": "test",
                    "resource_scope": "*",
                    "data_classification": "public",
                }
            )
        assert exc_info.value.status_code == 401

    def test_evaluate_429_raises_rate_limit(self, client, mock_api):
        mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                429,
                json={"error": "rate_limit_exceeded", "message": "Too many requests", "status": 429},
                headers={"Retry-After": "30"},
            )
        )
        with pytest.raises(RateLimitError) as exc_info:
            client.evaluate(
                {
                    "operation": "test",
                    "target_integration": "test",
                    "resource_scope": "*",
                    "data_classification": "public",
                }
            )
        assert exc_info.value.retry_after == 30.0

    def test_evaluate_402_raises_plan_limit(self, client, mock_api):
        mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                402,
                json={
                    "error": "plan_limit_reached",
                    "message": "Agent limit",
                    "status": 402,
                    "details": {"limit": "agents", "current": 5, "max": 5},
                },
            )
        )
        with pytest.raises(PlanLimitError) as exc_info:
            client.evaluate(
                {
                    "operation": "test",
                    "target_integration": "test",
                    "resource_scope": "*",
                    "data_classification": "public",
                }
            )
        assert exc_info.value.status_code == 402
        assert exc_info.value.limit_name == "agents"

    def test_no_retry_on_400(self, client, mock_api):
        route = mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                400,
                json={"error": "bad_request", "message": "Invalid input", "status": 400},
            )
        )
        with pytest.raises(APIError):
            client.evaluate(
                {
                    "operation": "test",
                    "target_integration": "test",
                    "resource_scope": "*",
                    "data_classification": "public",
                }
            )
        assert route.call_count == 1


class TestRetry:
    def test_retry_on_500(self, retry_client, mock_api):
        route = mock_api.post("/api/v1/evaluate")
        route.side_effect = [
            httpx.Response(500, json={"error": "internal", "message": "Server error", "status": 500}),
            httpx.Response(500, json={"error": "internal", "message": "Server error", "status": 500}),
            httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "trace_id": "t",
                    "approval_request_id": None,
                    "reason": "ok",
                    "policy_rule_id": None,
                },
            ),
        ]
        result = retry_client.evaluate(
            {
                "operation": "test",
                "target_integration": "test",
                "resource_scope": "*",
                "data_classification": "public",
            }
        )
        assert result.decision == "allow"
        assert route.call_count == 3


class TestRecordOutcome:
    def test_record_outcome_success(self, client, mock_api):
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=httpx.Response(200, json={}))
        client.record_outcome("trace-1", {"status": "success"})

    def test_record_outcome_error(self, client, mock_api):
        mock_api.post("/api/v1/traces/trace-1/outcome").mock(return_value=httpx.Response(200, json={}))
        client.record_outcome("trace-1", {"status": "error", "metadata": {"error": "Something failed"}})


class TestWaitForApproval:
    def test_wait_for_approval_approved(self, client, mock_api):
        mock_api.get("/api/v1/approvals/approval-1/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "approval-1",
                    "status": "approved",
                    "decided_at": "2026-01-01T00:00:00Z",
                    "approver_name": "Admin",
                    "decision_note": "Looks good",
                },
            )
        )
        result = client.wait_for_approval("approval-1")
        assert result.status == "approved"
        assert result.approver_name == "Admin"

    def test_wait_for_approval_denied(self, client, mock_api):
        mock_api.get("/api/v1/approvals/approval-1/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "approval-1",
                    "status": "denied",
                    "decided_at": "2026-01-01T00:00:00Z",
                    "approver_name": "Admin",
                    "decision_note": "Not allowed",
                },
            )
        )
        result = client.wait_for_approval("approval-1")
        assert result.status == "denied"

    def test_wait_for_approval_timeout(self, client, mock_api):
        mock_api.get("/api/v1/approvals/approval-1/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "approval-1",
                    "status": "pending",
                    "decided_at": None,
                    "approver_name": None,
                    "decision_note": None,
                },
            )
        )
        with pytest.raises(ApprovalTimeoutError):
            client.wait_for_approval("approval-1", {"timeout": 0.1, "poll_interval": 0.05})

    def test_wait_for_approval_expired(self, client, mock_api):
        mock_api.get("/api/v1/approvals/approval-1/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "approval-1",
                    "status": "expired",
                    "decided_at": None,
                    "approver_name": None,
                    "decision_note": None,
                },
            )
        )
        with pytest.raises(ApprovalExpiredError):
            client.wait_for_approval("approval-1")


class TestContextManager:
    def test_context_manager(self):
        with SidClaw(api_key="test-key", base_url="https://test.api", agent_id="test-agent") as client:
            assert client is not None
