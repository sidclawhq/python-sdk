from sidclaw.cost import MODEL_PRICING, estimate_cost, register_model_pricing


class TestEstimateCost:
    def test_computes_opus_4_7_cost(self):
        cost = estimate_cost(
            model="claude-opus-4-7",
            tokens_in=1_000_000,
            tokens_out=500_000,
        )
        # 1M * $15 + 0.5M * $75 = $15 + $37.5 = $52.5
        assert cost == 52.5

    def test_handles_cache_read_discount(self):
        cost = estimate_cost(
            model="claude-sonnet-4-6",
            tokens_in=1_000_000,
            tokens_out=100_000,
            tokens_cache_read=2_000_000,
        )
        # 1M * $3 + 0.1M * $15 + 2M * $0.3 = 3 + 1.5 + 0.6 = $5.1
        assert abs(cost - 5.1) < 1e-5

    def test_returns_zero_for_unknown_models(self):
        assert estimate_cost(model="unknown-model", tokens_in=1000, tokens_out=1000) == 0

    def test_register_model_pricing_overrides_table(self):
        register_model_pricing("custom-model", {"input": 10, "output": 20})
        assert MODEL_PRICING["custom-model"] == {"input": 10, "output": 20}
        cost = estimate_cost(model="custom-model", tokens_in=1_000_000, tokens_out=1_000_000)
        assert abs(cost - 30) < 1e-5
