"""Pure LLM call-cost computation (#1528, ADR-0051 salvage).

The one capability the retired ops platform had no substitute for:
turning a call's token usage into a USD cost. This module is the single
place that mapping lives; the pricing source of truth for Anthropic
models is ``dazzle.core.model_defaults.ANTHROPIC_PRICING_PER_MTOK``.

Costs land on the governed ``AIJob`` entity (ADR-0043) via
``LLMIntentExecutor`` — there is no separate cost table.
"""

from __future__ import annotations

from decimal import Decimal

from dazzle.core.model_defaults import ANTHROPIC_PRICING_PER_MTOK

# USD per million tokens (input, output). OpenAI models the runtime can
# reach via `provider: openai`; extend as models are adopted.
OPENAI_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
}

_PROVIDER_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": ANTHROPIC_PRICING_PER_MTOK,
    "openai": OPENAI_PRICING_PER_MTOK,
}

_MTOK = Decimal(1_000_000)


def compute_cost_usd(
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
) -> Decimal | None:
    """USD cost of one call, or ``None`` when it cannot be known.

    ``None`` (rather than 0) is deliberate for every unknowable case —
    a missing price must read as "unknown", never as "free":

    - provider without metered pricing here (``claude_cli`` / ``local``
      subscription billing, ``google``, …)
    - model absent from the provider's price table
    - no usage reported (both token counts zero/negative)
    """
    pricing = _PROVIDER_PRICING.get(provider)
    if pricing is None:
        return None
    rates = pricing.get(model)
    if rates is None:
        return None
    if tokens_in <= 0 and tokens_out <= 0:
        return None
    in_rate, out_rate = rates
    cost = (
        Decimal(max(tokens_in, 0)) * Decimal(str(in_rate))
        + Decimal(max(tokens_out, 0)) * Decimal(str(out_rate))
    ) / _MTOK
    # Money-grade precision: quantize to micro-dollars, plenty for per-call
    # granularity while keeping sums exact.
    return cost.quantize(Decimal("0.000001"))
