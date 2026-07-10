"""Blind vision-judge taste panel (spec Phase 0).

Assembles a pool of screenshots — Dazzle fleet captures plus dialect
references — strips identity, and scores each image with N independent
vision-LLM judges against ``dazzle.core.taste_rubric``. Judge noise is
measured by repeat-scoring a subset; the parity margin per dimension is
``max(floor, 2 * noise_sd)`` so the gate can never be tighter than the
judges' own repeatability.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
from dazzle.core.taste_rubric import TasteDimension, build_judge_prompt, dimensions_for_theme

logger = logging.getLogger(__name__)

__all__ = [
    "JudgeScore",
    "PanelImage",
    "PanelResult",
    "TastePanelError",
    "aggregate_scores",
    "assemble_pool",
    "blind_order",
    "build_report",
    "noise_sd",
    "normalize_pool_frames",
    "parity_verdict",
    "run_panel",
    "score_image",
]


@dataclass(frozen=True)
class PanelImage:
    """One screenshot in the blind pool.

    ``label`` is for the report only — judges see nothing but pixels and an
    opaque ``image_id``.
    """

    image_id: str
    source: str  # "dazzle" | "reference"
    label: str
    path: Path
    theme: str  # "light" | "dark"


@dataclass(frozen=True)
class JudgeScore:
    """One dimension score from one judge pass over one image."""

    image_id: str
    dimension: str
    score: int
    judge: int
    repeat: int = 0


def assemble_pool(fleet_manifest: Path, references_manifest: Path) -> list[PanelImage]:
    """Merge the Dazzle fleet manifest and the references manifest into a pool.

    Missing screenshot files are skipped with a warning. ``image_id`` is an
    opaque ``img-NN`` assigned in merge order — no filename or app name leaks.
    """
    entries: list[tuple[str, str, Path, str]] = []  # (source, label, path, theme)

    fleet = json.loads(fleet_manifest.read_text(encoding="utf-8"))
    for app in fleet.get("apps", []):
        for screen in app.get("screens", []):
            entries.append(
                (
                    "dazzle",
                    f"{app['app']}/{screen['workspace']}/{screen['persona']}",
                    Path(screen["screenshot"]),
                    screen.get("theme", "light"),
                )
            )

    refs = json.loads(references_manifest.read_text(encoding="utf-8"))
    for ref in refs.get("references", []):
        entries.append(
            ("reference", ref["name"], Path(ref["screenshot"]), ref.get("theme", "light"))
        )

    pool: list[PanelImage] = []
    for source, label, path, theme in entries:
        if not path.exists():
            logger.warning("taste-panel: missing screenshot %s (%s) — skipped", path, label)
            continue
        pool.append(
            PanelImage(
                image_id=f"img-{len(pool):02d}",
                source=source,
                label=label,
                path=path,
                theme=theme,
            )
        )
    return pool


def normalize_pool_frames(
    pool: list[PanelImage], *, frame_width: int = 1440, frame_height: int = 900
) -> list[PanelImage]:
    """Crop every pool image to the judged frame (top-left anchored).

    The parity contract is "a fixed frame for every image, Dazzle and
    reference alike". Fleet captures default to full-page screenshots; a
    tall Dazzle image judged against a 900px reference frame is a fairness
    confound (below-the-fold footers/empty states drag one side only).
    Cropped copies are written beside the originals with a ``-frame``
    suffix; images already within the frame pass through untouched.
    Requires Pillow; if unavailable, images pass through with a warning.
    """
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - env-dependent
        logger.warning("taste-panel: Pillow unavailable — frame normalization skipped")
        return pool

    normalized: list[PanelImage] = []
    for p in pool:
        with Image.open(p.path) as img:
            w, h = img.size
            if w <= frame_width and h <= frame_height:
                normalized.append(p)
                continue
            cropped = img.crop((0, 0, min(w, frame_width), min(h, frame_height)))
            out = p.path.with_stem(p.path.stem + "-frame")
            cropped.save(out)
        normalized.append(
            PanelImage(
                image_id=p.image_id,
                source=p.source,
                label=p.label,
                path=out,
                theme=p.theme,
            )
        )
    return normalized


def blind_order(pool: list[PanelImage], seed: int) -> list[PanelImage]:
    """Deterministically shuffle the pool so sources interleave."""
    ordered = list(pool)
    random.Random(seed).shuffle(ordered)
    return ordered


def aggregate_scores(
    scores: list[JudgeScore], *, sources: dict[str, str]
) -> dict[str, dict[str, float]]:
    """Mean score per dimension per source: ``{dim: {"dazzle": m, "reference": m}}``.

    Every (judge, repeat) pass contributes equally; *sources* maps
    ``image_id`` → ``"dazzle" | "reference"``.
    """
    buckets: dict[str, dict[str, list[int]]] = {}
    for s in scores:
        source = sources[s.image_id]
        buckets.setdefault(s.dimension, {}).setdefault(source, []).append(s.score)
    return {
        dim: {source: statistics.fmean(vals) for source, vals in by_source.items()}
        for dim, by_source in buckets.items()
    }


def noise_sd(scores: list[JudgeScore]) -> dict[str, float]:
    """Pooled per-dimension sample-SD across repeat passes of the same image.

    Only (image, dimension) groups with >= 2 observations contribute.
    Pooling: sqrt(mean of per-image variances).
    """
    groups: dict[tuple[str, str], list[int]] = {}
    for s in scores:
        groups.setdefault((s.image_id, s.dimension), []).append(s.score)

    variances: dict[str, list[float]] = {}
    for (_, dim), vals in groups.items():
        if len(vals) >= 2:
            variances.setdefault(dim, []).append(statistics.variance(vals))

    return {dim: statistics.fmean(vs) ** 0.5 for dim, vs in variances.items()}


def parity_verdict(
    means: dict[str, dict[str, float]],
    noise: dict[str, float],
    *,
    floor: float = 0.5,
) -> dict[str, dict[str, float | bool]]:
    """Per-dimension parity: dazzle_mean >= reference_mean - margin.

    ``margin = max(floor, 2 * noise_sd)`` — the gate can never be tighter
    than judge repeatability (spec: "otherwise the gate is theater").
    """
    verdict: dict[str, dict[str, float | bool]] = {}
    for dim, by_source in means.items():
        dazzle = by_source.get("dazzle")
        reference = by_source.get("reference")
        if dazzle is None or reference is None:
            continue
        margin = max(floor, 2.0 * noise.get(dim, 0.0))
        verdict[dim] = {
            "dazzle": round(dazzle, 2),
            "reference": round(reference, 2),
            "margin": round(margin, 2),
            "gap": round(reference - dazzle, 2),
            "parity": dazzle >= reference - margin,
        }
    return verdict


# ── Judge runner ─────────────────────────────────────────────────────


class TastePanelError(RuntimeError):
    """A judge returned unusable output after retries."""


@dataclass
class PanelResult:
    """Full output of one panel run."""

    scores: list[JudgeScore]
    means: dict[str, dict[str, float]]
    noise: dict[str, float]
    verdict: dict[str, dict[str, float | bool]]
    pool: list[PanelImage]


def _make_client() -> Any:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - env-dependent
        raise TastePanelError(
            "anthropic package required for the taste panel. Install with: pip install anthropic"
        ) from e
    return anthropic.Anthropic()


def score_image(
    image: PanelImage,
    *,
    judge: int,
    repeat: int = 0,
    model: str = DEFAULT_JUDGMENT_MODEL,
    client: Any | None = None,
    dimensions: Sequence[TasteDimension] | None = None,
) -> list[JudgeScore]:
    """Score one image across its applicable dimensions with one judge pass.

    Sends ONLY pixels + rubric — no filename, label, or source hint (the
    blindness contract). Retries JSON parsing twice, then raises.

    ``dimensions`` overrides the rubric (e.g. SITESPEC_VISION_DIMENSIONS for
    property-vision, #1567); ``None`` keeps the taste rubric for the panel.
    """
    if client is None:
        client = _make_client()

    dims = list(dimensions) if dimensions is not None else dimensions_for_theme(image.theme)
    prompt = build_judge_prompt(dims)
    b64 = base64.standard_b64encode(image.path.read_bytes()).decode("ascii")

    last_error = "no attempts"
    for attempt in range(3):
        message = client.messages.create(
            model=model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text = "".join(getattr(block, "text", "") for block in message.content)
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            payload = json.loads(text[start:end])
            raw_scores = payload["scores"]
            return [
                JudgeScore(
                    image_id=image.image_id,
                    dimension=d.key,
                    score=max(1, min(10, int(raw_scores[d.key]))),
                    judge=judge,
                    repeat=repeat,
                )
                for d in dims
            ]
        except (ValueError, KeyError, TypeError) as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning(
                "taste-panel: unparseable judge response for %s (attempt %d): %s",
                image.image_id,
                attempt + 1,
                last_error,
            )
    raise TastePanelError(
        f"Judge {judge} returned unusable output for {image.image_id}: {last_error}"
    )


def run_panel(
    pool: list[PanelImage],
    *,
    judges: int = 3,
    noise_runs: int = 2,
    noise_subset: int = 4,
    seed: int = 7,
    model: str = DEFAULT_JUDGMENT_MODEL,
    client: Any | None = None,
) -> PanelResult:
    """Run the full blind panel: base passes, noise repeats, aggregate, verdict.

    Base: every image scored once per judge (order re-blinded per judge).
    Noise: the first *noise_subset* images of the seed order are re-scored
    *noise_runs* more times by judge 0; the noise SD pools ONLY judge-0
    passes of that subset so inter-judge disagreement doesn't inflate the
    repeatability estimate. Means exclude repeat passes so the noise subset
    doesn't get extra weight.
    """
    if client is None:
        client = _make_client()

    all_scores: list[JudgeScore] = []
    for judge in range(judges):
        for image in blind_order(pool, seed=seed + judge):
            all_scores.extend(score_image(image, judge=judge, model=model, client=client))

    subset = blind_order(pool, seed=seed)[:noise_subset]
    for repeat in range(1, noise_runs + 1):
        for image in subset:
            all_scores.extend(
                score_image(image, judge=0, repeat=repeat, model=model, client=client)
            )

    sources = {p.image_id: p.source for p in pool}
    subset_ids = {p.image_id for p in subset}
    noise_scores = [s for s in all_scores if s.image_id in subset_ids and s.judge == 0]
    means = aggregate_scores([s for s in all_scores if s.repeat == 0], sources=sources)
    noise = noise_sd(noise_scores)
    verdict = parity_verdict(means, noise)
    return PanelResult(scores=all_scores, means=means, noise=noise, verdict=verdict, pool=pool)


# ── Report ───────────────────────────────────────────────────────────


def build_report(result: PanelResult) -> tuple[dict[str, Any], str]:
    """Build the (json_dict, markdown) pair for a panel run."""
    overall = bool(result.verdict) and all(v["parity"] for v in result.verdict.values())
    counts = {
        "dazzle": sum(1 for p in result.pool if p.source == "dazzle"),
        "reference": sum(1 for p in result.pool if p.source == "reference"),
    }
    data: dict[str, Any] = {
        "parity": overall,
        "counts": counts,
        "means": result.means,
        "noise_sd": result.noise,
        "verdict": result.verdict,
        "pool": [
            {
                "image_id": p.image_id,
                "source": p.source,
                "label": p.label,
                "theme": p.theme,
                "path": str(p.path),
            }
            for p in result.pool
        ],
        "scores": [
            {
                "image_id": s.image_id,
                "dimension": s.dimension,
                "score": s.score,
                "judge": s.judge,
                "repeat": s.repeat,
            }
            for s in result.scores
        ],
    }

    lines = [
        "# Taste Panel",
        "",
        f"**Overall parity: {'PASS' if overall else 'FAIL'}** "
        f"({counts['dazzle']} dazzle screens vs {counts['reference']} references)",
        "",
        "| Dimension | Dazzle | Reference | Gap | Margin | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for dim, v in sorted(result.verdict.items()):
        lines.append(
            f"| {dim} | {v['dazzle']} | {v['reference']} | {v['gap']} "
            f"| {v['margin']} | {'PASS' if v['parity'] else 'FAIL'} |"
        )
    lines += [
        "",
        "Margin = max(0.5, 2 × judge noise SD) per dimension. "
        "Parity = dazzle mean ≥ reference mean − margin.",
        "",
    ]
    return data, "\n".join(lines)
