"""MCP governance proxy example."""

import asyncio
from sidclaw.mcp import GovernanceMCPServer, GovernanceMCPServerConfig

async def main():
    config = GovernanceMCPServerConfig(
        api_key="ai_your_key_here",
        agent_id="agent-001",
        upstream_command="npx",
        upstream_args=["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
    )

    server = GovernanceMCPServer(config)
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())
