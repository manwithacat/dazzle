#!/usr/bin/env python3
"""Build the HaTchi-MaXchi distribution bundle — self-contained, stdlib-only.

Produces:
    dist/hatchi-maxchi.css   tokens + base + components (design system only)
    dist/hatchi-maxchi.js    behaviour controllers (dz-confirm, dz-command)
    dist/fonts/              vendored Geist (OFL)

Unlike the Dazzle monorepo's ``scripts/build_dist.py`` (which bundles the
whole framework), this builds ONLY the design system, from package sources,
with no Dazzle imports — it runs identically in the standalone repo's CI.

Prefix (``--prefix``): the ``dz-`` namespace is the default, not a
requirement. Passing e.g. ``--prefix ax-`` rewrites every ``dz-``
occurrence — class names (``.dz-button``), data attributes
(``data-dz-tone``), and keyframes (``dz-fade-in``) — across the CSS and
JS. The rename is a plain textual transform, which works because the
namespace is used consistently; remember your markup must use the same
prefix (the gallery snippets are published with ``dz-``).
"""

import argparse
import re
import shutil
from pathlib import Path

PKG = Path(__file__).resolve().parent

# Concatenation order mirrors the monorepo cascade: fonts first (families
# exist before tokens reference them), tokens, base, then components.
# Each source is wrapped in a CSS cascade layer (declared in LAYER_ORDER);
# consumers' own unlayered CSS therefore always wins the cascade — override
# by writing plain rules, no specificity games needed. The layer names are
# a subset of Dazzle's (reset, vendor, tokens, base, utilities, components,
# overrides) so the bundle slots into its consumer's layer order unchanged.
CSS_SOURCES = [
    ("vendor", "base/fonts.css"),
    ("tokens", "tokens/tokens.css"),
    ("tokens", "base/design-system.css"),
    ("base", "base/base.css"),
    ("components", "components/accordion.css"),
    ("components", "components/alert.css"),
    ("components", "components/toast.css"),
    ("components", "components/badge.css"),
    ("components", "components/button.css"),
    ("components", "components/dialog.css"),
    ("components", "components/drawer.css"),
    ("components", "components/form.css"),
    ("components", "components/richtext.css"),
    ("components", "components/fragment-primitives.css"),
    ("components", "components/hm-core.css"),
    ("components", "components/htmx-states.css"),
    ("components", "components/transitions.css"),
    ("components", "components/pagination.css"),
    ("components", "components/skeleton.css"),
    ("components", "components/switch.css"),
    ("components", "components/toggle.css"),
    ("components", "components/aspect-ratio.css"),
    ("components", "components/item.css"),
    ("components", "components/hover-card.css"),
    ("components", "components/carousel.css"),
    ("components", "components/menubar.css"),
    ("components", "components/bubble.css"),
    ("components", "components/message.css"),
    ("components", "components/message-scroller.css"),
    ("components", "components/navigation-menu.css"),
    ("components", "components/marker.css"),
    ("components", "components/table.css"),
    ("components", "components/layout.css"),
    ("components", "components/app-shell.css"),
    ("components", "components/workspace-shell.css"),
    ("components", "components/status-list.css"),
    ("components", "components/action-grid.css"),
    ("components", "components/queue.css"),
    ("components", "components/kanban.css"),
    ("components", "components/timeline.css"),
    ("components", "components/activity-feed.css"),
    ("components", "components/related-tables.css"),
    ("components", "components/metrics.css"),
    ("components", "components/sparkline.css"),
    ("components", "components/funnel.css"),
    ("components", "components/bar-chart.css"),
    ("components", "components/chart-legend.css"),
    ("components", "components/heatmap.css"),
    ("components", "components/pivot.css"),
    ("components", "components/bullet.css"),
    ("components", "components/histogram.css"),
    ("components", "components/box-plot.css"),
    ("components", "components/bar-track.css"),
    ("components", "components/progress-region.css"),
    ("components", "components/task-inbox.css"),
    ("components", "components/grid-list.css"),
    ("components", "components/list-region.css"),
    ("components", "components/detail.css"),
    ("components", "components/onboarding.css"),
    ("components", "components/tree.css"),
    ("components", "components/diagram.css"),
    ("components", "components/confirm-panel.css"),
    ("components", "components/search-box.css"),
    ("components", "components/form-chrome.css"),
    ("components", "components/date-range.css"),
    ("components", "components/search-select.css"),
    ("components", "components/combobox.css"),
    ("components", "components/code.css"),
    ("components", "components/tags.css"),
    ("components", "components/profile-card.css"),
    ("components", "components/two-factor.css"),
    ("components", "components/pdf.css"),
    ("components", "components/pdf-viewer.css"),
    ("components", "components/tabs.css"),
    ("components", "components/touch-targets.css"),
    ("components", "components/mobile-scroll.css"),
    # fragments.css (HMC-016): shared fragment/region chrome families, migrated
    # wholesale from Dazzle. Registered late to preserve source-order tie-winning
    # it had when it loaded after the HM dist in the Dazzle bundle.
    ("components", "components/fragments.css"),
    # dashboard-card LAST (HMC-007d): its .dz-add-card-button must keep winning
    # over touch-targets' coarse-pointer override (source-order parity with the
    # pre-move state where Dazzle dashboard.css loaded after the whole HM dist).
    ("components", "components/dashboard-card.css"),
    ("components", "components/sitespec.css"),
    # feedback-widget.css left the package (dazzle#1854): the widget renders in a
    # shadow root and carries its stylesheet in feedback-widget.js.
]

LAYER_ORDER = "@layer vendor, tokens, base, components;"

JS_SOURCES = [
    "controllers/dz-confirm.js",
    "controllers/dz-cue.js",  # opt-in sound; toast and other hosts call window.dzCue
    "controllers/dz-toast.js",
    "controllers/dz-command.js",
    "controllers/dz-master-detail.js",
    "controllers/dz-dialog.js",
    "controllers/dz-slider.js",
    "controllers/dz-tabs.js",
    "controllers/dz-carousel.js",
    "controllers/dz-grid.js",
    "controllers/dz-grid-cols.js",
    "controllers/dz-grid-resize.js",
    "controllers/dz-grid-edit.js",
    "controllers/dz-kanban.js",
    "controllers/dz-app-shell.js",
    "controllers/dz-confirm-gate.js",
    "controllers/dz-search-select.js",
    "controllers/dz-combobox.js",
    "controllers/dz-tags.js",
    "controllers/dz-money.js",
    "controllers/dz-date-range.js",
    "controllers/dz-search-box.js",
    "controllers/dz-wizard.js",
    "controllers/dz-color.js",
    "controllers/dz-time.js",
    "controllers/dz-date.js",
    "controllers/dz-number.js",
    "controllers/dz-pdf.js",
    "controllers/dz-code.js",
    "controllers/dz-menubar.js",
    "controllers/dz-navigation-menu.js",
    "controllers/dz-details-light-dismiss.js",
    "controllers/dz-hover-card.js",
    "controllers/dz-toggle.js",
]

FONT_DIR = PKG / "site" / "fonts"  # tracked vendored copy (Geist, OFL)

# The DEFAULT published namespace is EMPTY — HM ships clean, unprefixed
# markup (`.button`, `data-tone`, `@keyframes fade-in`). A consumer applies
# its own namespace at ingest: Dazzle builds with prefix="dz-" (see
# src/dazzle/page/runtime/css_loader.py, scripts/build_dist.py), which is a
# no-op transform on the `dz-`-prefixed SOURCE — so Dazzle's output is
# byte-identical to before, while the standalone/CDN artifact is clean.
DEFAULT_PREFIX = ""

# A valid explicit prefix looks like `dz-` / `ax-`; "" means strip (the default).
_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]*-$")

# `dz-` in the SOURCE is the namespace token on classes, data-attributes,
# and keyframes — all part of the public API and reprefixable. Custom-property
# names are NOT blanket-reprefixed (the negative-lookbehind for `--` skips
# them): most are internal tokens, and stripping those wholesale would
# collide with real theme tokens (e.g. `--dz-shadow-sm` -> `--shadow-sm`).
_DZ_TOKEN_RE = re.compile(r"(?<!--)dz-")

# EXCEPT the public knobs: custom properties a CONSUMER sets — inline in a
# snippet (`style="--dz-progress-value:62%"`), server-emitted per request
# (`--dz-list-rows` from page_size), or overridden at :root
# (`--dz-touch-target-min`). These are API exactly like a class name, so
# they follow the prefix (strip -> `--progress-value`). Adding a name here
# requires checking it doesn't strip-collide with an existing bare token
# (test_public_css_props_follow_the_prefix gates the mechanics; the
# no-leak gate stops snippets referencing anything NOT listed here).
PUBLIC_CSS_PROPS = (
    "--dz-progress-value",
    "--dz-list-rows",
    "--dz-touch-target-min",
    # Layout knobs (L1): the sidebar pane width + wrap threshold, and the
    # auto-grid column minimum. Checked against strip-collisions like the
    # rest (no bare --sidebar-width/--grid-min/--sidebar-content-min exist).
    "--dz-sidebar-width",
    "--dz-sidebar-content-min",
    "--dz-grid-min",
)


# Structural wrappers that intentionally carry no rule of their own
# (styled via inheritance / parent selectors). Additions here need a
# comment explaining why (here and/or in the component's CSS). Shared with
# the Dazzle Fragment-renderer conformance gate (#1799).
SEMANTIC_ONLY: frozenset[str] = frozenset(
    {
        "dz-alert__body",
        # dz-empty-state__description removed 2026-07-09: it gained a style rule
        # (color + font-size) when the detail-view empty-state was folded into HM
        # (HMC-003c), so it is no longer semantic-only.
        # tab panel container: identity for the controller + a swap target; its
        # visibility rides the native `hidden` attribute, so it carries no rule.
        "dz-tabs__panel",
        # the select-column <col> in the grid's colgroup: a structural marker so
        # the resize/visibility extensions can address data cols by exclusion —
        # the table stays layout:auto, so the col itself needs no width rule.
        "dz-table-col-select",
        # region-body wrappers (W1): the workspace card slot provides the box;
        # these wrappers are the emitters' structural anchors and have never
        # carried rules (verbatim from Dazzle, where they were also rule-less).
        "dz-status-list-region",
        "dz-action-grid-region",
        "dz-queue-region",
        "dz-timeline-region",
        "dz-funnel-chart-region",
        "dz-bar-chart-region",
        "dz-heatmap-region",
        "dz-bullet-region",
        "dz-pivot-region",
        # dz-bar-track-region removed from SEMANTIC_ONLY — it gained grid
        # column-stop rules with the summary-alignment fix.
        "dz-histogram-region",
        "dz-box-plot-region",
        "dz-progress-region",
        "dz-line-chart-region",
        "dz-area-chart-region",
        "dz-radar-region",
        "dz-profile-card-region",
        "dz-grid-region",
        "dz-list-region",
        "dz-task-inbox-region",  # dual-lock root; chips/items own styling
        "dz-cohort-strip-region",  # dual-lock root; lenses/cells own styling
        "dz-day-timeline-region",  # dual-lock root; slots own styling
        "dz-entity-card-region",  # dual-lock root; sections own styling
        "dz-pipeline-steps-region",  # dual-lock root; stages own styling
        # wizard stage block: visibility rides the native `hidden` attribute
        # (dz-wizard.js); the fields inside carry the styling.
        "dz-wizard-stage",
        # money widget root: the data-dz-money marker + scale attribute are
        # the contract; the styled box is the inner dz-form-money-group.
        "dz-money",
        # search-box results container: the htmx swap target + aria-live
        # region — pure structure, its children (count/list/rows) carry the
        # styling.
        "dz-search-box-results",
        # task-inbox item skeleton (items/link/body/title/meta/empty) gained
        # rules in cycle 1355 coherence drain (list-style + flex row/urgency
        # tones) — removed from SEMANTIC_ONLY when styles landed.
        # tree root: the nodes/summaries carry the chrome and `data-dz-tree`
        # is the controller hook. (Surfaced in #1799 when the class gates
        # moved from substring to exact class-token matching.)
        "dz-tree",
        # ── Fragment-renderer structural classes (#1799). The Dazzle gate
        # (tests/unit/render/fragment/test_fragment_bundle_conformance.py) holds
        # every class the typed renderer emits to "has a rule OR is listed here",
        # so this set is the one allowlist for both repos.
        # htmx behaviour wrapper: carries hx-* attrs around any child; it must
        # not add a box of its own.
        "dz-interactive",
        # Region kind modifiers with no kind-specific chrome (list / detail /
        # related / form have rules in fragment-primitives.css; these kinds
        # take the base `.dz-region` flow — the modifier names the kind for
        # host CSS and agents).
        "dz-region--kind-calendar",
        "dz-region--kind-dashboard",
        "dz-region--kind-kanban",
        "dz-region--kind-report",
        # detail-grid region root (HM contracts/detail_grid.py): the
        # `dz-detail-region-grid` <dl> inside carries the layout, like every
        # other `*-region` root above.
        "dz-detail-region",
        # CalendarGrid view modifiers: the event list reads the same in each
        # view (fragment-primitives.css calendar note).
        "dz-calendar--view-day",
        "dz-calendar--view-week",
        "dz-calendar--view-month",
    }
)


def build_css(prefix: str = DEFAULT_PREFIX) -> str:
    parts = [LAYER_ORDER, ""]
    for layer, rel in CSS_SOURCES:
        css = (PKG / rel).read_text(encoding="utf-8")
        # Dazzle serves fonts at /static/fonts/; the standalone bundle
        # keeps them relative, next to the CSS.
        css = css.replace("/static/fonts/", "fonts/")
        parts.append(f"/* ── {rel} ── */\n@layer {layer} {{\n{css}\n}}")
    # exactly ONE trailing newline: keeps the committed artifacts stable
    # under end-of-file-fixer (adds if missing, trims if multiple)
    return apply_prefix("\n".join(parts).rstrip("\n") + "\n", prefix)


def build_js(prefix: str = DEFAULT_PREFIX) -> str:
    parts = [f"/* ── {rel} ── */\n{(PKG / rel).read_text(encoding='utf-8')}" for rel in JS_SOURCES]
    return apply_prefix("\n".join(parts).rstrip("\n") + "\n", prefix)


def apply_prefix(text: str, prefix: str) -> str:
    """Reprefix the design-system namespace. `prefix=""` strips it (the
    published default); `prefix="dz-"` keeps the source form; `prefix="ax-"`
    renames it. Custom-property names are untouched EXCEPT the public knobs
    in `PUBLIC_CSS_PROPS`, which follow the prefix like any other API name."""
    if prefix and not _PREFIX_RE.match(prefix):
        raise SystemExit(f"invalid prefix {prefix!r} — want '' (strip) or lowercase like 'ax-'")
    out = _DZ_TOKEN_RE.sub(prefix, text)
    for prop in PUBLIC_CSS_PROPS:
        out = out.replace(prop, "--" + prefix + prop.removeprefix("--dz-"))
    return out


def build(out_dir: Path, prefix: str = DEFAULT_PREFIX) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hatchi-maxchi.css").write_text(build_css(prefix), encoding="utf-8")
    (out_dir / "hatchi-maxchi.js").write_text(build_js(prefix), encoding="utf-8")
    fonts_out = out_dir / "fonts"
    fonts_out.mkdir(exist_ok=True)
    for f in FONT_DIR.iterdir():
        if f.is_file():
            shutil.copyfile(f, fonts_out / f.name)
    print(f"built dist -> {out_dir} (prefix {prefix!r})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(PKG / "dist"))
    ap.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help="class/attr namespace; '' (default) = unprefixed, e.g. 'dz-' or 'ax-' to prefix",
    )
    args = ap.parse_args()
    build(Path(args.out), args.prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
