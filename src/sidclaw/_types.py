from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel

# === Enums as Literal types (forward-compatible, OpenAI/Anthropic pattern) ===

DataClassification = Literal["public", "internal", "confidential", "restricted"]
PolicyEffect = Literal["allow", "approval_required", "deny"]
ApprovalStatus = Literal["pending", "approved", "denied", "expired"]
RiskClassification = Literal["low", "medium", "high", "critical"]
TraceOutcome = Literal["in_progress", "executed", "blocked", "denied", "completed_with_approval", "expired"]


# === Request types (TypedDict — lightweight, no runtime overhead) ===


class EvaluateParams(TypedDict, total=False):
    operation: str  # required
    target_integration: str  # required
    resource_scope: str  # required
    data_classification: DataClassification  # required
    context: dict[str, Any]  # optional


class RecordOutcomeParams(TypedDict, total=False):
    status: Literal["success", "error"]  # required
    metadata: dict[str, Any]  # optional


class ApprovalDecisionParams(TypedDict):
    approver_name: str
    decision_note: str | None


# === Response types (Pydantic models — validation, serialization) ===


class EvaluateResponse(BaseModel):
    decision: PolicyEffect
    trace_id: str
    approval_request_id: str | None = None
    reason: str
    policy_rule_id: str | None = None


class ApprovalStatusResponse(BaseModel):
    id: str
    status: ApprovalStatus
    decided_at: str | None = None
    approver_name: str | None = None
    decision_note: str | None = None


class WaitForApprovalOptions(TypedDict, total=False):
    timeout: float  # seconds, default 300
    poll_interval: float  # seconds, default 2
