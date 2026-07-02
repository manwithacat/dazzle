"""#1528 — pure LLM call-cost computation (`dazzle.llm.costing`).

Cost semantics: None means "unknown", never "free". A computed Decimal
comes straight from the central pricing tables (per-MTok USD rates).
"""

from __future__ import annotations

from decimal import Decimal

from dazzle.core.model_defaults import ANTHROPIC_PRICING_PER_MTOK
from dazzle.llm.costing import compute_cost_usd


class TestComputeCostUsd:
    def test_anthropic_known_model_exact_math(self) -> None:
        # claude-sonnet-4-6: $3/MTok input, $15/MTok output.
        cost = compute_cost_usd("anthropic", "claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == Decimal("18.000000")

    def test_small_call_quantized_to_micro_dollars(self) -> None:
        cost = compute_cost_usd("anthropic", "claude-sonnet-4-6", 1000, 500)
        assert cost == Decimal("0.010500")

    def test_openai_known_model(self) -> None:
        # gpt-4-turbo: $10/MTok input, $30/MTok output.
        cost = compute_cost_usd("openai", "gpt-4-turbo", 1_000_000, 1_000_000)
        assert cost == Decimal("40.000000")

    def test_unknown_model_is_none(self) -> None:
        assert compute_cost_usd("anthropic", "claude-3-haiku-20240307", 100, 100) is None

    def test_unmetered_provider_is_none(self) -> None:
        # Subscription (claude_cli / local) and unpriced providers: unknown, not free.
        assert compute_cost_usd("claude_cli", "claude-sonnet-4-6", 100, 100) is None
        assert compute_cost_usd("local", "claude-sonnet-4-6", 100, 100) is None
        assert compute_cost_usd("google", "gemini-pro", 100, 100) is None

    def test_no_reported_usage_is_none(self) -> None:
        # (0, 0) means the provider reported nothing — unknown, not free.
        assert compute_cost_usd("anthropic", "claude-sonnet-4-6", 0, 0) is None

    def test_one_sided_usage_still_computes(self) -> None:
        cost = compute_cost_usd("anthropic", "claude-sonnet-4-6", 0, 1_000_000)
        assert cost == Decimal("15.000000")

    def test_every_priced_anthropic_model_computes(self) -> None:
        for model in ANTHROPIC_PRICING_PER_MTOK:
            assert compute_cost_usd("anthropic", model, 1000, 1000) is not None
