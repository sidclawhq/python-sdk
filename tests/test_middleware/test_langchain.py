import httpx
import pytest
import respx

from sidclaw import SidClaw
from sidclaw._errors import ActionDeniedError


@pytest.fixture
def lc_client():
    return SidClaw(api_key="test-key", base_url="https://test.api", agent_id="test-agent", max_retries=0)


@pytest.fixture
def lc_mock():
    with respx.mock(base_url="https://test.api") as m:
        yield m


class FakeTool:
    """Minimal LangChain tool-like for testing without importing langchain."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    def invoke(self, input, config=None, **kwargs):
        return f"result:{input}"

    async def ainvoke(self, input, config=None, **kwargs):
        return f"async_result:{input}"


def test_govern_tool_allow(lc_client, lc_mock):
    """Test that govern_tool with _base helpers works for allow decisions."""
    from sidclaw.middleware._base import evaluate_governance_sync, record_outcome_sync

    lc_mock.post("/api/v1/evaluate").mock(
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
    outcome_route = lc_mock.post("/api/v1/traces/t-1/outcome").mock(return_value=httpx.Response(200, json={}))

    tool = FakeTool("search", "Search tool")
    decision = evaluate_governance_sync(
        lc_client,
        tool.name,
        target_integration=tool.name,
        context={"input": "test", "tool_description": tool.description},
    )
    result = tool.invoke("test")
    record_outcome_sync(lc_client, decision.trace_id)

    assert result == "result:test"
    assert outcome_route.call_count == 1


def test_govern_tool_deny(lc_client, lc_mock):
    from sidclaw.middleware._base import evaluate_governance_sync

    lc_mock.post("/api/v1/evaluate").mock(
        return_value=httpx.Response(
            200,
            json={
                "decision": "deny",
                "trace_id": "t-2",
                "approval_request_id": None,
                "reason": "Not allowed",
                "policy_rule_id": "r-1",
            },
        )
    )

    with pytest.raises(ActionDeniedError):
        evaluate_governance_sync(lc_client, "search", target_integration="search")
