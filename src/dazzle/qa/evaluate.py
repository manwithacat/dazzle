"""Prompt builder + response parser for the Dazzle visual QA toolkit.

The visual-QA loop captures screenshots via :mod:`dazzle.qa.capture`,
then dispatches a Claude Code Task subagent to evaluate them against the
categories in :mod:`dazzle.qa.categories`. The subagent reads each
screenshot via the standard Read tool and writes a JSON findings file.

This module provides:

- :func:`build_subagent_prompt` — multi-screen mission prompt for the
  subagent dispatch (see ``.claude/commands/improve/strategies/visual_tier2_subagent.md``).
- :func:`parse_findings` — parser for the JSON the subagent writes back.

The previous Anthropic-API-bound evaluator was removed when ``dazzle qa
visual`` was removed in favour of the CC-subagent substrate.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dazzle.qa.categories import CATEGORIES
from dazzle.qa.models import Finding

logger = logging.getLogger(__name__)


def build_subagent_prompt(
    manifest: dict[str, Any],
    findings_path: str,
    categories: list[str] | None = None,
) -> str:
    """Build a multi-screen mission prompt for a CC Task subagent.

    The subagent receives a list of screenshots (with persona / workspace
    / URL context for each), the QA category definitions, and an output
    path. It is expected to Read every screenshot, evaluate it against
    the categories, and write a JSON array of findings to *findings_path*.

    Args:
        manifest: Manifest produced by
            :func:`dazzle.qa.capture.write_manifest` — must have an
            ``"apps"`` key listing ``{app, screens: [...]}`` entries.
        findings_path: Absolute path where the subagent must write its
            findings JSON. Used both in the prompt body and as the
            artifact the dispatcher reads after the subagent completes.
        categories: Optional subset of category IDs to evaluate. If
            ``None``, all categories from
            :data:`dazzle.qa.categories.CATEGORIES` are included.

    Returns:
        A self-contained mission prompt.
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

    screen_lines: list[str] = []
    total_screens = 0
    for app_entry in manifest.get("apps", []):
        app_name = app_entry.get("app", "?")
        for screen in app_entry.get("screens", []):
            total_screens += 1
            screen_lines.append(
                f"- app=`{app_name}` persona=`{screen.get('persona')}` "
                f"workspace=`{screen.get('workspace')}` "
                f"url=`{screen.get('url')}`\n"
                f"  screenshot: `{screen.get('screenshot')}`"
            )
    screens_block = "\n".join(screen_lines)

    return f"""You are a visual UX assessor for Dazzle example apps.

Your task: evaluate {total_screens} screenshots across {len(manifest.get("apps", []))} apps against the categories below, then write findings to a JSON file.

## Screenshots to evaluate

{screens_block}

Use the Read tool on each screenshot path (Read supports PNG natively). Inspect each image and assess it against the categories.

## Evaluation categories

{categories_block}

## What to flag

Only flag genuine UX problems a human would actually notice. Skip:

- Minor pixel-level imperfections
- Subjective style preferences
- Anything that looks deliberate (e.g. empty states are fine if the copy + CTA make sense)

## Output

Write a JSON array of findings to `{findings_path}`. Each finding must have these fields, all strings:

- `app`: app identifier (e.g. `ops_dashboard`) — derived from which screenshot triggered the finding
- `category`: one of the category ids listed above
- `severity`: `"high"`, `"medium"`, or `"low"`
- `location`: short description of where on the page the issue appears (e.g. `"alerts_timeseries region header"`)
- `description`: concise description of the problem
- `suggestion`: brief, actionable suggestion to fix it

Use Write to create `{findings_path}` containing the JSON array. Return the array contents in your final message as well.

If all screenshots look genuinely good, write `[]` to the file and report that.

The findings array is the durable artifact — make it complete and self-contained.
"""


def parse_findings(raw: str) -> list[Finding]:
    """Parse a raw JSON response into a list of Finding objects.

    Strips markdown code fences if present, parses JSON, validates required
    keys, and skips malformed entries. Returns an empty list on parse failure
    rather than raising.

    The Finding dataclass itself doesn't carry an ``app`` field — the
    ingest helper (:mod:`dazzle.cli.runtime_impl.ux_cycle_impl.visual_tier2_ingest`)
    pairs each finding with the app from the source JSON before writing
    backlog rows.

    Args:
        raw: Raw JSON string (with optional markdown fences).

    Returns:
        List of Finding objects (may be empty).
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse subagent findings response as JSON")
        return []

    if not isinstance(data, list):
        logger.warning("Subagent findings response was not a JSON array")
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
