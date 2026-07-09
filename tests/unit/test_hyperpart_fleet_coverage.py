"""Hyperpart fleet-coverage oracle (#164 — James's requirement).

Every HM Hyperpart must be exercised at least once by the example apps.
The F4d incident is the motivating case: the wizard was
registered-but-never-mounted for months — silently broken through every
fleet walk — because NO example declares multi-section experience
forms. A capability no example exercises is a capability nothing tests.

Mechanics: each Hyperpart maps to the DSL signal whose presence in an
example app makes Dazzle emit it (always-emitted framework chrome is
marked ALWAYS; gallery-only primitives are EXEMPT with a reason).
``KNOWN_GAPS`` is a ratchet: a Hyperpart listed there is a recorded
adoption debt — the test fails if a NEW gap appears (regression) and
fails if a listed gap is actually covered (remove it; the ratchet only
shrinks).
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"

# ── the coverage map ────────────────────────────────────────────────
# hyperpart id → ("always" | "exempt:<reason>" | regex over example DSL)
SIGNALS: dict[str, object] = {
    "button": "always",
    "badge": "always",
    "field": "always",
    "toolbar": "always",
    "empty-state": "always",
    "pagination": "always",
    "skeleton": "always",
    "menu": "always",  # workspace More-overflow; only emitted past the 3-action budget (anchor: acme_billing billing workspace)
    "card": "always",  # dashboard cards
    "stack": "always",  # L2: Stack/Row emitters
    "cluster": "always",
    "app-shell": "always",
    "grid": "always",  # every list surface
    "grid-list": r"display:\s*grid",
    "list-region": r"display:\s*list",
    "command": "always",  # ⌘K palette
    "confirm": "always",  # hx-confirm on every delete row action
    "dialog": "always",  # detail drawer family
    "drawer": r"peek:\s*slide_over",
    "master-detail": "exempt:gallery blueprint composition (no Dazzle mode yet)",
    "controls": "always",  # checkboxes in forms
    # field options use `=` (widget=slider), not `:` — the colon-only
    # regex was an oracle lie: design_studio has used slider all along
    "slider": r"widget\s*[:=]\s*slider",
    "confirm-panel": r"display:\s*confirm_action_panel",
    "search-box": r"display:\s*search_box",
    "form-chrome": r"^\s*section\b|section:",  # form/surface sections
    # the stepper renders only for experience steps whose SURFACE is
    # create/edit mode — checked structurally per app (see
    # _wizard_covered), not by corpus grep.
    "wizard": "structural:wizard",
    "money": r":\s*money",
    # HMC-018 HM-native widgets (replaced TomSelect): opt-in via `widget=`
    # on a create/edit field. Corpus: 12 combobox + 6 tags across
    # project_tracker/design_studio/component_showcase.
    "combobox": r"widget\s*[:=]\s*combobox",
    "tags": r"widget\s*[:=]\s*tags",
    "pdf": r"display:\s*pdf_viewer",
    "two-factor": "always",  # gated on sitespec presence — 7/12 examples mount /2fa/*
    # field-level DOTTED source refs only (source=pack.operation; the
    # workspace-region `source: Entity` keyword is a different feature).
    # Anchor: fieldtest_hub manufacturer ← companies_house_lookup.
    "search-select": r"source[:=]\s*\w+\.\w+",
    "date-range": r"date_range|date-range",
    "toggle-group": "exempt:no Dazzle emitter yet (gallery primitive)",
    "breadcrumb": "exempt:no Dazzle emitter yet (gallery primitive)",
    "accordion": "exempt:no Dazzle emitter yet (gallery primitive)",
    "tabs": r"display:\s*tabbed_list",
    "avatar": r"display:\s*profile_card",
    "progress": "exempt:no Dazzle emitter yet (the determinate bar; the StageBar is progress-region)",
    "sidebar-layout": "always",
    "auto-grid": "always",
    "center": "exempt:no Dazzle emitter yet (gallery/HM-site layout primitive)",
    "status-list": r"display:\s*status_list",
    "action-grid": r"display:\s*action_grid",
    "queue": r"display:\s*queue",
    "kanban": r"display:\s*kanban",
    "timeline": r"display:\s*(day_)?timeline",
    "activity-feed": r"display:\s*activity_feed",
    "related-tables": r"mode:\s*view",  # detail views with reverse FKs
    "metrics": r"display:\s*metrics",
    "sparkline": r"display:\s*sparkline",
    "funnel": r"display:\s*funnel_chart",
    "bar-chart": r"display:\s*bar_chart",
    "chart-legend": r"display:\s*(pie|area|line)_chart|overlay_series",
    "heatmap": r"display:\s*heatmap",
    "bullet": r"display:\s*bullet",
    "pivot": r"display:\s*pivot_table",
    "bar-track": r"display:\s*bar_track",
    "histogram": r"display:\s*histogram",
    "box-plot": r"display:\s*box_plot",
    "progress-region": r"display:\s*progress",
    "profile-card": r"display:\s*profile_card",
    "task-inbox": r"display:\s*task_inbox",
    "tree": r"display:\s*tree",
    "diagram": r"display:\s*diagram",
    "separator": "exempt:visual primitive, no DSL surface",
    "icon": "always",  # via command-palette results (lazy /command fetch) — thin anchor
    "popover": "exempt:no Dazzle emitter yet (gallery primitive)",
    "tooltip": "exempt:no Dazzle emitter yet (gallery primitive)",
    "alert": "exempt:no Dazzle emitter yet (form errors are form-chrome dz-form-errors; the banner is a CSS-only different contract)",
}

# ── the ratchet: recorded adoption debt (#164) ──────────────────────
# Remove an entry when an example adopts the feature; the test fails
# on unexpected NEW gaps and on stale entries. Each of these is a
# wizard-class blind spot until closed.
# NOTE: wizard is covered by ops_dashboard's alert_ack step (a
# SECTIONED edit surface inside an experience) — a single-section
# stepper, so step NAVIGATION is still unexercised; a multi-section
# adoption remains desirable but the Hyperpart does render + mount.
KNOWN_GAPS: set[str] = set()


def _wizard_covered() -> bool:
    """True when any example has an experience STEP whose surface is a
    create/edit-mode surface — the only shape that renders the wizard
    stepper. A corpus-wide grep can't express the join (ops_dashboard
    has experiences AND create surfaces, but its steps point at
    list/detail surfaces — no stepper)."""
    for app_dir in sorted(EXAMPLES.iterdir()):
        dsl = app_dir / "dsl"
        if not dsl.is_dir():
            continue
        text = "\n".join(p.read_text(encoding="utf-8") for p in sorted(dsl.glob("*.dsl")))
        step_surfaces = set(re.findall(r"^\s*surface\s+(\w+)\s*$", text, re.M))
        if not step_surfaces:
            continue
        for name in step_surfaces:
            # the step's surface must be create/edit mode AND declare
            # sections — a section-less form step renders plain fields,
            # no stepper (experience_renderer: `if sections:`)
            m = re.search(
                r"^surface\s+" + re.escape(name) + r"\b(?P<body>.*?)(?=^surface\s|\Z)",
                text,
                re.M | re.S,
            )
            if not m:
                continue
            body = m.group("body")
            if re.search(r"^\s*mode:\s*(create|edit)\b", body, re.M) and re.search(
                r"^\s*section\s+\w+", body, re.M
            ):
                return True
    return False


def _dsl_corpus() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(EXAMPLES.glob("*/dsl/*.dsl")))


def _registry_ids() -> set[str]:
    # importlib by path with a UNIQUE module name — never sys.path
    # pollution (a top-level module literally named `registry` would
    # shadow same-named modules for the rest of the xdist worker).
    import importlib.util
    import sys

    path = REPO / "packages/hatchi-maxchi/site/registry.py"
    spec = importlib.util.spec_from_file_location("_hm_registry_164", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_hm_registry_164"] = mod
    spec.loader.exec_module(mod)
    return {h.id for h in mod.HYPERPARTS}


def test_signal_map_covers_the_whole_registry() -> None:
    """Every registry Hyperpart must have a coverage signal (or an
    explicit exemption) — a new Hyperpart lands with its signal."""
    missing = _registry_ids() - set(SIGNALS)
    stale = set(SIGNALS) - _registry_ids()
    assert not missing, f"Hyperparts with no coverage signal: {sorted(missing)}"
    assert not stale, f"signals for retired Hyperparts: {sorted(stale)}"


def test_fleet_coverage_ratchet() -> None:
    corpus = _dsl_corpus()
    uncovered: list[str] = []
    for hp_id, signal in sorted(SIGNALS.items()):
        if isinstance(signal, str) and (signal == "always" or signal.startswith("exempt:")):
            continue
        if signal == "structural:wizard":
            hit = _wizard_covered()
        else:
            hit = bool(re.search(signal, corpus, re.M))
        if not hit:
            uncovered.append(hp_id)

    new_gaps = sorted(set(uncovered) - KNOWN_GAPS)
    closed = sorted(KNOWN_GAPS - set(uncovered))
    assert not new_gaps, (
        "NEW fleet-coverage gaps (a Hyperpart lost its last example — the "
        f"wizard-class blind spot): {new_gaps}"
    )
    assert not closed, (
        "these gaps are now covered — remove them from KNOWN_GAPS so the "
        f"ratchet keeps shrinking: {closed}"
    )
