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


ErrorClassification = Literal["timeout", "permission", "not_found", "runtime"]


class RecordOutcomeParams(TypedDict, total=False):
    status: Literal["success", "error"]  # required
    metadata: dict[str, Any]  # optional
    # Added 2026-04-16 — hooks + cost-attribution telemetry. All optional.
    outcome_summary: str
    error_classification: ErrorClassification
    exit_code: int
    tokens_in: int
    tokens_out: int
    tokens_cache_read: int
    model: str
    cost_estimate: float


class RecordTelemetryParams(TypedDict, total=False):
    """Late-arriving LLM telemetry attached to a trace after its outcome."""

    tokens_in: int
    tokens_out: int
    tokens_cache_read: int
    model: str
    cost_estimate: float
    outcome_summary: str


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
