import httpx
import pytest
import respx

from sidclaw import AsyncSidClaw
from sidclaw._errors import ApprovalExpiredError, ApprovalTimeoutError, AuthenticationError


@pytest.fixture
def async_mock_api():
    with respx.mock(base_url="https://test.api") as respx_mock:
        yield respx_mock


class TestAsyncEvaluate:
    async def test_evaluate_allow(self, async_client, async_mock_api):
        async_mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "trace_id": "trace-1",
                    "approval_request_id": None,
                    "reason": "ok",
                    "policy_rule_id": None,
                },
            )
        )
        result = await async_client.evaluate(
            {
                "operation": "test",
                "target_integration": "test",
                "resource_scope": "*",
                "data_classification": "public",
            }
        )
        assert result.decision == "allow"

    async def test_evaluate_401(self, async_client, async_mock_api):
        async_mock_api.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                401,
                json={"error": "unauthorized", "message": "Bad key", "status": 401},
            )
        )
        with pytest.raises(AuthenticationError):
            await async_client.evaluate(
                {
                    "operation": "test",
                    "target_integration": "test",
                    "resource_scope": "*",
                    "data_classification": "public",
                }
            )


class TestAsyncWaitForApproval:
    async def test_approved(self, async_client, async_mock_api):
        async_mock_api.get("/api/v1/approvals/a-1/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "a-1",
                    "status": "approved",
                    "decided_at": "2026-01-01T00:00:00Z",
                    "approver_name": "Admin",
                    "decision_note": "ok",
                },
            )
        )
        result = await async_client.wait_for_approval("a-1")
        assert result.status == "approved"

    async def test_timeout(self, async_client, async_mock_api):
        async_mock_api.get("/api/v1/approvals/a-1/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "a-1",
                    "status": "pending",
                    "decided_at": None,
                    "approver_name": None,
                    "decision_note": None,
                },
            )
        )
        with pytest.raises(ApprovalTimeoutError):
            await async_client.wait_for_approval("a-1", {"timeout": 0.1, "poll_interval": 0.05})

    async def test_expired(self, async_client, async_mock_api):
        async_mock_api.get("/api/v1/approvals/a-1/status").mock(
            return_value=httpx.Response(
                200,
                json={"id": "a-1", "status": "expired", "decided_at": None, "approver_name": None, "decision_note": None},
            )
        )
        with pytest.raises(ApprovalExpiredError):
            await async_client.wait_for_approval("a-1")


class TestAsyncRecordOutcome:
    async def test_record_success(self, async_client, async_mock_api):
        async_mock_api.post("/api/v1/traces/t-1/outcome").mock(return_value=httpx.Response(200, json={}))
        await async_client.record_outcome("t-1", {"status": "success"})


class TestAsyncContextManager:
    async def test_context_manager(self):
        async with AsyncSidClaw(api_key="test-key", base_url="https://test.api", agent_id="test-agent") as client:
            assert client is not None
