"""Basic SidClaw SDK usage — sync client."""

from sidclaw import SidClaw, ActionDeniedError

client = SidClaw(
    api_key="ai_your_key_here",
    agent_id="agent-customer-support",
)

# Evaluate an action
decision = client.evaluate({
    "operation": "send_email",
    "target_integration": "email_service",
    "resource_scope": "outbound_customer_email",
    "data_classification": "confidential",
})

print(f"Decision: {decision.decision}")
print(f"Trace ID: {decision.trace_id}")
print(f"Reason: {decision.reason}")

if decision.decision == "allow":
    # Execute the action
    print("Sending email...")
    # send_email(...)
    client.record_outcome(decision.trace_id, {"status": "success"})

elif decision.decision == "approval_required":
    print(f"Waiting for approval: {decision.approval_request_id}")
    approval = client.wait_for_approval(
        decision.approval_request_id,
        {"timeout": 60, "poll_interval": 2},
    )
    print(f"Approval status: {approval.status}")
    if approval.status == "approved":
        print("Sending email...")
        client.record_outcome(decision.trace_id, {"status": "success"})

elif decision.decision == "deny":
    print(f"Action denied: {decision.reason}")
