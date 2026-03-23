# Changelog

## 0.1.0 (2026-03-23)

- Initial release
- Sync and async clients (`SidClaw`, `AsyncSidClaw`)
- Policy evaluation, approval polling, outcome recording
- Framework integrations: LangChain, CrewAI, OpenAI Agents, Pydantic AI
- MCP governance proxy with CLI (`sidclaw-mcp-proxy`)
- Webhook signature verification
- Typed errors: `ActionDeniedError`, `ApprovalTimeoutError`, `ApprovalExpiredError`, `RateLimitError`
