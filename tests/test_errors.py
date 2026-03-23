from sidclaw._errors import (
    APIError,
    ActionDeniedError,
    ApprovalExpiredError,
    ApprovalTimeoutError,
    AuthenticationError,
    PlanLimitError,
    RateLimitError,
    SidClawError,
)


def test_error_hierarchy():
    assert issubclass(APIError, SidClawError)
    assert issubclass(ActionDeniedError, APIError)
    assert issubclass(AuthenticationError, APIError)
    assert issubclass(RateLimitError, APIError)
    assert issubclass(PlanLimitError, APIError)
    assert issubclass(ApprovalExpiredError, APIError)
    assert issubclass(ApprovalTimeoutError, SidClawError)
    assert not issubclass(ApprovalTimeoutError, APIError)


def test_action_denied_attributes():
    err = ActionDeniedError("not allowed", trace_id="t-1", policy_rule_id="r-1")
    assert err.reason == "not allowed"
    assert err.trace_id == "t-1"
    assert err.policy_rule_id == "r-1"
    assert err.status_code == 403
    assert err.code == "action_denied"
    assert "not allowed" in str(err)


def test_rate_limit_retry_after():
    err = RateLimitError("too fast", retry_after=30.0)
    assert err.retry_after == 30.0
    assert err.status_code == 429


def test_approval_timeout_attributes():
    err = ApprovalTimeoutError("a-1", "t-1", 300)
    assert err.approval_request_id == "a-1"
    assert err.trace_id == "t-1"
    assert err.timeout == 300
    assert "300" in str(err)


def test_plan_limit_attributes():
    err = PlanLimitError("agents", 5, 5)
    assert err.limit_name == "agents"
    assert err.current == 5
    assert err.max == 5
    assert err.status_code == 402
