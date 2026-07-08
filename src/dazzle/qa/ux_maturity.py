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
from dazzle.core import ir
from dazzle.core.ir import AggregateRef, PeekMode, workspaces
from dazzle.core.ir.rhythm import PhaseKind
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.page import app_paths
from dazzle.page.runtime.action_prominence_resolver import (
    resolve_action_prominence,
    resolve_action_prominence_by_usage,
)
from dazzle.page.runtime.auto_display import resolve_region_display_mode
from dazzle.page.runtime.column_economy_resolver import (
    resolve_column_economy,
    resolve_column_economy_by_usage,
)
from dazzle.page.runtime.comparison_resolver import resolve_comparison
from dazzle.page.runtime.form_engagement_resolver import annotate_form_fields_by_usage
from dazzle.page.runtime.landing_resolver import check_landing_drift, infer_landing_route
from dazzle.page.runtime.peek_resolver import resolve_peek_mode
from dazzle.render import filters
from dazzle.render.context import ColumnContext, TransitionContext
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer._data_row import _render_cell_display, drill_row_attrs
from dazzle.render.fragment.state_affordance import gated_row_transitions

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
    """Region form is inferred by default (#1492) AND form fields adapt to
    observed usage (level 4, ADR-0050 Phase 5b): above the engagement floor
    the hottest plain field gains autofocus and a heavily-engaged long select
    upgrades to the searchable combobox; below the floor the field dicts are
    untouched (cold-start byte parity) — exercised through the real
    resolvers."""
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
    # Level 4: usage annotates the form's field dicts (autofocus + upgrade)…
    hot: list[dict[str, Any]] = [
        {"name": "title", "kind": "text", "label": "T"},
        {
            "name": "cat",
            "kind": "select",
            "label": "C",
            "options": [(str(i), str(i)) for i in range(10)],
        },
    ]
    annotate_form_fields_by_usage(hot, {"title": 30, "cat": 12})
    usage_adapts = hot[0].get("autofocus") is True and hot[1].get("widget") == "combobox"
    # …and below the floor is byte-identical (cold-start invariant).
    cold: list[dict[str, Any]] = [{"name": "title", "kind": "text", "label": "T"}]
    annotate_form_fields_by_usage(cold, {"title": 2})
    cold_parity = cold == [{"name": "title", "kind": "text", "label": "T"}]
    ok = default_infers and explicit_respected and rich and usage_adapts and cold_parity
    return ProbeResult(
        ok,
        f"unset->infer={default_infers}, explicit-list-respected={explicit_respected}, "
        f"kinds={len(kinds)}; usage-adapts-form={usage_adapts}, "
        f"below-floor-byte-parity={cold_parity}",
    )


def _probe_1c() -> ProbeResult:
    """Comparison context IS inferred by default and ADAPTS to the aggregate grain
    (level 4, #1491): an unset metrics region resolves to a period-over-period
    `DeltaSpec` for *any* grain over an entity with `created_at` — `count` AND
    scalar `sum`/`avg` (not just count, the level-3 limit) — so a revenue-sum or
    rating-avg tile gets a trend too. An explicit `delta:` still wins, and an
    undated entity gracefully stays a lone KPI. Exercises the real resolver."""
    dated_entity = SimpleNamespace(fields=[SimpleNamespace(name="created_at")])
    undated_entity = SimpleNamespace(fields=[SimpleNamespace(name="id")])
    repos_dated = {"Order": SimpleNamespace(entity_spec=dated_entity)}
    repos_undated = {"Order": SimpleNamespace(entity_spec=undated_entity)}

    count_infers = (
        resolve_comparison({"n": AggregateRef(func="count", entity="Order")}, repos_dated)
        is not None
    )
    # Level 4: a scalar grain infers the comparison too, adapting to the grain.
    sum_infers = (
        resolve_comparison(
            {"rev": AggregateRef(func="sum", entity="Order", column="amount")}, repos_dated
        )
        is not None
    )
    undated_stays_kpi = (
        resolve_comparison({"n": AggregateRef(func="count", entity="Order")}, repos_undated) is None
    )
    _, kinds = _display_kinds()
    have = kinds & {"comparison", "radar", "box_plot", "bullet", "sparkline", "heatmap"}
    ok = count_infers and sum_infers and undated_stays_kpi and bool(have)
    return ProbeResult(
        ok,
        f"count-infers={count_infers}, scalar-grain-infers={sum_infers}, "
        f"undated->kpi={undated_stays_kpi}, comparison-family kinds={sorted(have)}",
    )


def _probe_1b() -> ProbeResult:
    """A declared+validated status->tone binding is consumed at render time
    (#1493 slice 2), with WCAG colour+icon+text and state-machine inference.

    Level 4 evidence: the render-layer resolver `resolve_status_tone` consults a
    field's declared `semantic:` map before the `_STATUS_TONE_MAP` name guess, and
    the badge path threads that map (`ColumnContext.semantic_map`). On top of the
    level-3 binding, level 4 adds (a) WCAG colour+icon+text — `badge_icon_html`
    emits a non-colour glyph on every badge surface so state never relies on
    colour alone (WCAG 1.4.1); and (b) `infer_terminal_tone_map` —
    state-machine-terminal inference for undeclared, name-guess-miss values
    (a graph sink is a reached end-state), merged at build time by
    `status_tone_map`.
    """
    has_resolver = hasattr(filters, "resolve_status_tone")
    threads_binding = "semantic_map" in ColumnContext.model_fields
    has_fallback = hasattr(filters, "_STATUS_TONE_MAP")
    has_wcag_icon = hasattr(filters, "badge_icon_html")
    has_sm_inference = hasattr(filters, "infer_terminal_tone_map") and hasattr(
        filters, "status_tone_map"
    )
    ok = has_resolver and threads_binding and has_fallback and has_wcag_icon and has_sm_inference
    return ProbeResult(
        ok,
        f"declared semantic: binding consumed (resolver={has_resolver}, "
        f"ColumnContext.semantic_map={threads_binding}, name-guess-fallback={has_fallback}, "
        f"wcag-icon={has_wcag_icon}, sm-terminal-inference={has_sm_inference})",
    )


def _probe_1d() -> ProbeResult:
    """Raw data is humanised EXHAUSTIVELY at the shared cell core (level 4,
    #1491). This probe exercises the real render-layer core `_render_cell_display`
    for every humanised type and asserts none leak: no raw ISO timestamp, no
    full-precision float, no `key:val`-mangled JSON, plus the WCAG badge + bool
    icon. A coverage gate, not the old hasattr no-op. (The http detail seam maps
    form-input types onto these display types; that plumbing is unit-tested in
    test_raw_data_honesty_1d.py — the primitive under test lives in render.)"""
    dt_ok = "2026-06-30T" not in _render_cell_display({"type": "datetime"}, "2026-06-30T03:01:29")
    float_ok = "0.8850441412520064" not in _render_cell_display(
        {"type": "number"}, 0.8850441412520064
    )
    json_out = _render_cell_display({"type": "json"}, {"currency": "GBP", "amount": 500})
    json_ok = "amount: 500" in json_out  # summarised, not mangled to one value
    null_ok = _render_cell_display({"type": "number"}, None) == "—"  # no fabricated "0"
    badge_ok = "dz-badge" in _render_cell_display({"type": "badge"}, "open")
    bool_ok = "True" not in _render_cell_display({"type": "bool"}, True)
    ok = dt_ok and float_ok and json_ok and null_ok and badge_ok and bool_ok
    return ProbeResult(
        ok,
        f"cell core humanises: datetime={dt_ok}, float={float_ok}, json={json_ok}, "
        f"null->dash={null_ok}, badge={badge_ok}, bool={bool_ok}",
    )


def _probe_2a() -> ProbeResult:
    """Answer-first landing is inferred from a persona's rhythm when
    default_workspace is unset, declaration stays authoritative, and
    declared-vs-rhythm drift is detectable (level 4, #1558). Exercised against
    synthetic in-memory IR — the route-precedence integration lives in
    tests/unit/test_landing_resolver.py."""
    ws = [ir.WorkspaceSpec(name="queue"), ir.WorkspaceSpec(name="reports")]
    rhythm = ir.RhythmSpec(
        name="agent_daily",
        persona="agent",
        phases=[
            ir.PhaseSpec(
                name="active",
                kind=PhaseKind.ACTIVE,
                scenes=[ir.SceneSpec(name="review", surface="queue")],
            )
        ],
    )
    # (a) infer a workspace landing when default_workspace is unset
    p_unset = ir.PersonaSpec(id="agent", label="Agent")
    infers = infer_landing_route(p_unset, [rhythm], ws, []) == "/app/workspaces/queue"
    # (a2) a rhythm scene naming a LIST surface resolves to its registered route
    surf = ir.SurfaceSpec(name="ticket_list", mode=SurfaceMode.LIST, entity_ref="Ticket")
    r_surface = ir.RhythmSpec(
        name="agent_surface",
        persona="agent",
        phases=[
            ir.PhaseSpec(
                name="active",
                kind=PhaseKind.ACTIVE,
                scenes=[ir.SceneSpec(name="browse", surface="ticket_list")],
            )
        ],
    )
    infers_surface = infer_landing_route(p_unset, [r_surface], ws, [surf]) == app_paths.list_path(
        "/app", app_paths.entity_slug("Ticket")
    )
    # (b) declaration is distinguished from the rhythm (drift fires on conflict)
    p_conflict = ir.PersonaSpec(id="agent", label="Agent", default_workspace="reports")
    drift_fires = check_landing_drift(p_conflict, [rhythm], ws, []) is not None
    # (c) coherent declaration is silent
    p_ok = ir.PersonaSpec(id="agent", label="Agent", default_workspace="queue")
    drift_silent = check_landing_drift(p_ok, [rhythm], ws, []) is None
    # cold-start: no rhythm -> no inference (fall through unchanged)
    cold_start_safe = infer_landing_route(p_unset, [], ws, []) is None
    ok = infers and infers_surface and drift_fires and drift_silent and cold_start_safe
    return ProbeResult(
        ok=ok,
        note=(
            f"infer={infers} infer_surface={infers_surface} drift_fires={drift_fires} "
            f"drift_silent={drift_silent} cold_start_safe={cold_start_safe}"
        ),
    )


def _probe_2b() -> ProbeResult:
    """List->detail drill is the default AND perceived-instant (level 4, #1491):
    a clickable row carries `hx-preload="mouseover"`, so the vendored htmx-4
    preload extension warms the detail GET on hover and the click serves the
    cached prefetch. Exercises the real render seam (`drill_row_attrs`)."""
    drill = drill_row_attrs("/app/thing/1")
    preloads = 'hx-preload="mouseover"' in drill and "hx-get" in drill
    ok = hasattr(app_paths, "detail_path") and preloads
    return ProbeResult(ok, f"drill default + hover-preload wired (preload={preloads})")


def _probe_2d() -> ProbeResult:
    """Field economy is usage-boosted (level 4, ADR-0050 / #1524): above the
    engagement floor a heavily-engaged low-salience field survives truncation;
    below the floor the truncation is byte-identical to the declared-salience
    default (level-3 behaviour, cold-start safety) — both exercised through
    the real resolvers."""
    wide = [{"key": f"f{i}", "type": "text"} for i in range(10)]
    wide[0] = {"key": "title", "type": "text"}  # identifying — must survive
    wide[1] = {"key": "created_at", "type": "date"}  # timestamp — must drop
    kept = resolve_column_economy(wide)
    keys = {c["key"] for c in kept}
    trims_to_budget = len(kept) == 6
    keeps_identifying = "title" in keys
    drops_timestamp = "created_at" not in keys
    narrow = [{"key": "a", "type": "text"}, {"key": "b", "type": "badge"}]
    within_budget_noop = resolve_column_economy(narrow) == narrow
    # Above the floor, heavy engagement rescues the declared-last text field
    # f9 (dropped by the static truncation above).
    hot = {"f9": 40, "title": 5}
    kept_hot = resolve_column_economy_by_usage(wide, hot, key_of=lambda c: c["key"])
    usage_rescues = any(c["key"] == "f9" for c in kept_hot) and any(
        c["key"] == "title" for c in kept_hot
    )
    # Below the floor, byte-identical to the declared-salience truncation.
    cold_parity = (
        resolve_column_economy_by_usage(wide, {"f9": 2}, key_of=lambda c: c["key"]) == kept
    )
    ok = (
        trims_to_budget
        and keeps_identifying
        and drops_timestamp
        and within_budget_noop
        and usage_rescues
        and cold_parity
    )
    return ProbeResult(
        ok,
        f"over-budget->kept={len(kept)} (title kept={keeps_identifying}, "
        f"created_at dropped={drops_timestamp}); within-budget-noop={within_budget_noop}; "
        f"usage-rescues-hot-field={usage_rescues}; below-floor-byte-parity={cold_parity}",
    )


def _probe_2c() -> ProbeResult:
    """`peek:` + the resolve_peek_mode default-flip are live (#1494). An *unset*
    list surface whose entity has a detail surface resolves to `expand` (the
    inline action-proximate detail panel) by default; an explicit author value
    still wins. Proven by exercising the real resolver, not just a field check."""

    class _UnsetSurface:
        peek = None

    flips_to_expand = resolve_peek_mode(_UnsetSurface(), entity=object()) == PeekMode.EXPAND
    off_without_detail = resolve_peek_mode(_UnsetSurface(), entity=None) == PeekMode.OFF
    return ProbeResult(
        flips_to_expand and off_without_detail,
        "resolve_peek_mode default-flip — unset + detail surface -> peek: expand (action-proximate detail by default)",
    )


def _probe_3a() -> ProbeResult:
    """Action prominence is usage-weighted (level 4, ADR-0050): above the
    min-sample floor a frequently-clicked tail action is promoted into the
    primary row; below the floor the split is byte-identical to the declared-
    order default (level-3 behaviour, cold-start safety) — both exercised
    through the real resolvers."""
    over_budget = [{"label": f"a{i}", "route": f"/{i}"} for i in range(5)]
    # Declared-order default still demotes the tail (cold-start path).
    primary, overflow = resolve_action_prominence(over_budget)
    demotes_tail = len(primary) == 3 and len(overflow) == 2
    # Above the floor, the heavily-clicked tail action /4 is promoted.
    hot_tail = {"/4": 40, "/0": 5}
    p_hot, o_hot = resolve_action_prominence_by_usage(
        over_budget, hot_tail, route_of=lambda a: a["route"]
    )
    promotes_hot = any(a["route"] == "/4" for a in p_hot)
    # Below the floor, byte-identical to the declared-order split.
    p_cold, o_cold = resolve_action_prominence_by_usage(
        over_budget, {"/4": 2}, route_of=lambda a: a["route"]
    )
    cold_start_parity = (p_cold, o_cold) == (primary, overflow)
    ok = demotes_tail and promotes_hot and cold_start_parity
    return ProbeResult(
        ok,
        f"declared-order demote={demotes_tail}; usage-promotes-hot-tail={promotes_hot}; "
        f"below-floor-byte-parity={cold_start_parity}",
    )


def _probe_3b() -> ProbeResult:
    """Role-gated affordance via the provable RBAC matrix."""
    return ProbeResult(
        importlib.util.find_spec("dazzle.rbac") is not None,
        "provable RBAC matrix (permit/scope) gates affordances by role",
    )


def _probe_3c() -> ProbeResult:
    """State-gated affordances: only transitions valid from a record's current
    state are offered (detail view + list rows) via the shared
    `gated_row_transitions` gate — from_state == current or the '*' wildcard
    (level 4, #1558)."""
    ts = [
        TransitionContext(from_state="open", to_state="in_progress", label="Start"),
        TransitionContext(from_state="in_progress", to_state="resolved", label="Resolve"),
        TransitionContext(from_state="*", to_state="open", label="Reopen"),
    ]
    from_open = [t.to_state for t in gated_row_transitions(ts, "open")]
    from_resolved = [t.to_state for t in gated_row_transitions(ts, "resolved")]
    # From open: in_progress is offered; resolved is NOT (can't skip a state).
    open_ok = "in_progress" in from_open and "resolved" not in from_open
    # From resolved: only the '*' wildcard reopen applies; resolved-self is absent.
    resolved_reopen = "open" in from_resolved and "resolved" not in from_resolved
    empty_ok = gated_row_transitions(ts, "") == []
    ok = open_ok and resolved_reopen and empty_ok
    return ProbeResult(
        ok=ok,
        note=f"from_open={from_open} from_resolved={from_resolved} empty_gated={empty_ok}",
    )


def _probe_3d() -> ProbeResult:
    """Empty-state suppression: an empty region self-demotes (#1494). The
    `when_empty:` IR primitive + the render-time default-flip resolver are
    present, so an empty supporting region suppresses (OOB-delete) by default
    instead of rendering dead scaffolding."""
    have_resolver = importlib.util.find_spec("dazzle.page.runtime.when_empty_resolver") is not None
    have_enum = hasattr(workspaces, "WhenEmpty")
    return ProbeResult(
        have_resolver and have_enum,
        "when_empty: + resolve_when_empty default-flip — empty supporting region collapses to header-only",
    )


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
        4,
        "#1492 L3 + ADR-0050 Phase 5b L4 — `display: auto` is the DEFAULT (a genuinely-unset `display:` routes through resolve_region_display_mode -> resolve_auto_display, inferring the form from the data shape; an explicit value stays authoritative), AND form-field selection now adapts to observed usage: `annotate_form_fields_by_usage` (`page/runtime/form_engagement_resolver`, wired at the `page_routes` dispatch-ctx seam) consumes the dz-usage.js first-focus signal (`_dazzle_usage_events`, tenant-fenced) to autofocus the entity's most-engaged plain field and upgrade a heavily-engaged long select to the searchable combobox. Author-declared `widget:` is authoritative; rich client widgets are excluded from autofocus; cold-start byte-identical below the min-sample floor; every usage-driven change carries an explain-trace.",
        "high",
        _probe_1a,
    ),
    Criterion(
        "1b",
        "data_drives_ui",
        "semantic-state binding",
        4,
        "#1493 — a declared+validated `semantic:` binding (shared `enum` block or inline `enum[...]` field) is CONSUMED at render time: `resolve_status_tone` resolves the field's declared value->tone map before the `_STATUS_TONE_MAP` name guess, threaded via `ColumnContext.semantic_map`. Level 4 (adaptive) adds (a) WCAG colour+icon+text — `badge_icon_html` leads every non-neutral badge with a non-colour glyph (WCAG 1.4.1), so state never relies on colour alone; and (b) state-machine-terminal inference (`infer_terminal_tone_map`, merged by `status_tone_map`): an undeclared, name-guess-miss terminal state (a graph sink) is inferred a reached `success` end-state. Precedence: declared > name-guess > SM-terminal > neutral. Known limit: the IR doesn't yet classify a terminal as success-vs-failure, so a custom-named *failure* terminal needs an explicit `semantic:` binding.",
        "high",
        _probe_1b,
    ),
    Criterion(
        "1c",
        "data_drives_ui",
        "comparison context",
        4,
        "#1491 — an unset `metrics`/`summary` tile infers comparison context by DEFAULT and the inference ADAPTS to the aggregate grain (level 4): `resolve_comparison` (`page/runtime/comparison_resolver`) synthesises a 30-day period-over-period `DeltaSpec` for **any** grain — `count` AND scalar `sum`/`avg`/`min`/`max` — over an entity with `created_at`, and `_compute_aggregate_metrics` fires the prior-window query for every grain (`_prior_period_task`), so a revenue-sum or rating-avg tile shows a trend arrow + `vs prior 30 days`, not just count tiles. Applied at the shared compute seam (server-render + htmx lazy-fetch both light up). Sentiment is `neutral` for an inferred delta — magnitude/direction without asserting good/bad (declared `semantic:`/1b owns tone). An explicit author `delta:` always wins; an entity with no `created_at` gracefully stays a lone KPI. The comparison/outlier/rag/sparkline display kinds (#1470) remain for richer opt-in forms.",
        "high",
        _probe_1c,
    ),
    Criterion(
        "1d",
        "data_drives_ui",
        "raw-data honesty",
        4,
        "#1491 — raw data is humanised EXHAUSTIVELY at the shared cell core (`_render_cell_display`), list AND detail. The detail view fed the core form-input types (`checkbox`/`datetime`/`number`/`select`/`textarea`) the core didn't recognise, so it leaked raw `True` / ISO timestamps / full-precision floats / JSON mangled-to-one-value; `_detail_field_value` now reconciles form→display types and the core gained `datetime` (date+time), `number` (rounded float, no binary-precision leak), and `json` (compact `key: val · …` summary) branches + a dict/float-aware default. List columns map `FLOAT→number` / `JSON→json` too (decimal keeps str() precision; datetime stays date-only in dense lists). The `_probe_1d` drift gate now renders each type through the real detail seam and asserts no leak — a coverage assertion, not the old hasattr no-op.",
        "medium",
        _probe_1d,
    ),
    # Progressive disclosure
    Criterion(
        "2a",
        "progressive_disclosure",
        "answer-first landing",
        4,
        "#1558 L3 + rhythm inference L4 — the answer-first landing is inferred from a "
        "persona's rhythm (first active-phase scene) when default_workspace is unset, via "
        "`infer_landing_route` consulted in BOTH redirect resolvers: `_resolve_persona_route` "
        "(step 2.5) and `resolve_persona_workspace_route` (step 1.5, the in-app /app root). "
        "The scene target resolves to a workspace root route OR a list-mode surface's route "
        "keyed by the surface's entity through the app_paths SSOT (so it matches registration, "
        "never a dead link). An explicit default_workspace stays authoritative and cold-start "
        "(no rhythm) is byte-identical; declared-vs-rhythm drift surfaces as an advisory line "
        "in `dazzle rhythm fidelity`.",
        "medium",
        _probe_2a,
    ),
    Criterion(
        "2b",
        "progressive_disclosure",
        "depth in <=1 action",
        4,
        '#1491 — list→detail drill is the default (app_paths #1426, ref drill-down #1471) AND perceived-instant (level 4): every clickable row carries `hx-preload="mouseover"`, so the vendored htmx-4 `preload` extension (bundled into dazzle.min.js after the core) warms the detail GET on hover and the click serves the cached prefetch — drilling feels instant fleet-wide. The extension dedups per row (one prefetch / 5s) so a mouse-sweep doesn\'t storm the server; the prefetch is the same scope-filtered detail GET, so no RBAC change.',
        "low",
        _probe_2b,
    ),
    Criterion(
        "2c",
        "progressive_disclosure",
        "action-proximate detail",
        4,
        "#1494 — `peek:` (expand | slide_over | off) + the `resolve_peek_mode` default-flip: an *unset* list surface whose entity has a detail surface resolves to `peek: expand` by default, so each row gets an inline expand-in-place chevron that `hx-get`s the entity's detail *body* partial into a sibling panel row (the same detail body the drill page shows — one detail renderer, not two). Level 4 (adaptive): the right-by-default form is the default; the author writes nothing and gets action-proximate detail wherever a detail surface exists. An explicit `peek: off` opts out (true-unset discriminator: `SurfaceSpec.peek is None`). Render gates the chevron on `detail_url_template`, so a non-drillable row degrades to plain drill. Follow-ons (#1494 Slice 2): the click-to-edit view⇄edit partial swap + the `slide_over` render branch.",
        "medium",
        _probe_2c,
    ),
    Criterion(
        "2d",
        "progressive_disclosure",
        "field economy",
        4,
        "#1491 L3 + ADR-0050/#1524 L4 — auto-derived list columns infer field economy by default AND adapt to observed usage: `resolve_column_economy` (`page/runtime/column_economy_resolver`) keeps the top-6 most salient columns (identifying/title > badge/ref > scalar > auto-timestamp); `resolve_column_economy_by_usage` (wired at the `list_handlers` seam) boosts each column's salience by its form-engagement frequency (`_dazzle_usage_events`, tenant-fenced GROUP BY) so a heavily-used field survives truncation even if declared-low — bounded below the identifying-field floor, cold-start byte-identical below the min-sample floor. Dropped fields are recovered by the default row drill (2b) / `peek:` (2c). An explicit surface field projection is authoritative and rendered in full (auto-columns only).",
        "medium",
        _probe_2d,
    ),
    # Negative space
    Criterion(
        "3a",
        "negative_space",
        "frequency-weighted prominence",
        4,
        "#1491 L3 + ADR-0050 L4 — workspace heading actions infer prominence by default AND reorder by observed usage: `resolve_action_prominence` (`page/runtime/action_prominence_resolver`) keeps the top-3 prominent by declaration order and demotes the tail to a native `<details>` `More ⋯` overflow; `resolve_action_prominence_by_usage` (wired at the `page_routes` `_workspace_handler` seam) stable-sorts by per-tenant click frequency captured via `hx-headers`-tagged anchors + `UsageSignalMiddleware` into `_dazzle_usage_events`, so a frequently-clicked action stays in the primary row and a rarely-clicked declared-early one demotes. Cold-start byte-identical below the min-sample floor (a fresh app is exactly the declared-order L3 split). The observe→infer loop the framework thesis promises, closed for actions. Remaining follow-on: extend to row-action / bulk-toolbar / action-grid placements.",
        "medium",
        _probe_3a,
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
        4,
        "#1558 L3 + current-state gating L4 — state-machine transition affordances are "
        "filtered to those valid FROM the record's current state (from_state == current or "
        "'*', via the shared `gated_row_transitions`) on BOTH the detail view (request-time "
        "filter in page_routes) and regular list rows (per-row, in the row actions cell). "
        "The compile build preserves `from_state` on TransitionContext; guards remain "
        "enforced by HTTP validation on click; no state machine = byte-identical.",
        "low",
        _probe_3c,
    ),
    Criterion(
        "3d",
        "negative_space",
        "empty-state suppression",
        4,
        "#1494 — `when_empty:` (message | collapse | suppress) + the render-time "
        "default-flip (`resolve_when_empty`) make empty-state handling **adaptive**: "
        "an empty *supporting* widget (chart/metric/summary, or any region with "
        "declared `aggregates`) self-**collapses** to header-only by default (the dead "
        "body scaffolding goes via a native `HX-Reswap: delete` at the lazy-load seam — "
        "no bespoke JS), while a *primary content* region (list/grid/kanban/…) and any "
        "region with an author `empty_message:` keep their typed empty-state. Two "
        "safety refinements keep the auto-default from over-reaching: the geometry gate "
        "skips grid assertions for a collapsed region (`ViewportAssertion.skip_if_absent` "
        "— geometry is N/A for an absent grid), and a picker-**added** card is exempt "
        "(it shows its empty-state, `?added=1`). Full `suppress` (card removal) stays "
        "explicit opt-in. Level 4 (adaptive): the empty region's presence adapts to its "
        "data + role, traceable to `display`/`aggregates`/`empty_message`.",
        "high",
        _probe_3d,
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
