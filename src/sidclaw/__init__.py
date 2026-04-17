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
    ErrorClassification,
    EvaluateParams,
    EvaluateResponse,
    PolicyEffect,
    RecordOutcomeParams,
    RecordTelemetryParams,
    RiskClassification,
    WaitForApprovalOptions,
)
from .cost import MODEL_PRICING, ModelPricing, estimate_cost, register_model_pricing
from .webhooks import verify_webhook_signature

__all__ = [
    "SidClaw",
    "AsyncSidClaw",
    "EvaluateParams",
    "EvaluateResponse",
    "RecordOutcomeParams",
    "RecordTelemetryParams",
    "ApprovalStatusResponse",
    "WaitForApprovalOptions",
    "DataClassification",
    "PolicyEffect",
    "ApprovalStatus",
    "RiskClassification",
    "ErrorClassification",
    "SidClawError",
    "APIError",
    "ActionDeniedError",
    "ApprovalTimeoutError",
    "ApprovalExpiredError",
    "RateLimitError",
    "AuthenticationError",
    "PlanLimitError",
    "verify_webhook_signature",
    "MODEL_PRICING",
    "ModelPricing",
    "estimate_cost",
    "register_model_pricing",
    "__version__",
]
