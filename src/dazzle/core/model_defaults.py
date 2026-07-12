"""Single source of truth for the framework's Claude model defaults (#1368).

Every LLM-calling site in the framework imports its default model from
here instead of hardcoding an ID. The pre-#1368 state — six call sites
each pinning their own ID — rotted independently until the most common
pin (``claude-sonnet-4-20250514``) was four days from API retirement.
``tests/unit/test_model_defaults_policy.py`` enforces that no other
module under ``src/dazzle/`` contains a ``claude-*`` model-ID literal.

Tier policy (mirrors the Subagent Model Policy in .claude/CLAUDE.md):

- **Judgment work** (agent missions, trial verdicts, visual evaluation,
  fitness investigation) uses the current Sonnet alias — an undated ID,
  so it tracks Anthropic's stable release of that tier.
- **Mechanical work** (fixed-signature generation like the DSL fuzzer)
  pins dated Haiku per the policy.

When Anthropic ships new tiers, this file and the pricing table below
are the only places to update.
"""

DEFAULT_JUDGMENT_MODEL = "claude-sonnet-4-6"
DEFAULT_MECHANICAL_MODEL = "claude-haiku-4-5-20251001"

# Grok Build CLI / xAI model defaults (subscription driver: grok-cli).
# Keep undated aliases where the CLI accepts them so pins track the
# current Grok tier without a dated retirement cliff.
DEFAULT_GROK_JUDGMENT_MODEL = "grok-4.5"


def default_model_for_driver(driver: str) -> str:
    """Pick the judgment-tier model ID for a resolved LLM driver.

    Subscription CLIs only accept model IDs from their own family —
    passing ``claude-sonnet-*`` to ``grok -p --model`` aborts with
    "unknown model id". Call sites that leave ``model=None`` must use
    this helper so auto / grok-cli paths do not inherit the Claude pin.
    """
    if driver == "grok-cli":
        return DEFAULT_GROK_JUDGMENT_MODEL
    return DEFAULT_JUDGMENT_MODEL


# USD per million tokens (input, output) — current Anthropic lineup,
# verified 2026-06-11. Consumers derive their own units from this; do
# not duplicate prices elsewhere.
ANTHROPIC_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}
