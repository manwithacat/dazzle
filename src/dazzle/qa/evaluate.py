"""Pluggable LLM evaluator for the Dazzle visual QA toolkit.

Default backend: Claude Vision (claude-sonnet-4-20250514).
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Protocol

from dazzle.qa.categories import CATEGORIES
from dazzle.qa.models import CapturedScreen, Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class QAEvaluator(Protocol):
    """Protocol for pluggable LLM evaluators."""

    def evaluate(
        self,
        screen: CapturedScreen,
        categories: list[str] | None = None,
    ) -> list[Finding]: ...


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_evaluation_prompt(
    screen: CapturedScreen,
    categories: list[str] | None = None,
) -> str:
    """Build an evaluation prompt for the given screen.

    Args:
        screen: The captured screen to evaluate.
        categories: Optional list of category IDs to restrict evaluation to.
                    If None, all categories are included.

    Returns:
        A prompt string ready to send to an LLM.
    """
    active_categories = (
        [c for c in CATEGORIES if c.id in categories] if categories is not None else CATEGORIES
    )

    category_lines: list[str] = []
    for cat in active_categories:
        category_lines.append(
            f"- **{cat.id}**: {cat.definition}\n"
            f"  Example: {cat.example}\n"
            f"  Default severity: {cat.severity_default}"
        )
    categories_block = "\n".join(category_lines)

    prompt = f"""You are a UX quality assessor for a web application built with the Dazzle framework.

You are reviewing a screenshot of the **{screen.workspace}** workspace, viewed by the **{screen.persona}** persona.
URL: {screen.url}

Your task is to identify genuine UX problems visible in the screenshot. Only flag things a human would actually notice — skip minor pixel-level imperfections or subjective style preferences.

## Evaluation categories

{categories_block}

## Output format

Return a JSON array of findings. Each finding must have these fields:
- category: one of the category ids listed above
- severity: "high", "medium", or "low"
- location: a short description of where on the page the issue appears
- description: a concise description of the problem you observed
- suggestion: a brief, actionable suggestion to fix it

If the page looks genuinely good, return an empty array: []

Return ONLY the JSON array — no markdown, no prose, no explanation outside the array.
"""
    return prompt


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def parse_findings(raw: str) -> list[Finding]:
    """Parse a raw LLM response into a list of Finding objects.

    Strips markdown code fences if present, parses JSON, validates required
    keys, and skips malformed entries. Returns an empty list on parse failure
    rather than raising.

    Args:
        raw: Raw string from the LLM response.

    Returns:
        List of Finding objects (may be empty).
    """
    # Strip markdown code fences
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (```json or ```)
        lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON")
        return []

    if not isinstance(data, list):
        logger.warning("LLM response was not a JSON array")
        return []

    required_keys = {"category", "severity", "location", "description", "suggestion"}
    findings: list[Finding] = []
    for entry in data:
        if not isinstance(entry, dict):
            logger.warning("Skipping non-dict entry in findings array: %r", entry)
            continue
        missing = required_keys - set(entry.keys())
        if missing:
            logger.warning("Skipping finding missing keys %s: %r", missing, entry)
            continue
        findings.append(
            Finding(
                category=str(entry["category"]),
                severity=str(entry["severity"]),
                location=str(entry["location"]),
                description=str(entry["description"]),
                suggestion=str(entry["suggestion"]),
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Screenshot helper
# ---------------------------------------------------------------------------


def _read_screenshot_b64(path: Path) -> str:
    """Read a screenshot file and return its base64-encoded content."""
    return base64.b64encode(path.read_bytes()).decode("ascii")


# ---------------------------------------------------------------------------
# Claude Vision evaluator
# ---------------------------------------------------------------------------


class ClaudeEvaluator:
    """LLM evaluator backed by Claude Vision (Anthropic Messages API).

    Args:
        client: Optional pre-constructed ``anthropic.Anthropic`` client.
                If not provided, one will be created lazily on first use.
        model: Anthropic model identifier to use for evaluation.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._client = client
        self._model = model

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "The 'anthropic' package is required to use ClaudeEvaluator. "
                "Install it with: pip install anthropic"
            ) from exc
        self._client = anthropic.Anthropic()
        return self._client

    def evaluate(
        self,
        screen: CapturedScreen,
        categories: list[str] | None = None,
    ) -> list[Finding]:
        """Evaluate a captured screen and return a list of findings.

        Args:
            screen: The captured screen to evaluate.
            categories: Optional list of category IDs to restrict evaluation to.

        Returns:
            List of Finding objects discovered in the screenshot.
        """
        prompt = build_evaluation_prompt(screen, categories=categories)
        image_b64 = _read_screenshot_b64(screen.screenshot)
        client = self._get_client()

        response = client.messages.create(
            model=self._model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                    ],
                }
            ],
        )
        raw_text: str = response.content[0].text
        return parse_findings(raw_text)
