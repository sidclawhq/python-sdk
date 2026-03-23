import httpx
import pytest
import respx

from sidclaw import SidClaw
from sidclaw._errors import ActionDeniedError
from sidclaw.middleware.generic import GovernanceConfig, with_governance


@pytest.fixture
def gov_client():
    return SidClaw(api_key="test-key", base_url="https://test.api", agent_id="test-agent", max_retries=0)


@pytest.fixture
def gov_mock():
    with respx.mock(base_url="https://test.api") as m:
        yield m


class TestWithGovernance:
    def test_allow_executes_and_records(self, gov_client, gov_mock):
        gov_mock.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "trace_id": "t-1",
                    "approval_request_id": None,
                    "reason": "ok",
                    "policy_rule_id": None,
                },
            )
        )
        outcome_route = gov_mock.post("/api/v1/traces/t-1/outcome").mock(return_value=httpx.Response(200, json={}))

        @with_governance(
            gov_client,
            GovernanceConfig(operation="test_op", target_integration="test_svc"),
        )
        def my_func() -> str:
            return "result"

        assert my_func() == "result"
        assert outcome_route.call_count == 1

    def test_deny_raises(self, gov_client, gov_mock):
        gov_mock.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "deny",
                    "trace_id": "t-2",
                    "approval_request_id": None,
                    "reason": "Blocked",
                    "policy_rule_id": "r-1",
                },
            )
        )

        @with_governance(
            gov_client,
            GovernanceConfig(operation="test_op", target_integration="test_svc"),
        )
        def my_func() -> str:
            return "should not run"

        with pytest.raises(ActionDeniedError) as exc_info:
            my_func()
        assert "Blocked" in str(exc_info.value)

    def test_records_error_on_exception(self, gov_client, gov_mock):
        gov_mock.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "decision": "allow",
                    "trace_id": "t-3",
                    "approval_request_id": None,
                    "reason": "ok",
                    "policy_rule_id": None,
                },
            )
        )
        outcome_route = gov_mock.post("/api/v1/traces/t-3/outcome").mock(return_value=httpx.Response(200, json={}))

        @with_governance(
            gov_client,
            GovernanceConfig(operation="test_op", target_integration="test_svc"),
        )
        def my_func() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            my_func()
        assert outcome_route.call_count == 1
