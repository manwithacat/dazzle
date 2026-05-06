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
from enum import StrEnum


class BlockerKind(StrEnum):
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

    def to_text(self) -> str:
        """Render a human-readable report.

        Format roughly mirrors `dazzle coverage`: header line, ready
        section, blocked section, aggregated-blockers section.
        """
        lines: list[str] = []
        total = len(self.surfaces)
        lines.append(f"Coverage: {self.ready_count} / {total} surfaces ready to flip")
        lines.append("")

        ready = [s for s in self.surfaces if s.is_ready]
        blocked = [s for s in self.surfaces if not s.is_ready]

        if ready:
            lines.append(f"Ready ({len(ready)}):")
            for s in ready:
                lines.append(f"  ✓ {s.name:30s} mode={s.mode.lower()}")
            lines.append("")

        if blocked:
            lines.append(f"Blocked ({len(blocked)}):")
            for s in blocked:
                blocker_summary = "; ".join(f"{b.kind.value}={b.detail}" for b in s.blockers)
                lines.append(f"  ✗ {s.name:30s} mode={s.mode.lower()}: {blocker_summary}")
            lines.append("")

        if blocked:
            lines.append("Aggregated blockers (close highest-count first):")
            agg = self.aggregated_blockers
            for (kind, detail), count in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"  {count:>3d}  {kind}={detail}")
            lines.append("")

        return "\n".join(lines)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Render the report as JSON. Stable shape for piping into tooling."""
        import json

        agg = self.aggregated_blockers
        agg_list = [
            {"kind": kind, "detail": detail, "count": count}
            for (kind, detail), count in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        payload = {
            "total": len(self.surfaces),
            "ready_count": self.ready_count,
            "blocked_count": self.blocked_count,
            "surfaces": [
                {
                    "name": s.name,
                    "mode": s.mode,
                    "is_ready": s.is_ready,
                    "blockers": [{"kind": b.kind.value, "detail": b.detail} for b in s.blockers],
                }
                for s in self.surfaces
            ],
            "aggregated_blockers": agg_list,
        }
        return json.dumps(payload, indent=indent)


# Capability matrix — what FragmentSurfaceAdapter currently supports.
# Updated when the adapter gains new mode/feature/field-type support.
_SUPPORTED_MODES: frozenset[str] = frozenset({"list", "view", "create", "edit"})

# Surface-level features that block Fragment rendering when present.
# Each entry is the SurfaceSpec attribute name; if non-empty, the surface
# is blocked on that feature.
_UNSUPPORTED_FEATURES: tuple[str, ...] = (
    # related_groups closed in Plan 10.
    "companions",
    "search_fields",
    # NB: actions on a SurfaceSpec is empty for most simple surfaces;
    # adding it here would over-flag. Defer to a Plan-N adapter pass.
)

# Field types the adapter can't render. Plan 3's _format_cell str-coerces
# everything, so structurally no type is blocked yet — this constant is
# the seam for future restrictions (e.g. `ref` cells need FK-aware
# rendering and per-row link generation).
_UNSUPPORTED_FIELD_TYPES: frozenset[str] = frozenset({"ref", "uuid", "json", "file"})


def _resolve_field_kind(appspec: object, entity_name: str, field_name: str) -> str | None:
    """Look up `field_name` on the entity named `entity_name` in
    `appspec.domain.entities`. Returns the FieldType.kind value as a
    lowercase string (e.g. 'ref', 'uuid', 'str'), or None if the entity
    isn't found or the field doesn't exist on it.

    The audit's job is to surface adapter gaps, not validate the IR —
    a missing entity or field returns None and the caller proceeds
    without flagging. The linker enforces structural validity earlier.
    """
    domain = getattr(appspec, "domain", None)
    if domain is None:
        return None
    for entity in getattr(domain, "entities", []) or []:
        if getattr(entity, "name", None) != entity_name:
            continue
        for field_spec in getattr(entity, "fields", []) or []:
            if getattr(field_spec, "name", None) != field_name:
                continue
            ft = getattr(field_spec, "type", None)
            kind_obj = getattr(ft, "kind", None) if ft is not None else None
            if kind_obj is None:
                return None
            kind_value = getattr(kind_obj, "value", None)
            return str(kind_value or kind_obj).lower()
        return None
    return None


def _audit_surface(appspec: object, surface: object) -> SurfaceCoverage:
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

    entity_ref = getattr(surface, "entity_ref", None)
    if entity_ref:
        seen_kinds: set[str] = set()
        for section in getattr(surface, "sections", []) or []:
            for element in getattr(section, "elements", []) or []:
                field_name = getattr(element, "field_name", None)
                if not field_name:
                    continue
                kind = _resolve_field_kind(appspec, entity_ref, field_name)
                if kind and kind in _UNSUPPORTED_FIELD_TYPES and kind not in seen_kinds:
                    seen_kinds.add(kind)
                    blockers.append(Blocker(kind=BlockerKind.UNSUPPORTED_FIELD_TYPE, detail=kind))

    return SurfaceCoverage(
        name=getattr(surface, "name", "<anonymous>"),
        mode=mode_value.upper(),
        blockers=tuple(blockers),
    )


def audit_appspec(appspec: object) -> CoverageReport:
    """Walk every surface in `appspec` and report Fragment-rendering coverage.

    `appspec` must expose `.surfaces` and `.domain.entities` for the
    field-type resolution to work; both are standard AppSpec shape.
    Anything missing falls back to "no resolution" — robust to partial input.
    """
    surfaces = tuple(_audit_surface(appspec, s) for s in getattr(appspec, "surfaces", []))
    return CoverageReport(surfaces=surfaces)
