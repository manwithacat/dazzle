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
    UNSUPPORTED_DISPLAY = "unsupported_display"


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
    source: str = "declared"  # "declared" | "framework_injected"

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
                    "source": s.source,
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
#
# Issue #1033 (v0.66.140): `file` removed — the FileUpload primitive
# now handles file fields. The set is currently empty; the constant
# remains as the audit's blocker-list seam.
_UNSUPPORTED_FIELD_TYPES: frozenset[str] = frozenset()

# Surface-level `display:` values the adapter knows how to render.
# Empty string / None means "use the surface mode default" (e.g.
# `mode: list` + no display → standard Table).
#
# Mirrored against `WorkspaceRegionAdapter._BUILDERS | _ALIASES |
# _TIMESERIES_VIEWS` in src/dazzle/render/fragment/region/ (ADR-0038).
# We can't import the backend from core (layering rule) so the two
# lists must stay in sync. The drift is enforced by
# `tests/unit/render/fragment/test_coverage.py::test_supported_displays_match_adapter`.
_SUPPORTED_DISPLAYS: frozenset[str] = frozenset(
    {
        "",
        "list",
        "kanban",
        "timeline",
        "grid",
        "metrics",
        "summary",
        "bar_chart",
        "pivot_table",
        "tabbed_list",
        "activity_feed",
        "detail",
        "queue",
        "histogram",
        "funnel_chart",
        "status_list",
        "profile_card",
        "action_grid",
        "tree",
        "pipeline_steps",
        "progress",
        "heatmap",
        "confirm_action_panel",
        "search_box",
        "bar_track",
        "bullet",
        "diagram",
        "line_chart",
        "area_chart",
        "sparkline",
        "radar",
        "box_plot",
        "cohort_strip",  # #1018 (v0.67.7) — adapter live; data resolution pending
        "day_timeline",  # #1016 (v0.67.8) — adapter live; data resolution pending
        "task_inbox",  # #1015 (v0.67.8) — adapter live; data resolution pending
        "entity_card",  # #1017 (v0.67.8) — adapter live; data resolution pending
    }
)

# Display modes that are intentionally NOT in `_SUPPORTED_DISPLAYS` —
# the audit will continue to flag them so the gap stays visible. These
# are deferred for design reasons rather than time, and adding them
# without resolving the listed concerns will lock the framework into
# a decision that's harder to undo than to delay.
#
# `map`: vendor-neutral geographic rendering is genuinely hard. Three
#   options, each with a real cost:
#     1. Static SVG basemap — vendor-free but zero-zoom (granularity
#        is fixed at the embedded SVG asset).
#     2. Bring-your-own-tile-URL via Leaflet (BSD-licensed) — keeps the
#        framework neutral but pushes vendor choice to the deployer.
#     3. Defer until a real user picks. We've taken option 3.
#   The granularity question (street pin vs. region choropleth vs.
#   density heatmap) is more painful than the vendor question — each
#   wants a different IR shape and committing prematurely is worse
#   than the visible gap.
_DEFERRED_DISPLAYS: frozenset[str] = frozenset({"map"})


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
    mode_value: str
    if mode_obj is not None and hasattr(mode_obj, "value"):
        mode_value = str(mode_obj.value)
    elif mode_obj:
        mode_value = str(mode_obj)
    else:
        mode_value = ""
    if mode_value not in _SUPPORTED_MODES:
        blockers.append(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail=mode_value.upper()))

    for feature_attr in _UNSUPPORTED_FEATURES:
        value = getattr(surface, feature_attr, None)
        if value:
            blockers.append(Blocker(kind=BlockerKind.UNSUPPORTED_FEATURE, detail=feature_attr))

    # `display:` clause — Phase 4A. Surfaces with non-default display
    # (kanban, timeline, bar_chart, pivot_table, metrics, heatmap,
    # funnel_chart) need dedicated adapter dispatch the substrate
    # doesn't yet provide. Currently the adapter's _build_list emits
    # a Table regardless of `display:`, so a `display: kanban` surface
    # silently renders as a table — exactly the under-reporting Plan 13
    # closed for field types.
    display_value = (getattr(surface, "display", None) or "").strip()
    if display_value not in _SUPPORTED_DISPLAYS:
        blockers.append(Blocker(kind=BlockerKind.UNSUPPORTED_DISPLAY, detail=display_value))

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

    name_str = getattr(surface, "name", "<anonymous>")
    # Framework-injected surfaces use a `_admin_` or `_platform_` prefix
    # (admin_builder.py:744). Cyfuture pilot asked for this distinction
    # so consumers can ignore framework noise in their own coverage stats.
    source = "framework_injected" if name_str.startswith(("_admin_", "_platform_")) else "declared"
    return SurfaceCoverage(
        name=name_str,
        mode=mode_value.upper(),
        blockers=tuple(blockers),
        source=source,
    )


def _audit_workspace_region(workspace_name: str, region: object) -> SurfaceCoverage:
    """Inspect one workspace region against the capability matrix.

    Regions are a separate render target from surfaces — they have
    their own `display:` mode (DisplayMode enum, broader than
    SurfaceSpec.display). Each region becomes its own coverage entry
    keyed `<workspace>.<region>` with `mode = "REGION"`.

    Phase 4A scope: flag any non-default display. The adapter doesn't
    yet have region-level dispatch; this is the seam for Phase 4B
    (workspace_renderer.py port).
    """
    blockers: list[Blocker] = []

    display_obj = getattr(region, "display", None)
    display_value = ""
    if display_obj is not None:
        # DisplayMode is a StrEnum — both `.value` and str-coercion work
        display_value = (
            display_obj.value if hasattr(display_obj, "value") else str(display_obj)
        ).strip()
    if display_value not in _SUPPORTED_DISPLAYS:
        blockers.append(Blocker(kind=BlockerKind.UNSUPPORTED_DISPLAY, detail=display_value))

    region_name = getattr(region, "name", "<anonymous>")
    full_name = f"{workspace_name}.{region_name}"
    source = (
        "framework_injected" if workspace_name.startswith(("_admin_", "_platform_")) else "declared"
    )
    return SurfaceCoverage(
        name=full_name,
        mode="REGION",
        blockers=tuple(blockers),
        source=source,
    )


def audit_appspec(appspec: object) -> CoverageReport:
    """Walk every surface and workspace region in `appspec` and report
    Fragment-rendering coverage.

    `appspec` must expose `.surfaces` and `.domain.entities` for the
    field-type resolution to work; both are standard AppSpec shape.
    Anything missing falls back to "no resolution" — robust to partial input.

    v0.66.59: also walks `.workspaces[*].regions[*]` so display-mode
    coverage gaps in workspace regions are visible (Phase 4A). Each
    region becomes a coverage entry named `<workspace>.<region>` with
    `mode = "REGION"`.
    """
    surface_entries = [_audit_surface(appspec, s) for s in getattr(appspec, "surfaces", [])]

    region_entries: list[SurfaceCoverage] = []
    for ws in getattr(appspec, "workspaces", []) or []:
        ws_name = getattr(ws, "name", "<anonymous>")
        for region in getattr(ws, "regions", []) or []:
            region_entries.append(_audit_workspace_region(ws_name, region))

    return CoverageReport(surfaces=tuple(surface_entries + region_entries))
