"""Per-1M-token pricing for common LLM models.

Keep this table up to date — stale pricing produces bad cost estimates.
Prices are in USD per 1,000,000 tokens.

Used by :func:`estimate_cost` and consumed by the Claude Code Stop hook.
"""

from __future__ import annotations

from typing import TypedDict


class ModelPricing(TypedDict, total=False):
    input: float  # required
    output: float  # required
    cache_read: float
    cache_write: float


MODEL_PRICING: dict[str, ModelPricing] = {
    # Anthropic Claude 4.x
    "claude-opus-4-7": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    "claude-haiku-4-5": {"input": 0.8, "output": 4.0, "cache_read": 0.08},
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0, "cache_read": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "cache_read": 0.075},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "o1-preview": {"input": 15.0, "output": 60.0},
    "o1-mini": {"input": 3.0, "output": 12.0},
    # Google Gemini
    "gemini-2.0-flash": {"input": 0.1, "output": 0.4},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.3},
}


def estimate_cost(
    model: str,
    tokens_in: int,
    tokens_out: int,
    tokens_cache_read: int = 0,
    tokens_cache_write: int = 0,
) -> float:
    """Compute a USD cost estimate for a model call.

    Returns 0 if the model is not in the pricing table — prefer emitting 0
    over a wildly wrong estimate.
    """
    pricing = MODEL_PRICING.get(model) or MODEL_PRICING.get(model.lower())
    if not pricing:
        return 0.0

    input_price = pricing.get("input", 0.0)
    output_price = pricing.get("output", 0.0)
    cache_read_price = pricing.get("cache_read", 0.0)
    cache_write_price = pricing.get("cache_write", input_price)

    cost = (
        tokens_in * input_price
        + tokens_out * output_price
        + tokens_cache_read * cache_read_price
        + tokens_cache_write * cache_write_price
    )

    return cost / 1_000_000


def register_model_pricing(model: str, pricing: ModelPricing) -> None:
    """Register or override pricing for a model — useful for fine-tuned variants
    or self-hosted models where you know the unit cost.
    """
    MODEL_PRICING[model] = pricing


__all__ = ["MODEL_PRICING", "ModelPricing", "estimate_cost", "register_model_pricing"]
