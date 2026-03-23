from __future__ import annotations


class SidClawError(Exception):
    """Base exception for all SidClaw SDK errors."""


class APIError(SidClawError):
    """Base for HTTP API errors."""

    def __init__(self, message: str, *, status_code: int, code: str, request_id: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id


class ActionDeniedError(APIError):
    """The action was denied by a policy rule."""

    def __init__(
        self, reason: str, *, trace_id: str, policy_rule_id: str | None = None, request_id: str | None = None
    ) -> None:
        super().__init__(f"Action denied: {reason}", status_code=403, code="action_denied", request_id=request_id)
        self.reason = reason
        self.trace_id = trace_id
        self.policy_rule_id = policy_rule_id


class ApprovalTimeoutError(SidClawError):
    """Timed out waiting for approval."""

    def __init__(self, approval_request_id: str, trace_id: str, timeout: float) -> None:
        super().__init__(f"Approval timed out after {timeout}s")
        self.approval_request_id = approval_request_id
        self.trace_id = trace_id
        self.timeout = timeout


class ApprovalExpiredError(APIError):
    """The approval request expired on the server."""

    def __init__(self, approval_request_id: str, trace_id: str) -> None:
        super().__init__("Approval request expired", status_code=410, code="approval_expired")
        self.approval_request_id = approval_request_id
        self.trace_id = trace_id


class RateLimitError(APIError):
    """Rate limit exceeded."""

    def __init__(self, message: str, *, retry_after: float, request_id: str | None = None) -> None:
        super().__init__(message, status_code=429, code="rate_limit_exceeded", request_id=request_id)
        self.retry_after = retry_after


class AuthenticationError(APIError):
    """Invalid or missing API key."""

    def __init__(self, message: str = "Authentication required", *, request_id: str | None = None) -> None:
        super().__init__(message, status_code=401, code="unauthorized", request_id=request_id)


class PlanLimitError(APIError):
    """Plan limit reached."""

    def __init__(self, limit_name: str, current: int, max_val: int, *, request_id: str | None = None) -> None:
        super().__init__(
            f"Plan limit reached: {limit_name} ({current}/{max_val})",
            status_code=402,
            code="plan_limit_reached",
            request_id=request_id,
        )
        self.limit_name = limit_name
        self.current = current
        self.max = max_val
