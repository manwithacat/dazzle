"""Blind vision-judge taste panel (spec Phase 0).

Assembles a pool of screenshots — Dazzle fleet captures plus dialect
references — strips identity, and scores each image with N independent
vision-LLM judges against ``dazzle.core.taste_rubric``. Judge noise is
measured by repeat-scoring a subset; the parity margin per dimension is
``max(floor, 2 * noise_sd)`` so the gate can never be tighter than the
judges' own repeatability.
"""

from __future__ import annotations

import json
import logging
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "JudgeScore",
    "PanelImage",
    "aggregate_scores",
    "assemble_pool",
    "blind_order",
    "noise_sd",
    "parity_verdict",
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
