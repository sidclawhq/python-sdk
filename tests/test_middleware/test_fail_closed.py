"""The guarded action runs only on an explicit ``allow``.

Two layers enforce this, and these tests cover both:

1. ``EvaluateResponse.decision`` is a ``Literal``, so pydantic rejects any
   value the SDK does not know about before middleware ever sees it.
2. ``evaluate_governance_*`` re-checks for an explicit ``allow`` at the
   decision site.

Layer 2 looks redundant against layer 1 today — that is the point. The
TypeScript SDK had only the equivalent of layer 2, wrote it as a denylist
("raise on deny, raise on approval_required, otherwise proceed"), and shipped
a live governance bypass: any unrecognised decision became ALLOW. Python is
safe from that today only because of layer 1. The moment someone widens the
``PolicyEffect`` literal to add a decision value, layer 1 stops rejecting it
and layer 2 is the only thing standing between a new server decision and an
ungoverned tool call. These tests fail if that guard is ever removed.
"""

import httpx
import pytest
import respx

from sidclaw import AsyncSidClaw, SidClaw
from sidclaw._errors import ActionDeniedError
from sidclaw._types import EvaluateResponse
from sidclaw.middleware._base import evaluate_governance_async, evaluate_governance_sync


def _body(decision: str) -> dict:
    return {
        "decision": decision,
        "trace_id": "t-1",
        "approval_request_id": None,
        "reason": "because",
        "policy_rule_id": None,
    }


@pytest.fixture
def fc_client():
    return SidClaw(api_key="k", base_url="https://fc.api", agent_id="a", max_retries=0)


@pytest.fixture
def fc_async_client():
    return AsyncSidClaw(api_key="k", base_url="https://fc.api", agent_id="a", max_retries=0)


@pytest.fixture
def fc_mock():
    with respx.mock(base_url="https://fc.api") as m:
        yield m


class TestLayerOneRejectsUnknownDecisions:
    """An unrecognised decision never reaches middleware."""

    @pytest.mark.parametrize("decision", ["quarantine", "log", "ALLOW", "Allow", "", "allow_once"])
    def test_unknown_decision_does_not_allow(self, fc_client, fc_mock, decision):
        fc_mock.post("/api/v1/evaluate").mock(return_value=httpx.Response(200, json=_body(decision)))
        # Must raise something. What matters is that it does NOT return and
        # let the caller proceed — that is the fail-open failure mode.
        with pytest.raises(Exception):
            evaluate_governance_sync(fc_client, "op")

    def test_missing_decision_field_does_not_allow(self, fc_client, fc_mock):
        fc_mock.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(200, json={"trace_id": "t-1", "reason": "no decision key"})
        )
        with pytest.raises(Exception):
            evaluate_governance_sync(fc_client, "op")


class TestLayerTwoGuardsTheDecisionSite:
    """The explicit-allow check, exercised directly.

    ``model_construct`` skips pydantic validation, which simulates the world
    where ``PolicyEffect`` has been widened and layer 1 no longer rejects the
    value. Without the guard in ``_base.py`` these calls return normally and
    the guarded action executes ungoverned.
    """

    @pytest.mark.parametrize("decision", ["quarantine", "log", "", "ALLOW"])
    def test_sync_raises_on_non_allow(self, fc_client, monkeypatch, decision):
        monkeypatch.setattr(
            fc_client,
            "evaluate",
            lambda _params: EvaluateResponse.model_construct(
                decision=decision, trace_id="t-1", approval_request_id=None, reason="r", policy_rule_id=None
            ),
        )
        with pytest.raises(ActionDeniedError, match="Unexpected policy decision"):
            evaluate_governance_sync(fc_client, "op")

    @pytest.mark.parametrize("decision", ["quarantine", "log", "", "ALLOW"])
    async def test_async_raises_on_non_allow(self, fc_async_client, monkeypatch, decision):
        async def _fake(_params):
            return EvaluateResponse.model_construct(
                decision=decision, trace_id="t-1", approval_request_id=None, reason="r", policy_rule_id=None
            )

        monkeypatch.setattr(fc_async_client, "evaluate", _fake)
        with pytest.raises(ActionDeniedError, match="Unexpected policy decision"):
            await evaluate_governance_async(fc_async_client, "op")


class TestKnownDecisionsStillBehave:
    """The guard must not change the three documented outcomes."""

    def test_allow_returns(self, fc_client, fc_mock):
        fc_mock.post("/api/v1/evaluate").mock(return_value=httpx.Response(200, json=_body("allow")))
        assert evaluate_governance_sync(fc_client, "op").decision == "allow"

    def test_deny_raises(self, fc_client, fc_mock):
        fc_mock.post("/api/v1/evaluate").mock(return_value=httpx.Response(200, json=_body("deny")))
        with pytest.raises(ActionDeniedError):
            evaluate_governance_sync(fc_client, "op")

    def test_approval_required_raises(self, fc_client, fc_mock):
        fc_mock.post("/api/v1/evaluate").mock(
            return_value=httpx.Response(200, json=_body("approval_required"))
        )
        with pytest.raises(ActionDeniedError, match="Approval required"):
            evaluate_governance_sync(fc_client, "op")

    async def test_async_allow_returns(self, fc_async_client, fc_mock):
        fc_mock.post("/api/v1/evaluate").mock(return_value=httpx.Response(200, json=_body("allow")))
        result = await evaluate_governance_async(fc_async_client, "op")
        assert result.decision == "allow"
