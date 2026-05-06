"""Fragment-rendering coverage audit.

Walks any AppSpec and reports, per surface, whether the typed Fragment
substrate can render it given the adapter's current capabilities.

The audit is structural — it inspects each surface's IR features (mode,
field types, related_groups, companions, transitions) and cross-references
against the adapter's capability matrix. It does NOT actually invoke the
renderer or build a Fragment tree (no test data is required).

Subsequent plans close blockers by extending the adapter; the audit's
aggregated counts drive prioritisation: closing whichever blocker affects
the most surfaces first.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum


class BlockerKind(str, Enum):
    """Why a surface cannot currently be rendered via Fragment."""

    UNSUPPORTED_MODE = "unsupported_mode"
    UNSUPPORTED_FIELD_TYPE = "unsupported_field_type"
    UNSUPPORTED_FEATURE = "unsupported_feature"


@dataclass(frozen=True, slots=True)
class Blocker:
    """A single reason a surface is not Fragment-renderable today.

    `kind` names the structural class of obstruction; `detail` carries
    the specific instance (e.g. mode name, field type name, feature name).
    """

    kind: BlockerKind
    detail: str


@dataclass(frozen=True, slots=True)
class SurfaceCoverage:
    """Per-surface audit result."""

    name: str
    mode: str  # SurfaceMode.value as a string
    blockers: tuple[Blocker, ...]

    @property
    def is_ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Whole-AppSpec audit result."""

    surfaces: tuple[SurfaceCoverage, ...]

    @property
    def ready_count(self) -> int:
        return sum(1 for s in self.surfaces if s.is_ready)

    @property
    def blocked_count(self) -> int:
        return sum(1 for s in self.surfaces if not s.is_ready)

    @property
    def aggregated_blockers(self) -> dict[tuple[str, str], int]:
        """Map (kind, detail) → count of surfaces affected."""
        counter: Counter[tuple[str, str]] = Counter()
        for s in self.surfaces:
            for b in s.blockers:
                counter[(b.kind.value, b.detail)] += 1
        return dict(counter)


# Capability matrix — what FragmentSurfaceAdapter currently supports.
# Updated when the adapter gains new mode/feature/field-type support.
_SUPPORTED_MODES: frozenset[str] = frozenset({"list"})

# Surface-level features that block Fragment rendering when present.
# Each entry is the SurfaceSpec attribute name; if non-empty, the surface
# is blocked on that feature.
_UNSUPPORTED_FEATURES: tuple[str, ...] = (
    "related_groups",
    "companions",
    "search_fields",
    # NB: actions on a SurfaceSpec is empty for most simple surfaces;
    # adding it here would over-flag. Defer to a Plan-N adapter pass.
)

# Field types the adapter can't render. Plan 3's _format_cell str-coerces
# everything, so structurally no type is blocked yet — this constant is
# the seam for future restrictions (e.g. `ref` cells need FK-aware
# rendering and per-row link generation).
_UNSUPPORTED_FIELD_TYPES: frozenset[str] = frozenset()


def _audit_surface(surface: object) -> SurfaceCoverage:
    """Inspect one surface against the capability matrix."""
    blockers: list[Blocker] = []

    mode_obj = getattr(surface, "mode", None)
    mode_value = (
        mode_obj.value if hasattr(mode_obj, "value") else (str(mode_obj) if mode_obj else "")
    )
    if mode_value not in _SUPPORTED_MODES:
        blockers.append(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail=mode_value.upper()))

    for feature_attr in _UNSUPPORTED_FEATURES:
        value = getattr(surface, feature_attr, None)
        if value:
            blockers.append(Blocker(kind=BlockerKind.UNSUPPORTED_FEATURE, detail=feature_attr))

    for section in getattr(surface, "sections", []) or []:
        for field_spec in getattr(section, "fields", []) or []:
            ft = getattr(field_spec, "type", None) or getattr(field_spec, "field_type", None)
            if ft and str(ft).lower() in _UNSUPPORTED_FIELD_TYPES:
                blockers.append(
                    Blocker(
                        kind=BlockerKind.UNSUPPORTED_FIELD_TYPE,
                        detail=str(ft).lower(),
                    )
                )

    return SurfaceCoverage(
        name=getattr(surface, "name", "<anonymous>"),
        mode=mode_value.upper(),
        blockers=tuple(blockers),
    )


def audit_appspec(appspec: object) -> CoverageReport:
    """Walk every surface in `appspec` and report Fragment-rendering coverage.

    `appspec` is duck-typed — anything with a `.surfaces` iterable of
    SurfaceSpec-shaped objects works. The audit doesn't mutate or
    instantiate; it just inspects IR features.
    """
    surfaces = tuple(_audit_surface(s) for s in getattr(appspec, "surfaces", []))
    return CoverageReport(surfaces=surfaces)
