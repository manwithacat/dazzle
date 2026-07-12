"""Fallback verdict synthesizer for ``dazzle qa trial``.

Trials 1-3 all hit ``max_steps`` before the LLM called
``submit_verdict``. The verdict is the most important output of a
trial — without it the report has no headline takeaway — so we
guarantee one via a single follow-up LLM call that reads the
friction observations and writes a 1-paragraph verdict in Sarah's
voice.

This is a cheap, constant-cost fallback (~2-3k tokens). Invoked
only when ``transcript_sink["verdict"]`` is empty at trial end.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL

logger = logging.getLogger(__name__)
_FALLBACK_SYSTEM_PROMPT = """\
You are writing the closing verdict for a software trial. The trial
subject — a real business user — ran out of time before writing their
own verdict, so you're closing the gap from their recorded
observations.

Read their friction notes below and write a ONE-PARAGRAPH verdict in
their voice (first-person, business-owner-trialling-software tone, not
QA-engineer tone). The verdict should:

- Name the one or two most important things that stood out (good OR bad).
- End with a concrete recommendation: switch, don't switch, or "not yet
  but I'd look again in 3 months."
- Be honest and balanced. If the friction is all bugs, say so. If the
  friction is mild and the core value prop is clear, say that too.

Do NOT invent findings that aren't in the notes. If there's very little
to go on, say so briefly.

--- User identity ---
{user_identity}

--- Business context ---
{business_context}

--- Friction recorded ---
{friction_summary}
"""


def _format_friction_for_synthesis(friction: list[dict[str, Any]]) -> str:
    if not friction:
        return "(no friction recorded)"
    lines = []
    for i, f in enumerate(friction, start=1):
        cat = f.get("category", "other")
        sev = f.get("severity", "medium")
        desc = f.get("description", "").strip()
        url = f.get("url", "").strip()
        meta = f"[{cat}/{sev}]"
        if url:
            meta += f" @ {url}"
        lines.append(f"{i}. {meta}\n   {desc}")
    return "\n".join(lines)


def synthesize_verdict(
    *,
    user_identity: str,
    business_context: str,
    friction: list[dict[str, Any]],
    model: str | None = None,
    api_key: str | None = None,
    llm_driver: str,
) -> str:
    """Call the LLM once to write a verdict from the friction record.

    ``llm_driver`` is required (no default) — the verdict call must bill
    the same way the trial itself did, so callers pass the driver they
    resolved, never an assumption.

    Returns the verdict text, or an empty string if the LLM call
    fails for any reason (we'd rather have an empty verdict and a
    good report than crash at the end of a 3-minute trial).
    """
    prompt = _FALLBACK_SYSTEM_PROMPT.format(
        user_identity=user_identity.strip() or "(not specified)",
        business_context=business_context.strip() or "(not specified)",
        friction_summary=_format_friction_for_synthesis(friction),
    )
    user_msg = "Write the verdict now. One paragraph, in character."

    from dazzle.llm.driver import is_subscription_driver

    if is_subscription_driver(llm_driver):
        try:
            from dazzle.core.model_defaults import default_model_for_driver
            from dazzle.llm.driver import call_subscription_cli

            text, _tokens = call_subscription_cli(
                llm_driver,
                user_msg,
                system_prompt=prompt,
                model=model or default_model_for_driver(llm_driver),
            )
            return text.strip()
        except Exception:
            logger.debug("ignored exception in verdict fallback (%s)", llm_driver, exc_info=True)
            return ""

    try:
        import anthropic
    except ImportError:
        return ""

    try:
        client_kwargs: dict[str, Any] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        elif os.environ.get("ANTHROPIC_API_KEY"):
            # Let the SDK pick up the env var — explicit None would fail.
            pass
        client = anthropic.Anthropic(**client_kwargs)
        resp = client.messages.create(
            model=model or DEFAULT_JUDGMENT_MODEL,
            max_tokens=512,
            system=prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        # Extract text from the first content block
        for block in resp.content:
            text_attr = getattr(block, "text", None)
            if isinstance(text_attr, str) and text_attr.strip():
                return text_attr.strip()
        return ""
    except Exception:
        # Never let the fallback crash the trial report. Empty
        # verdict → tombstone in the report, which is still useful.
        logger.debug("ignored exception in trial_verdict_fallback.py:115", exc_info=True)
        return ""
