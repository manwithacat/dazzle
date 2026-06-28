"""Framework UX-maturity rubric — the static capability scan.

Scores **Dazzle the framework** (not a screen): does Dazzle make the data-right
UI the DEFAULT? Each of 13 criteria carries a *declared* capability level (0-4,
the version-pinned baseline assessment) plus a *probe* — a lightweight, robust
check against the framework's own IR / registry / renderer that confirms the
declared level's premise still holds. A probe that disagrees with its declared
level is **drift**: a primitive shipped (level should rise) or regressed (level
fell). The CLI emits the scorecard; `tests/unit/test_ux_maturity_baseline.py`
gates the drift.

Rubric + ladder + criteria: ``docs/reference/ux-maturity.md``. This is the
*capability* (static) pass; the rendered/attribution pass is the ``/ux-maturity``
agent command.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

# Hoisted (no cycle: qa -> render/page/core is the correct layer direction; #1438).
from dazzle._version import get_version
from dazzle.core.ir import state_machine
from dazzle.page import app_paths
from dazzle.page.runtime.auto_display import resolve_region_display_mode
from dazzle.render import filters
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import format_cell
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter

# ── Ladder ───────────────────────────────────────────────────────────────
LEVEL_NAMES = {
    0: "absent",
    1: "escape-hatch",
    2: "declarative-manual",
    3: "good-defaults",
    4: "adaptive",
}


def _rag(level: float) -> str:
    if level <= 1:
        return "red"
    if level < 3:
        return "amber"
    return "green"


@dataclass(frozen=True)
class ProbeResult:
    ok: bool  # framework state is consistent with the declared level
    note: str  # human-readable evidence the probe observed


@dataclass(frozen=True)
class Criterion:
    id: str
    principle: str
    name: str
    declared: int  # baseline capability level (0-4)
    evidence: str
    leverage: str  # high | medium | low — for backlog ordering of red/amber rows
    probe: Callable[[], ProbeResult] | None = field(default=None)


PRINCIPLES = {
    "data_drives_ui": "Data drives the UI — choose the form",
    "progressive_disclosure": "Progressive disclosure — choose the amount",
    "negative_space": "Negative space — choose whether",
}


# ── Probes (robust, import-based — read the actual structure, not line numbers) ──


def _display_kinds() -> tuple[dict[str, str], set[str]]:
    """The full set of region display kinds (builders + aliases + timeseries
    views) and the raw `_BUILDERS` map."""
    builders = dict(WorkspaceRegionAdapter._BUILDERS)
    kinds = set(builders)
    for attr in ("_ALIASES", "_TIMESERIES_VIEWS"):
        kinds |= set(getattr(WorkspaceRegionAdapter, attr, {}) or {})
    return builders, kinds


def _probe_1a() -> ProbeResult:
    """Region form IS inferred by default (level 3): a genuinely-unset `display:`
    routes through the shape->form resolver, not the list template (#1492
    default-flip). Confirms the declared level by exercising the real dispatch
    decision — an unset region with a scalar aggregate must resolve to SUMMARY,
    not LIST."""
    unset_agg = SimpleNamespace(
        display="list", display_unset=True, aggregates={"n": object()}, source=""
    )
    explicit_list = SimpleNamespace(
        display="list", display_unset=False, aggregates={"n": object()}, source=""
    )
    default_infers = resolve_region_display_mode(unset_agg, {}) == "SUMMARY"
    # an explicit `display: list` is authoritative — never re-inferred
    explicit_respected = resolve_region_display_mode(explicit_list, {}) == "LIST"
    _, kinds = _display_kinds()
    rich = len(kinds) >= 10
    ok = default_infers and explicit_respected and rich
    return ProbeResult(
        ok,
        f"unset->infer={default_infers}, explicit-list-respected={explicit_respected}, "
        f"kinds={len(kinds)}",
    )


def _probe_1c() -> ProbeResult:
    """Comparison/distribution vocabulary exists (so the gap is the default, not
    the vocabulary)."""
    _, kinds = _display_kinds()
    have = kinds & {"comparison", "radar", "box_plot", "bullet", "sparkline", "heatmap"}
    return ProbeResult(bool(have), f"comparison-family kinds present: {sorted(have)}")


def _probe_1b() -> ProbeResult:
    """A declared+validated status->tone binding is consumed at render time
    (#1493 slice 2), with the name-convention map as the documented fallback.

    Level 3 evidence: the render-layer resolver `resolve_status_tone` consults a
    field's declared `semantic:` map before the `_STATUS_TONE_MAP` name guess,
    and the list/table badge path threads that map (`ColumnContext.semantic_map`,
    populated from shared-enum `EnumValueSpec.semantic` / inline
    `FieldType.enum_semantics`). Reaching 4 = icon (WCAG colour+icon+text) on
    every badge surface + state-machine-terminal inference when undeclared.
    """
    has_resolver = hasattr(filters, "resolve_status_tone")
    threads_binding = "semantic_map" in ColumnContext.model_fields
    has_fallback = hasattr(filters, "_STATUS_TONE_MAP")
    ok = has_resolver and threads_binding and has_fallback
    return ProbeResult(
        ok,
        f"declared semantic: binding consumed (resolver={has_resolver}, "
        f"ColumnContext.semantic_map={threads_binding}, name-guess-fallback={has_fallback})",
    )


def _probe_1d() -> ProbeResult:
    """The cell format layer humanises float/bool/ref/money by default."""
    has_infer = hasattr(format_cell, "_infer") or hasattr(format_cell, "format_cell")
    return ProbeResult(has_infer, "format_cell layer present (float->2dp, bool->Yes/No, FK->name)")


def _probe_2b() -> ProbeResult:
    """List->detail drill is the default path (app_paths.detail_path)."""
    return ProbeResult(hasattr(app_paths, "detail_path"), "app_paths.detail_path drill default")


def _probe_2c() -> ProbeResult:
    """A row-peek primitive exists (slide-over) but is a manual flag."""
    has_peek = "slide_over" in TableContext.model_fields
    return ProbeResult(has_peek, "TableContext.slide_over (manual row-peek)")


def _probe_3b() -> ProbeResult:
    """Role-gated affordance via the provable RBAC matrix."""
    return ProbeResult(
        importlib.util.find_spec("dazzle.rbac") is not None,
        "provable RBAC matrix (permit/scope) gates affordances by role",
    )


def _probe_3c() -> ProbeResult:
    """State-gated affordance via the state machine (transitions)."""
    has_sm = hasattr(state_machine, "StateMachineSpec")
    return ProbeResult(has_sm, "state-machine transitions gate actions by entity state")


def _probe_3e() -> ProbeResult:
    """Scope concealment: rows outside scope are never rendered (predicate
    algebra + RLS)."""
    have = importlib.util.find_spec("dazzle.core.ir.predicates") is not None
    return ProbeResult(have, "scope: -> predicate algebra (core.ir.predicates) + RLS conceals rows")


# ── The 13 criteria (declared baseline = the v0.87.x assessment) ─────────────

CRITERIA: list[Criterion] = [
    # Data drives the UI
    Criterion(
        "1a",
        "data_drives_ui",
        "region form inference",
        3,
        "`display: auto` is now the DEFAULT (#1492 default-flip): a genuinely-unset `display:` routes through resolve_region_display_mode -> resolve_auto_display, inferring the form from the data shape (aggregate->summary/chart, state-machine->kanban, temporal->timeline, else list). An explicit `display: list` stays authoritative (true-unset discriminator: WorkspaceRegion.display_unset). Level 3 (good-defaults): the data-right form is the default; the author writes nothing. Reaching 4 (adaptive) = runtime/usage-driven form selection.",
        "high",
        _probe_1a,
    ),
    Criterion(
        "1b",
        "data_drives_ui",
        "semantic-state binding",
        3,
        "#1493 — a declared+validated `semantic:` binding (shared `enum` block or inline `enum[...]` field) is now CONSUMED at render time: `resolve_status_tone` resolves the field's declared value->tone map before the `_STATUS_TONE_MAP` name guess, and the list/table badge path threads it via `ColumnContext.semantic_map`. Level 3 (good-defaults): the declared binding is authoritative where it renders; the name guess is the documented fallback. Reaching 4 (adaptive) = WCAG colour+icon+text on every badge surface + state-machine-terminal inference for undeclared values.",
        "high",
        _probe_1b,
    ),
    Criterion(
        "1c",
        "data_drives_ui",
        "comparison context",
        2,
        "comparison/outlier/rag/sparkline kinds exist (#1470) but are opt-in; a scalar defaults to a lone KPI",
        "high",
        _probe_1c,
    ),
    Criterion(
        "1d",
        "data_drives_ui",
        "raw-data honesty",
        3,
        "format_cell humanises float/bool/FK(display_field)/money by default; recent gaps (#1479 metric tiles, #1487 titles) closed",
        "medium",
        _probe_1d,
    ),
    # Progressive disclosure
    Criterion(
        "2a",
        "progressive_disclosure",
        "answer-first landing",
        3,
        "workspaces + default_workspace are answer-first by design (regions, not raw CRUD)",
        "medium",
        None,
    ),
    Criterion(
        "2b",
        "progressive_disclosure",
        "depth in <=1 action",
        3,
        "list->detail drill is the default (app_paths #1426, ref drill-down #1471)",
        "low",
        _probe_2b,
    ),
    Criterion(
        "2c",
        "progressive_disclosure",
        "action-proximate detail",
        2,
        "TableContext.slide_over exists (row-peek) but is opt-in, not default/inferred",
        "medium",
        _probe_2c,
    ),
    Criterion(
        "2d",
        "progressive_disclosure",
        "field economy",
        2,
        "per-persona `hide:` exists; no column-priority / show-top-N economy default",
        "medium",
        None,
    ),
    # Negative space
    Criterion(
        "3a",
        "negative_space",
        "frequency-weighted prominence",
        2,
        "command palette + primary/overflow/row actions exist; placement is manual, not frequency-derived",
        "medium",
        None,
    ),
    Criterion(
        "3b",
        "negative_space",
        "role-gated affordance",
        4,
        "provable RBAC matrix (permit/scope) gates affordances by role, inferred from the declared rules",
        "low",
        _probe_3b,
    ),
    Criterion(
        "3c",
        "negative_space",
        "state-gated affordance",
        3,
        "state-machine transitions offer only the actions the current state allows (inferred from the state graph)",
        "low",
        _probe_3c,
    ),
    Criterion(
        "3d",
        "negative_space",
        "empty-state suppression",
        2,
        "EmptyState renders a placeholder; an empty region does not self-demote/hide",
        "high",
        None,
    ),
    Criterion(
        "3e",
        "negative_space",
        "scope concealment",
        4,
        "scope: compiles to predicate algebra + RLS, so unactionable rows are never rendered",
        "low",
        _probe_3e,
    ),
]


def run_scan() -> dict[str, Any]:
    """Run the static capability scan and return the scorecard dict (the
    output schema in docs/reference/ux-maturity.md)."""
    crit_out: dict[str, Any] = {}
    by_principle: dict[str, list[int]] = {p: [] for p in PRINCIPLES}
    backlog: list[dict[str, Any]] = []
    version = get_version()

    for c in CRITERIA:
        probe_note = None
        if c.probe is not None:
            try:
                pr = c.probe()
                probe_note = pr.note
            except Exception as exc:  # a broken probe must not crash the scan
                probe_note = f"probe error: {type(exc).__name__}: {exc}"
        crit_out[c.id] = {
            "principle": c.principle,
            "name": c.name,
            "capability": c.declared,
            "rendered": None,
            "rag": _rag(c.declared),
            "evidence": c.evidence,
            "probe": probe_note,
            "attribution": None,
        }
        by_principle[c.principle].append(c.declared)
        if c.declared <= 2:  # red/amber → framework backlog
            backlog.append(
                {
                    "criterion": c.id,
                    "name": c.name,
                    "leverage": c.leverage,
                    "level": c.declared,
                    "gap": c.evidence,
                    "since_version": version,
                }
            )

    levels = [c.declared for c in CRITERIA]
    overall = round(sum(levels) / len(levels), 2)
    principles_out = {
        p: {
            "index": round(sum(v) / len(v), 2) if v else 0.0,
            "rag": _rag(sum(v) / len(v) if v else 0.0),
            "criteria": [c.id for c in CRITERIA if c.principle == p],
        }
        for p, v in by_principle.items()
    }
    # leverage order for the backlog (high first), then lowest level first
    _lev = {"high": 0, "medium": 1, "low": 2}
    backlog.sort(key=lambda b: (_lev.get(b["leverage"], 3), b["level"]))

    return {
        "framework_version": version,
        "overall_index": overall,
        "rag": _rag(overall),
        "principles": principles_out,
        "criteria": crit_out,
        "framework_backlog": backlog,
    }


def drift_violations() -> list[str]:
    """For the drift gate: a probe whose observed state contradicts its declared
    capability premise. Empty list = baseline in sync with the framework."""
    out: list[str] = []
    for c in CRITERIA:
        if c.probe is None:
            continue
        try:
            pr = c.probe()
        except Exception as exc:
            out.append(f"{c.id}: probe raised {type(exc).__name__}: {exc}")
            continue
        if not pr.ok:
            out.append(
                f"{c.id} ({c.name}): declared level {c.declared} but probe disagrees "
                f"— {pr.note}. Re-score and update the baseline in qa/ux_maturity.py."
            )
    return out
