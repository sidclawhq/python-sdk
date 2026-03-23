# sidclaw

[![PyPI version](https://img.shields.io/pypi/v/sidclaw)](https://pypi.org/project/sidclaw/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/sidclaw)](https://pypi.org/project/sidclaw/)

Python SDK for [SidClaw](https://sidclaw.com) — governance for AI agents.

Identity. Policy. Approval. Trace. Four primitives that give you control over what your AI agents can do.

## Install

```bash
pip install sidclaw
```

## Quick Start

```python
from sidclaw import SidClaw

client = SidClaw(api_key="ai_...", agent_id="your-agent-id")

# Evaluate an action against the policy engine
decision = client.evaluate({
    "operation": "send_email",
    "target_integration": "email_service",
    "resource_scope": "outbound_email",
    "data_classification": "confidential",
})

if decision.decision == "allow":
    send_email(...)
    client.record_outcome(decision.trace_id, {"status": "success"})
elif decision.decision == "approval_required":
    approval = client.wait_for_approval(decision.approval_request_id)
    if approval.status == "approved":
        send_email(...)
        client.record_outcome(decision.trace_id, {"status": "success"})
elif decision.decision == "deny":
    print(f"Denied: {decision.reason}")
```

## Governance Decorator

```python
from sidclaw import SidClaw
from sidclaw.middleware import with_governance, GovernanceConfig

client = SidClaw(api_key="ai_...", agent_id="your-agent-id")

@with_governance(client, GovernanceConfig(
    operation="send_email",
    target_integration="email_service",
    data_classification="confidential",
))
def send_email(to: str, subject: str, body: str) -> None:
    email_service.send(to=to, subject=subject, body=body)

send_email("customer@example.com", "Follow-up", "Hello...")
# allow -> executes immediately
# approval_required -> waits for human approval, then executes
# deny -> raises ActionDeniedError
```

## Async

```python
from sidclaw import AsyncSidClaw

async with AsyncSidClaw(api_key="ai_...", agent_id="...") as client:
    decision = await client.evaluate({
        "operation": "send_email",
        "target_integration": "email_service",
        "resource_scope": "outbound_email",
        "data_classification": "confidential",
    })
```

## Framework Integrations

```bash
pip install sidclaw[langchain]      # LangChain
pip install sidclaw[crewai]         # CrewAI
pip install sidclaw[openai-agents]  # OpenAI Agents SDK
pip install sidclaw[pydantic-ai]    # Pydantic AI
pip install sidclaw[mcp]            # MCP governance proxy
pip install sidclaw[all]            # Everything
```

### LangChain

```python
from sidclaw.middleware.langchain import govern_tools

governed = govern_tools(my_tools, client=client)
agent = create_react_agent(llm, governed)
```

### CrewAI

```python
from sidclaw.middleware.crewai import govern_crewai_tool

governed_tool = govern_crewai_tool(my_tool, client=client)
```

### OpenAI Agents SDK

```python
from sidclaw.middleware.openai_agents import govern_function_tool

tool, handler = govern_function_tool(tool_def, my_handler, client=async_client)
```

### MCP Governance Proxy

```python
from sidclaw.mcp import GovernanceMCPServer, GovernanceMCPServerConfig

server = GovernanceMCPServer(GovernanceMCPServerConfig(
    api_key="ai_...",
    agent_id="agent-001",
    upstream_command="npx",
    upstream_args=["-y", "@modelcontextprotocol/server-postgres", "postgresql://..."],
))
await server.start()
```

Or use the CLI:

```bash
SIDCLAW_API_KEY=ai_... SIDCLAW_AGENT_ID=agent-001 \
SIDCLAW_UPSTREAM_CMD=npx SIDCLAW_UPSTREAM_ARGS="-y,@modelcontextprotocol/server-postgres,postgresql://..." \
sidclaw-mcp-proxy
```

### Webhook Verification

```python
from sidclaw import verify_webhook_signature

is_valid = verify_webhook_signature(
    payload=request.body,
    signature=request.headers["X-Webhook-Signature"],
    secret="whsec_...",
)
```

## Error Handling

```python
from sidclaw import ActionDeniedError, ApprovalTimeoutError, RateLimitError

try:
    decision = client.evaluate(...)
except ActionDeniedError as e:
    print(f"Denied: {e.reason}, trace: {e.trace_id}")
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except ApprovalTimeoutError as e:
    print(f"Approval timed out for {e.approval_request_id}")
```

## Links

- [Documentation](https://docs.sidclaw.com)
- [TypeScript SDK](https://www.npmjs.com/package/@sidclaw/sdk)
- [Dashboard](https://app.sidclaw.com)
- [GitHub](https://github.com/sidclawhq/platform)
