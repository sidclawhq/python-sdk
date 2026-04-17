# Changelog

## 0.2.0 (2026-04-17)

Telemetry + cost attribution parity with `@sidclaw/sdk@0.1.11`.

Added:
- `record_telemetry(trace_id, params)` method on `SidClaw` and `AsyncSidClaw` — PATCH `/api/v1/traces/:id/telemetry`. Token usage and cost are accumulated server-side; outcome_summary and model are set-once (first write wins).
- `RecordTelemetryParams` TypedDict with `tokens_in`, `tokens_out`, `tokens_cache_read`, `model`, `cost_estimate`, `outcome_summary` (all optional).
- Extended `RecordOutcomeParams` with eight optional fields: `outcome_summary`, `error_classification`, `exit_code`, `tokens_in`, `tokens_out`, `tokens_cache_read`, `model`, `cost_estimate`.
- `ErrorClassification` literal type: `'timeout' | 'permission' | 'not_found' | 'runtime'`.
- New module `sidclaw.cost` — `MODEL_PRICING` table for 13 models (Claude 4.x, GPT-4o, Gemini), `estimate_cost(model, tokens_in, tokens_out, tokens_cache_read)`, `register_model_pricing(model, pricing)` for user overrides.

No breaking changes — all new fields are optional.

## 0.1.0 (2026-03-23)

- Initial release
- Sync and async clients (`SidClaw`, `AsyncSidClaw`)
- Policy evaluation, approval polling, outcome recording
- Framework integrations: LangChain, CrewAI, OpenAI Agents, Pydantic AI
- MCP governance proxy with CLI (`sidclaw-mcp-proxy`)
- Webhook signature verification
- Typed errors: `ActionDeniedError`, `ApprovalTimeoutError`, `ApprovalExpiredError`, `RateLimitError`
