"""OpenAI Agents SDK governance example."""

import asyncio
from sidclaw import AsyncSidClaw

async def main():
    client = AsyncSidClaw(
        api_key="ai_your_key_here",
        agent_id="agent-assistant",
    )

    # from sidclaw.middleware.openai_agents import govern_function_tool
    # tool_def = {"type": "function", "function": {"name": "search", "description": "Search the web"}}
    # async def search_handler(args): return "results..."
    # tool, handler = govern_function_tool(tool_def, search_handler, client=client)

    print("OpenAI Agents governance example — install openai-agents to run")
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
