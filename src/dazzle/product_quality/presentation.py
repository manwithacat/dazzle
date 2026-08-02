"""Presentation residual — ref_as_repr / person_as_text on hero stills (#1626 T2).

Machine floors (byte size, seed hits) miss buyer-chrome defects like:

  Device: {'id': UUID('d1000000-…')}

When local stills exist and ``tesseract`` is on PATH, OCR residual patterns.
Absent stills or missing OCR → skip (same posture as empty-hero floors in CI).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dazzle.product_quality.stills import HERO_MIN_BYTES, _shot_dir

# Buyer-chrome leaks: Python dict/UUID repr in still OCR text.
_REF_AS_REPR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"UUID\s*\(", re.IGNORECASE),
    re.compile(r"\{\s*['\"]id['\"]\s*:"),
    re.compile(r"dict_values\s*\(", re.IGNORECASE),
)

# #1626 F1 / S2 — metric delta seed-noise theater on hero stills.
_DELTA_THEATER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\(\s*\d{3,}(?:\.\d+)?\s*%\s*\)"),  # (150.0%) / (200%)
    re.compile(r"%\s*\)\s*vs", re.IGNORECASE),  # glued %)vs prior
)

# Queue pilot: person should be Avatar, not "Assigned To: Name" prose.
# Only checked on stills listed in PERSON_AS_TEXT_STILLS.
_PERSON_AS_TEXT_PATTERN = re.compile(r"Assigned\s+To\s*:", re.IGNORECASE)

PERSON_AS_TEXT_STILLS: frozenset[str] = frozenset(
    {
        "ticket_queue_agent_desktop_light.png",
    }
)


@dataclass
class PresentationScore:
    name: str
    path: str | None
    residual: bool
    kind: str  # ref_as_repr | person_as_text | ocr_skip | ok
    reason: str
    snippet: str = ""


def _ocr_png(path: Path, *, timeout: float = 90.0) -> str | None:
    """Return tesseract stdout text, or None if OCR unavailable/failed."""
    if not shutil.which("tesseract"):
        return None
    try:
        proc = subprocess.run(
            ["tesseract", str(path), "stdout"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout or ""


def _find_ref_as_repr(text: str) -> str | None:
    for pat in _REF_AS_REPR_PATTERNS:
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 60)
            return " ".join(text[start:end].split())
    return None


def _find_delta_theater(text: str) -> str | None:
    """Detect absurd metric % or glued %)vs on hero still OCR (#1626 F1)."""
    for pat in _DELTA_THEATER_PATTERNS:
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 40)
            return " ".join(text[start:end].split())
    return None


def score_presentation(app_dir: Path, app_name: str) -> list[PresentationScore]:
    """OCR-score hero stills for presentation honesty residuals."""
    shots = _shot_dir(app_dir)
    floors = HERO_MIN_BYTES.get(app_name) or {}
    out: list[PresentationScore] = []
    if shots is None or not floors:
        return out

    for name in floors:
        path = shots / name
        if not path.is_file():
            continue  # absent stills skipped (CI)
        text = _ocr_png(path)
        if text is None:
            out.append(
                PresentationScore(
                    name=name,
                    path=str(path),
                    residual=False,
                    kind="ocr_skip",
                    reason="ocr_unavailable",
                )
            )
            continue

        leak = _find_ref_as_repr(text)
        if leak:
            out.append(
                PresentationScore(
                    name=name,
                    path=str(path),
                    residual=True,
                    kind="ref_as_repr",
                    reason=f"ref_as_repr:{name}",
                    snippet=leak[:120],
                )
            )
            continue

        theater = _find_delta_theater(text)
        if theater:
            out.append(
                PresentationScore(
                    name=name,
                    path=str(path),
                    residual=True,
                    kind="delta_theater",
                    reason=f"delta_theater:{name}",
                    snippet=theater[:120],
                )
            )
            continue

        if name in PERSON_AS_TEXT_STILLS and _PERSON_AS_TEXT_PATTERN.search(text):
            out.append(
                PresentationScore(
                    name=name,
                    path=str(path),
                    residual=True,
                    kind="person_as_text",
                    reason=f"person_as_text:{name}",
                    snippet="Assigned To:",
                )
            )
            continue

        out.append(
            PresentationScore(
                name=name,
                path=str(path),
                residual=False,
                kind="ok",
                reason="ok",
            )
        )
    return out
