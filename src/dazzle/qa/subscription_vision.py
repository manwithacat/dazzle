"""Subscription-path vision scoring — no metered Anthropic/OpenAI API.

**Economic model.** Capture is local Playwright. Judgment is a host-harness
subagent (or the outer agent) that **Reads** PNGs in-session. Cognition bills
to the harness subscription (Claude Code / Grok Build / similar), never to
``anthropic.Anthropic().messages.create`` (the metered path used by
:func:`dazzle.qa.taste_panel.score_image`).

Same substrate as ``.claude/commands/improve/strategies/visual_tier2_subagent.md``
and ``scripts/hm_visual_smoke.py``. Scores are **advisory** — never a CI ship
gate (see ``docs/reference/taste.md``).

Pipeline::

    hm_visual_smoke / dazzle qa capture
         → PNG + manifest
         → build_subscription_score_prompt(...)
         → host subagent Reads PNGs, Writes scores JSON
         → parse_subscription_scores / persist under .dazzle/
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dazzle.core.taste_rubric import TASTE_DIMENSIONS, build_judge_prompt, dimensions_for_theme

logger = logging.getLogger(__name__)

__all__ = [
    "SubscriptionScore",
    "build_subscription_score_prompt",
    "parse_subscription_scores",
    "scores_from_smoke_manifest",
    "write_scores",
    "load_scores",
    "LIGHT_DIMENSION_KEYS",
]

# Light-theme dimensions only (smoke captures are light by default).
LIGHT_DIMENSION_KEYS: tuple[str, ...] = tuple(d.key for d in dimensions_for_theme("light"))


@dataclass(frozen=True)
class SubscriptionScore:
    """One image's taste scores from a subscription Read pass."""

    image_id: str
    path: str
    scores: dict[str, int]
    worst_detail: str = ""
    notes: str = ""

    def mean(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)


def build_subscription_score_prompt(
    images: list[dict[str, str]],
    *,
    scores_path: str | Path,
    theme: str = "light",
) -> str:
    """Build a host-harness mission prompt: Read PNGs → Write scores JSON.

    Parameters
    ----------
    images:
        ``[{"image_id": "...", "path": "/abs/or/rel.png", "label": "..."}]``
    scores_path:
        Where the subagent must Write the JSON scores array.
    theme:
        ``light`` or ``dark`` — selects rubric dimensions.
    """
    dims = dimensions_for_theme(theme)
    rubric = build_judge_prompt(dims)
    scores_path = str(scores_path)

    lines = [
        "You are scoring Dazzle / HaTchi-MaXchi UI screenshots for house taste.",
        "",
        "**Billing:** Read each PNG with the host Read/vision tool (subscription).",
        "Do NOT call the Anthropic/OpenAI HTTP API, `dazzle qa taste-panel`, or",
        "`dazzle qa component-vision` — those are metered.",
        "",
        "**Ship policy:** these scores are advisory only. Dual-locks + gate suite",
        "remain the only ship floor.",
        "",
        f"## Images ({len(images)})",
        "",
    ]
    for img in images:
        lines.append(
            f"- image_id=`{img['image_id']}` label=`{img.get('label', img['image_id'])}`\n"
            f"  path: `{img['path']}`"
        )
    lines.extend(
        [
            "",
            "## Rubric (score every dimension 1–10 using anchors)",
            "",
            rubric,
            "",
            "## Output",
            "",
            f"Write a JSON **array** to `{scores_path}` via the Write tool.",
            "One object per image, shape:",
            "",
            "```json",
            "[",
            "  {",
            '    "image_id": "<from list>",',
            '    "path": "<exact path from list>",',
            '    "scores": {',
        ]
    )
    for d in dims:
        lines.append(f'      "{d.key}": <1-10>,')
    lines.extend(
        [
            "    },",
            '    "worst_detail": "<one sentence>",',
            '    "notes": "<optional short note>"',
            "  }",
            "]",
            "```",
            "",
            "Respond with ONLY that array in the file (valid JSON). Also echo it in",
            "your final message. If an image cannot be read, still emit an object",
            "with empty scores and worst_detail explaining why.",
        ]
    )
    return "\n".join(lines)


def parse_subscription_scores(raw: str | list[Any] | dict[str, Any]) -> list[SubscriptionScore]:
    """Parse subagent JSON into :class:`SubscriptionScore` list."""
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("subscription_vision: invalid JSON")
            return []
    else:
        data = raw

    if isinstance(data, dict) and "scores" in data and "image_id" in data:
        data = [data]
    if not isinstance(data, list):
        return []

    out: list[SubscriptionScore] = []
    allowed = {d.key for d in TASTE_DIMENSIONS}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        image_id = str(entry.get("image_id") or entry.get("id") or "")
        path = str(entry.get("path") or "")
        raw_scores = entry.get("scores") or {}
        if not isinstance(raw_scores, dict):
            continue
        scores: dict[str, int] = {}
        for k, v in raw_scores.items():
            if k not in allowed:
                continue
            try:
                scores[str(k)] = max(1, min(10, int(v)))
            except (TypeError, ValueError):
                continue
        out.append(
            SubscriptionScore(
                image_id=image_id or path or "unknown",
                path=path,
                scores=scores,
                worst_detail=str(entry.get("worst_detail") or ""),
                notes=str(entry.get("notes") or ""),
            )
        )
    return out


def scores_from_smoke_manifest(manifest_path: Path) -> list[dict[str, str]]:
    """Build image list from ``hm_visual_smoke`` manifest.json."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    png = data.get("full_page_png") or ""
    out_dir = Path(data.get("out") or manifest_path.parent)
    if not png:
        candidate = out_dir / "full_page.png"
        png = str(candidate) if candidate.is_file() else str(manifest_path.parent / "full_page.png")
    parts = data.get("parts") or []
    label = "hm-visual-smoke: " + ", ".join(parts[:8])
    if len(parts) > 8:
        label += f" (+{len(parts) - 8})"
    return [
        {
            "image_id": "hm-visual-smoke-full",
            "path": png,
            "label": label,
        }
    ]


def write_scores(
    scores: list[SubscriptionScore],
    path: Path,
    *,
    meta: dict[str, Any] | None = None,
) -> Path:
    """Persist scores JSON (gitignored under ``.dazzle/`` by convention)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "billing": "subscription-host-read",
        "ship_gate": False,
        "scores": [
            {
                "image_id": s.image_id,
                "path": s.path,
                "scores": s.scores,
                "mean": round(s.mean(), 2),
                "worst_detail": s.worst_detail,
                "notes": s.notes,
            }
            for s in scores
        ],
    }
    if meta:
        payload["meta"] = meta
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_scores(path: Path) -> list[SubscriptionScore]:
    """Load scores written by :func:`write_scores` or a raw array."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "scores" in data:
        return parse_subscription_scores(data["scores"])
    return parse_subscription_scores(data)
