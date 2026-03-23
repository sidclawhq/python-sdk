"""Async SidClaw SDK usage."""

import asyncio

from sidclaw import AsyncSidClaw


async def main():
    async with AsyncSidClaw(
        api_key="ai_your_key_here",
        agent_id="agent-customer-support",
    ) as client:
        decision = await client.evaluate({
            "operation": "read_docs",
            "target_integration": "knowledge_base",
            "resource_scope": "internal_docs",
            "data_classification": "internal",
        })

        print(f"Decision: {decision.decision}")
        print(f"Trace ID: {decision.trace_id}")

        if decision.decision == "allow":
            # Do the work...
            await client.record_outcome(decision.trace_id, {"status": "success"})


if __name__ == "__main__":
    asyncio.run(main())
