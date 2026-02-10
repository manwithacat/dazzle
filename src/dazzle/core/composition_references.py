"""Composition reference library — few-shot exemplars for visual evaluation.

Manages a library of annotated section screenshots used as few-shot
references in LLM visual evaluation prompts.  Each reference is labelled
as "good" or "bad" for specific evaluation dimensions, stored alongside
a manifest.json per section type.

Directory layout::

    .dazzle/composition/references/
    ├── hero/
    │   ├── good-shadcn-hero.png
    │   ├── bad-no-image-hero.png
    │   └── manifest.json
    ├── features/
    │   ├── good-clean-icons.png
    │   ├── bad-blank-icons.png
    │   └── manifest.json
    └── ...
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class ReferenceImage:
    """An annotated reference screenshot for few-shot evaluation."""

    filename: str
    label: str  # "good" or "bad"
    section_type: str
    dimensions: list[str]  # which eval dimensions this is relevant for
    description: str  # what makes it good/bad
    source: str  # where it came from
    _base64_cache: str | None = field(default=None, repr=False)

    @property
    def base64(self) -> str:
        """Lazy-load and cache the base64-encoded image data."""
        if self._base64_cache is None:
            raise ValueError(
                f"base64 not loaded for {self.filename}. Call load_references() to populate."
            )
        return self._base64_cache

    def to_manifest_entry(self) -> dict[str, Any]:
        """Serialise to manifest JSON (excludes base64 cache)."""
        return {
            "filename": self.filename,
            "label": self.label,
            "section_type": self.section_type,
            "dimensions": self.dimensions,
            "description": self.description,
            "source": self.source,
        }


# ── Loader ───────────────────────────────────────────────────────────


def load_references(
    ref_dir: Path,
    *,
    section_types: list[str] | None = None,
    label_filter: str | None = None,
    max_per_section: int = 4,
) -> dict[str, list[ReferenceImage]]:
    """Load reference images from the library directory.

    Args:
        ref_dir: Root references directory.
        section_types: Only load these section types (default: all).
        label_filter: Only load "good" or "bad" (default: both).
        max_per_section: Maximum references per section type.

    Returns:
        Dict mapping section_type -> list of ReferenceImage with base64 loaded.
    """
    result: dict[str, list[ReferenceImage]] = {}

    if not ref_dir.exists():
        return result

    for section_dir in sorted(ref_dir.iterdir()):
        if not section_dir.is_dir():
            continue

        sec_type = section_dir.name
        if section_types and sec_type not in section_types:
            continue

        manifest_path = section_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read manifest for %s: %s", sec_type, e)
            continue

        refs: list[ReferenceImage] = []
        for entry in manifest.get("references", []):
            if label_filter and entry.get("label") != label_filter:
                continue

            img_path = section_dir / entry["filename"]
            if not img_path.exists():
                logger.debug("Reference image not found: %s", img_path)
                continue

            # Load and cache base64
            try:
                b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
            except OSError as e:
                logger.warning("Failed to read reference image %s: %s", img_path, e)
                continue

            ref = ReferenceImage(
                filename=entry["filename"],
                label=entry.get("label", "good"),
                section_type=sec_type,
                dimensions=entry.get("dimensions", []),
                description=entry.get("description", ""),
                source=entry.get("source", "unknown"),
                _base64_cache=b64,
            )
            refs.append(ref)

            if len(refs) >= max_per_section:
                break

        if refs:
            result[sec_type] = refs

    return result


# ── Manifest Writer ──────────────────────────────────────────────────


def save_manifest(
    section_dir: Path,
    references: list[ReferenceImage],
) -> Path:
    """Write manifest.json for a section type directory.

    Args:
        section_dir: Directory for this section type.
        references: List of ReferenceImage entries.

    Returns:
        Path to the written manifest.json.
    """
    section_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "section_type": section_dir.name,
        "references": [r.to_manifest_entry() for r in references],
    }
    manifest_path = section_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


# ── Auto-Promotion ───────────────────────────────────────────────────


def should_promote(
    *,
    dom_score: int,
    visual_score: int | None,
    dom_threshold: int = 95,
    visual_threshold: int = 90,
) -> bool:
    """Check if a section qualifies for promotion to the reference library.

    A section is promoted when it passes both DOM audit and visual
    evaluation at high confidence thresholds.

    Args:
        dom_score: Page-level DOM audit score.
        visual_score: Page-level visual evaluation score (None if not run).
        dom_threshold: Minimum DOM score for promotion.
        visual_threshold: Minimum visual score for promotion.

    Returns:
        True if the section qualifies for promotion.
    """
    if dom_score < dom_threshold:
        return False
    if visual_score is None:
        return False
    return visual_score >= visual_threshold


def promote_section(
    *,
    image_path: Path,
    section_type: str,
    ref_dir: Path,
    source: str = "dazzle-project",
    description: str = "",
) -> ReferenceImage | None:
    """Promote a captured section screenshot to the reference library.

    Copies the image into the reference directory and updates the manifest.

    Args:
        image_path: Path to the section screenshot.
        section_type: Section type (hero, features, etc.).
        ref_dir: Root references directory.
        source: Source attribution.
        description: What makes this a good reference.

    Returns:
        The created ReferenceImage, or None if the image doesn't exist.
    """
    if not image_path.exists():
        return None

    import shutil

    section_dir = ref_dir / section_type
    section_dir.mkdir(parents=True, exist_ok=True)

    # Copy image
    dest = section_dir / f"good-{source}-{section_type}.png"
    shutil.copy2(image_path, dest)

    ref = ReferenceImage(
        filename=dest.name,
        label="good",
        section_type=section_type,
        dimensions=[
            "content_rendering",
            "icon_media",
            "color_consistency",
            "layout_overflow",
            "visual_hierarchy",
        ],
        description=description or f"Auto-promoted from {source}",
        source=source,
    )

    # Update manifest
    manifest_path = section_dir / "manifest.json"
    existing_refs: list[ReferenceImage] = []
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            for entry in data.get("references", []):
                existing_refs.append(
                    ReferenceImage(
                        filename=entry["filename"],
                        label=entry.get("label", "good"),
                        section_type=section_type,
                        dimensions=entry.get("dimensions", []),
                        description=entry.get("description", ""),
                        source=entry.get("source", "unknown"),
                    )
                )
        except (json.JSONDecodeError, OSError):
            pass

    existing_refs.append(ref)
    save_manifest(section_dir, existing_refs)

    return ref


# ── Token Estimation ─────────────────────────────────────────────────


def estimate_reference_tokens(
    references: dict[str, list[ReferenceImage]],
    tokens_per_image: int = 680,
) -> int:
    """Estimate the token cost of including references in prompts.

    Args:
        references: Loaded reference library.
        tokens_per_image: Estimated tokens per reference image.

    Returns:
        Total estimated tokens for all loaded references.
    """
    total = 0
    for refs in references.values():
        total += len(refs) * tokens_per_image
    return total
