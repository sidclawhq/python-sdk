"""MCP governance proxy server.

Wraps any upstream MCP server with SidClaw policy evaluation.
Every tool call is evaluated before forwarding to the upstream server.

Usage:
    from sidclaw.mcp import GovernanceMCPServer, GovernanceMCPServerConfig

    server = GovernanceMCPServer(GovernanceMCPServerConfig(
        api_key="ai_...",
        agent_id="agent-001",
        upstream_command="npx",
        upstream_args=["-y", "@modelcontextprotocol/server-postgres", "postgresql://..."],
    ))
    await server.start()
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from typing import Any

from .._client import AsyncSidClaw
from .._types import EvaluateParams
from .config import GovernanceMCPServerConfig
from .interceptor import derive_resource_scope, find_mapping

logger = logging.getLogger("sidclaw.mcp")

try:
    try:
        from mcp.client.session import ClientSession
    except ImportError:
        from mcp.client import ClientSession  # Fallback for older MCP SDK versions
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, TextContent
except ImportError as e:
    raise ImportError("Install MCP SDK: pip install sidclaw[mcp]") from e


class GovernanceMCPServer:
    """MCP governance proxy that wraps an upstream MCP server."""

    def __init__(self, config: GovernanceMCPServerConfig) -> None:
        self.config = config
        self.sidclaw = AsyncSidClaw(
            api_key=config.api_key,
            base_url=config.api_url,
            agent_id=config.agent_id,
            max_retries=2,
        )
        self.server = Server("sidclaw-governance")
        self._upstream: ClientSession | None = None
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> list[Any]:
            if self._upstream:
                result = await self._upstream.list_tools()
                return result.tools
            return []

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
            args = arguments or {}
            mapping = find_mapping(name, self.config.tool_mappings)

            # Skip governance if configured
            if mapping and mapping.skip_governance:
                if self._upstream:
                    return await self._upstream.call_tool(name, args)
                return CallToolResult(content=[TextContent(type="text", text="No upstream server")])

            # Evaluate against SidClaw
            operation = mapping.operation if mapping and mapping.operation else name
            integration = (
                mapping.target_integration
                if mapping and mapping.target_integration
                else self.config.upstream_command or "upstream"
            )
            scope = (
                mapping.resource_scope
                if mapping and mapping.resource_scope
                else derive_resource_scope(name, args)
            )
            classification = (
                mapping.data_classification
                if mapping and mapping.data_classification
                else self.config.default_data_classification
            )

            try:
                decision = await self.sidclaw.evaluate(
                    EvaluateParams(
                        operation=operation,
                        target_integration=integration,
                        resource_scope=scope,
                        data_classification=classification,
                        context={"mcp_tool": name, "mcp_args": args},
                    )
                )
            except Exception as e:
                logger.error("Governance evaluation failed: %s", e)
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Governance error: {e}")],
                    isError=True,
                )

            if decision.decision == "deny":
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Action denied by policy: {decision.reason}")],
                    isError=True,
                )

            if decision.decision == "approval_required":
                if self.config.approval_wait_mode == "block":
                    try:
                        approval = await self.sidclaw.wait_for_approval(
                            decision.approval_request_id or "",
                            {"timeout": self.config.approval_block_timeout, "poll_interval": 1},
                        )
                        if approval.status == "approved":
                            pass  # Fall through to forward
                        else:
                            return CallToolResult(
                                content=[
                                    TextContent(
                                        type="text",
                                        text=f"Approval {approval.status}: {approval.decision_note or 'No reason'}",
                                    )
                                ],
                                isError=True,
                            )
                    except Exception:
                        return CallToolResult(
                            content=[
                                TextContent(
                                    type="text",
                                    text=(
                                        f"Approval required but timed out: {decision.reason}\n"
                                        f"Approval ID: {decision.approval_request_id}\n"
                                        f"Trace ID: {decision.trace_id}"
                                    ),
                                )
                            ],
                            isError=True,
                        )
                else:
                    return CallToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text=(
                                    f"Approval required: {decision.reason}\n"
                                    f"Approval ID: {decision.approval_request_id}\n"
                                    f"Trace ID: {decision.trace_id}\n"
                                    f"Check the SidClaw dashboard to approve or deny."
                                ),
                            )
                        ],
                        isError=True,
                    )

            # Allowed — forward to upstream
            if self._upstream:
                try:
                    result = await self._upstream.call_tool(name, args)
                    with contextlib.suppress(Exception):
                        await self.sidclaw.record_outcome(decision.trace_id, {"status": "success"})
                    return result
                except Exception as e:
                    with contextlib.suppress(Exception):
                        await self.sidclaw.record_outcome(
                            decision.trace_id, {"status": "error", "metadata": {"error": str(e)}}
                        )
                    raise

            return CallToolResult(content=[TextContent(type="text", text="No upstream server configured")])

    async def start(self) -> None:
        """Start the governance proxy."""
        logger.info("SidClaw governance proxy starting")
        logger.info("Agent: %s", self.config.agent_id)
        logger.info(
            "Upstream: %s %s",
            self.config.upstream_command,
            " ".join(self.config.upstream_args),
        )
        logger.info("API: %s", self.config.api_url)

        upstream_params = StdioServerParameters(
            command=self.config.upstream_command or "",
            args=self.config.upstream_args,
            env=self.config.upstream_env,
        )

        async with stdio_client(upstream_params) as (read, write), ClientSession(read, write) as session:
            self._upstream = session
            await session.initialize()

            async with stdio_server() as (server_read, server_write):
                await self.server.run(server_read, server_write, self.server.create_initialization_options())


def cli_main() -> None:
    """CLI entry point for `sidclaw-mcp-proxy` command."""
    import os

    api_key = os.environ.get("SIDCLAW_API_KEY")
    agent_id = os.environ.get("SIDCLAW_AGENT_ID")
    upstream_cmd = os.environ.get("SIDCLAW_UPSTREAM_CMD")
    upstream_args_raw = os.environ.get("SIDCLAW_UPSTREAM_ARGS", "")

    if not api_key:
        print("Error: SIDCLAW_API_KEY is required", file=sys.stderr)
        sys.exit(1)
    if not agent_id:
        print("Error: SIDCLAW_AGENT_ID is required", file=sys.stderr)
        sys.exit(1)
    if not upstream_cmd:
        print("Error: SIDCLAW_UPSTREAM_CMD is required", file=sys.stderr)
        sys.exit(1)

    config = GovernanceMCPServerConfig(
        api_key=api_key,
        api_url=os.environ.get("SIDCLAW_API_URL", "https://api.sidclaw.com"),
        agent_id=agent_id,
        upstream_command=upstream_cmd,
        upstream_args=upstream_args_raw.split(",") if upstream_args_raw else [],
        default_data_classification=os.environ.get("SIDCLAW_DEFAULT_CLASSIFICATION", "internal"),  # type: ignore[arg-type]
    )

    server = GovernanceMCPServer(config)
    asyncio.run(server.start())
