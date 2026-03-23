from sidclaw._types import ApprovalStatusResponse, EvaluateResponse


def test_evaluate_response_validation():
    data = {
        "decision": "allow",
        "trace_id": "trace-123",
        "approval_request_id": None,
        "reason": "Policy matched",
        "policy_rule_id": "rule-1",
    }
    resp = EvaluateResponse.model_validate(data)
    assert resp.decision == "allow"
    assert resp.trace_id == "trace-123"
    assert resp.policy_rule_id == "rule-1"


def test_evaluate_response_approval_required():
    data = {
        "decision": "approval_required",
        "trace_id": "trace-456",
        "approval_request_id": "approval-1",
        "reason": "Needs review",
        "policy_rule_id": "rule-2",
    }
    resp = EvaluateResponse.model_validate(data)
    assert resp.decision == "approval_required"
    assert resp.approval_request_id == "approval-1"


def test_approval_status_response():
    data = {
        "id": "a-1",
        "status": "approved",
        "decided_at": "2026-01-01T00:00:00Z",
        "approver_name": "Admin",
        "decision_note": "ok",
    }
    resp = ApprovalStatusResponse.model_validate(data)
    assert resp.status == "approved"
    assert resp.approver_name == "Admin"


def test_evaluate_response_minimal():
    data = {
        "decision": "deny",
        "trace_id": "t",
        "reason": "denied",
    }
    resp = EvaluateResponse.model_validate(data)
    assert resp.approval_request_id is None
    assert resp.policy_rule_id is None
