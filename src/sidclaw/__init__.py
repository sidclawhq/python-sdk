"""SidClaw Python SDK — Governance for AI agents."""

from ._client import AsyncSidClaw, SidClaw
from ._constants import SDK_VERSION as __version__  # noqa: N811
from ._errors import (
    ActionDeniedError,
    APIError,
    ApprovalExpiredError,
    ApprovalTimeoutError,
    AuthenticationError,
    PlanLimitError,
    RateLimitError,
    SidClawError,
)
from ._types import (
    ApprovalStatus,
    ApprovalStatusResponse,
    DataClassification,
    EvaluateParams,
    EvaluateResponse,
    PolicyEffect,
    RecordOutcomeParams,
    RiskClassification,
    WaitForApprovalOptions,
)
from .webhooks import verify_webhook_signature

__all__ = [
    "SidClaw",
    "AsyncSidClaw",
    "EvaluateParams",
    "EvaluateResponse",
    "RecordOutcomeParams",
    "ApprovalStatusResponse",
    "WaitForApprovalOptions",
    "DataClassification",
    "PolicyEffect",
    "ApprovalStatus",
    "RiskClassification",
    "SidClawError",
    "APIError",
    "ActionDeniedError",
    "ApprovalTimeoutError",
    "ApprovalExpiredError",
    "RateLimitError",
    "AuthenticationError",
    "PlanLimitError",
    "verify_webhook_signature",
    "__version__",
]
