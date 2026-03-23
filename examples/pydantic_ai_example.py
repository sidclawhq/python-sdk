"""Pydantic AI integration example.

Demonstrates using SidClaw governance within Pydantic AI tool functions
via the governance_dependency helper.

Usage:
    pip install sidclaw[pydantic-ai] pydantic-ai
    export SIDCLAW_API_KEY=ai_...
    export SIDCLAW_AGENT_ID=your-agent-id
    export OPENAI_API_KEY=sk-...
    python pydantic_ai_example.py
"""

import os

from pydantic_ai import Agent, RunContext

from sidclaw import ActionDeniedError, AsyncSidClaw
from sidclaw.middleware.pydantic_ai import governance_dependency


# --- SidClaw client ---

client = AsyncSidClaw(
    api_key=os.environ["SIDCLAW_API_KEY"],
    agent_id=os.environ["SIDCLAW_AGENT_ID"],
)


# --- Dependencies ---

class Deps:
    sidclaw_client: AsyncSidClaw = client


# --- Agent ---

agent = Agent("openai:gpt-4", deps_type=Deps)


@agent.tool
async def lookup_customer(ctx: RunContext[Deps], email: str) -> str:
    """Look up a customer by email address."""
    gov = governance_dependency(ctx.deps.sidclaw_client)
    decision = await gov.check(
        "lookup_customer",
        target_integration="crm",
        data_classification="confidential",
    )

    try:
        # Your CRM lookup logic here
        result = f"Customer found: {email} (Enterprise plan)"
        await gov.record_success(decision.trace_id)
        return result
    except Exception as e:
        await gov.record_error(decision.trace_id, e)
        raise


@agent.tool
async def send_email(ctx: RunContext[Deps], to: str, subject: str, body: str) -> str:
    """Send an email to a customer."""
    gov = governance_dependency(ctx.deps.sidclaw_client)

    try:
        decision = await gov.check(
            "send_email",
            target_integration="email_service",
            data_classification="confidential",
        )
    except ActionDeniedError as e:
        return f"Email blocked by policy: {e.reason}"

    try:
        # Your email sending logic here
        result = f"Email sent to {to}: {subject}"
        await gov.record_success(decision.trace_id)
        return result
    except Exception as e:
        await gov.record_error(decision.trace_id, e)
        raise


@agent.tool
async def export_data(ctx: RunContext[Deps], query: str) -> str:
    """Export customer data (blocked by policy)."""
    gov = governance_dependency(ctx.deps.sidclaw_client)

    try:
        decision = await gov.check(
            "export_data",
            target_integration="crm",
            data_classification="restricted",
        )
    except ActionDeniedError as e:
        return f"Data export blocked: {e.reason}"

    # This won't be reached if policy denies
    return "Export complete"


# --- Run ---

async def main():
    result = await agent.run(
        "Look up the customer john@example.com and send them a follow-up email",
        deps=Deps(),
    )
    print(result.data)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
