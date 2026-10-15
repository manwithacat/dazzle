"""Stylesheet regressions the renderer relies on, pinned as parsed rule facts.

Each row names the issue it guards. Rules are read with a small CSS parser
(selector list -> merged declarations, inside an optional at-rule), so a pin
fails on the declaration, not on a character window around a selector:

* #930 / CyFuture letter filters: inputs and native selects fit a 1.4 line-box;
* #985: the workspace heading and its primary-actions row wrap;
* #1596: the fixed sidebar panel scrolls itself, with a sticky header;
* #921: sitespec article bodies opt out of the centred headline style;
* #1590 / #1591 (CyFuture pilot): sitespec steps share equal columns and the
  site nav wraps instead of overflowing;
* #958: touch targets reach 44px under ``pointer: coarse``;
* #960: animation tokens resolve to defined keyframes, and collapse under
  reduced motion;
* #1079 / #1081 / Fragment primitives / #26: every class the renderer emits has
  a rule (layout Hyperparts, dark-mode site sections, theme toggle);
* retired selectors (L2 row/gap modifiers, the #1450 empty-state guard, #977
  Quill) stay out of the sources and the served bundle;
* the comment-bomb class (a ``*/`` inside a comment swallowing the next rule).
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
HM = REPO / "packages" / "hatchi-maxchi"
COMPONENTS = HM / "components"
TOKENS = HM / "tokens" / "tokens.css"
DAZZLE_CSS = REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "css"
DIST_CSS = REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "dist" / "dazzle.min.css"

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
ANY = object()  # the property must be declared, any value


@cache
def _rules(path: Path) -> tuple[tuple[tuple[str, ...], tuple[str, ...], dict[str, str]], ...]:
    """(enclosing at-rule preludes, selector list, declarations) for every rule."""
    text = _COMMENT.sub("", path.read_text(encoding="utf-8"))
    out: list[tuple[tuple[str, ...], tuple[str, ...], dict[str, str]]] = []
    stack: list[tuple[str, dict[str, str]]] = []
    buf = ""

    def declare(raw: str) -> None:
        if stack and ":" in raw:
            prop, value = raw.split(":", 1)
            stack[-1][1][prop.strip()] = " ".join(value.split()).removesuffix(" !important")

    for ch in text:
        if ch == "{":
            stack.append((" ".join(buf.split()), {}))
            buf = ""
        elif ch == ";":
            declare(buf)
            buf = ""
        elif ch == "}":
            declare(buf)
            buf = ""
            prelude, decls = stack.pop()
            if not prelude.startswith("@"):
                ctx = tuple(p for p, _ in stack)
                selectors = tuple(s.strip() for s in prelude.split(","))
                out.append((ctx, selectors, decls))
        else:
            buf += ch
    return tuple(out)


def _declarations(path: Path, selector: str, within: str | None) -> dict[str, str] | None:
    """Merged declarations of every rule listing ``selector`` in the given context.

    ``within=None`` means outside any @media; otherwise an enclosing at-rule
    prelude must contain ``within``.
    """
    merged: dict[str, str] | None = None
    for ctx, selectors, decls in _rules(path):
        in_media = any(p.startswith("@media") for p in ctx)
        if within is None and in_media:
            continue
        if within is not None and not any(within in p for p in ctx):
            continue
        if selector in selectors:
            merged = {**(merged or {}), **decls}
    return merged


_TOUCH = {"min-height": "var(--dz-touch-target-min)", "min-width": "var(--dz-touch-target-min)"}
_ARTICLE = [f".dz-section-markdown {t}" for t in ("h1", "h2", "h3", "h4", "p")] + [
    f".dz-section .prose {t}" for t in ("h1", "h2", "h3", "h4", "p")
]

# (id, file, selector, within at-rule, required declarations, forbidden declarations)
_RULE_PINS: list[tuple[str, Path, str, str | None, dict[str, object], dict[str, str]]] = [
    (
        "form-input-fits-line-box-930",
        COMPONENTS / "form.css",
        ".dz-form-input",
        None,
        {"min-height": "2.5rem", "line-height": "1.4", "padding-block": ANY},
        {"height": "2rem"},
    ),
    (
        "form-select-flat-chrome-930",
        COMPONENTS / "form.css",
        "select.dz-form-input",
        None,
        {"appearance": "none"},
        {},
    ),
    (
        "money-prefix-matches-input-930",
        COMPONENTS / "form.css",
        ".dz-form-money-prefix",
        None,
        {"min-height": "2.5rem"},
        {},
    ),
    (
        "money-select-matches-input-930",
        COMPONENTS / "form.css",
        ".dz-form-money-select",
        None,
        {"min-height": "2.5rem", "line-height": "1.4", "appearance": "none"},
        {},
    ),
    (
        "queue-filter-select-not-short-native-chrome",
        COMPONENTS / "queue.css",
        ".dz-queue-filter-select",
        None,
        {"appearance": "none", "line-height": "1.4", "padding-block": ANY},
        {"height": "1.75rem"},
    ),
    (
        "list-filter-select-pins-webkit-height",
        COMPONENTS / "table.css",
        "select.dz-filter-select",
        None,
        {"appearance": "none", "height": "2rem"},
        {},
    ),
    (
        "context-select-flat-chrome",
        COMPONENTS / "workspace-shell.css",
        ".dz-workspace-context-select",
        None,
        {"appearance": "none", "height": "2rem"},
        {},
    ),
    (
        "workspace-heading-wraps-985",
        COMPONENTS / "workspace-shell.css",
        ".dz-workspace-heading",
        None,
        {"flex-wrap": "wrap"},
        {},
    ),
    (
        "primary-actions-wrap-right-985",
        COMPONENTS / "workspace-shell.css",
        ".dz-workspace-primary-actions",
        None,
        {"flex-wrap": "wrap", "justify-content": "flex-end"},
        {},
    ),
    (
        "sidebar-panel-scrolls-itself-1596",
        COMPONENTS / "app-shell.css",
        ".dz-sidebar",
        None,
        {"position": "fixed", "overflow-y": "auto", "overscroll-behavior": "contain"},
        {},
    ),
    (
        "sidebar-header-sticky-1596",
        COMPONENTS / "app-shell.css",
        ".dz-sidebar__header",
        None,
        {"position": "sticky"},
        {},
    ),
    (
        "section-headline-stays-centred-921",
        COMPONENTS / "sitespec.css",
        ".dz-section h2",
        None,
        {"text-align": "center"},
        {},
    ),
    *[
        (
            f"article-{sel.split()[-2].lstrip('.')}-{sel.split()[-1]}-starts-921",
            COMPONENTS / "sitespec.css",
            sel,
            None,
            {"text-align": "start"},
            {},
        )
        for sel in _ARTICLE
    ],
    *[
        (
            f"article-h2-body-size-{i}-921",
            COMPONENTS / "sitespec.css",
            sel,
            None,
            {"font-size": "var(--text-xl)"},
            {},
        )
        for i, sel in enumerate((".dz-section-markdown h2", ".dz-section .prose h2"))
    ],
    (
        "section-h2-mobile-size-921",
        COMPONENTS / "sitespec.css",
        ".dz-section h2",
        "max-width: 768px",
        {"font-size": "var(--text-2xl)"},
        {},
    ),
    *[
        (
            f"article-h2-mobile-override-{i}-921",
            COMPONENTS / "sitespec.css",
            sel,
            "max-width: 768px",
            {"font-size": ANY},
            {},
        )
        for i, sel in enumerate((".dz-section-markdown h2", ".dz-section .prose h2"))
    ],
    *[
        (
            f"touch-target{sel.replace('.', '-')}-958",
            COMPONENTS / "touch-targets.css",
            sel,
            "pointer: coarse",
            _TOUCH,
            {},
        )
        for sel in (
            ".dz-button",
            ".dz-icon-button",
            ".dz-card-action-button",
            ".dz-list-csv-button",
            ".dz-sidebar-action-button",
            ".dz-add-card-button",
            ".dz-drawer__close",
            ".dz-pdf-viewer-help-close",
            ".dz-pdf-viewer-panel-close",
        )
    ],
    (
        "touch-target-bare-button-958",
        COMPONENTS / "touch-targets.css",
        "button",
        "pointer: coarse",
        {"min-height": "var(--dz-touch-target-min)"},
        {},
    ),
    (
        "reduced-motion-collapses-animation-960",
        TOKENS,
        '[style*="animation"]',
        "prefers-reduced-motion: reduce",
        {"animation-duration": "0.01ms"},
        {},
    ),
    *[
        (
            f"steps-equal-columns{sel.replace('.', '-')}-1590",
            COMPONENTS / "sitespec.css",
            sel,
            "min-width: 1024px",
            {"flex": "1 1 0"},
            {},
        )
        for sel in (".dz-step-item", ".dz-step-item.is-not-last")
    ],
    (
        "step-connector-out-of-flow-1590",
        COMPONENTS / "sitespec.css",
        ".dz-step-item.is-not-last .dz-step-connector",
        "min-width: 1024px",
        {"position": "absolute"},
        {"flex": "1"},
    ),
    (
        "step-connector-not-a-flex-crusher-1590",
        COMPONENTS / "sitespec.css",
        ".dz-step-connector",
        None,
        {},
        {"flex": "1"},
    ),
    (
        "site-nav-items-wrap-1591",
        COMPONENTS / "sitespec.css",
        ".dz-nav-items",
        None,
        {"flex-wrap": "wrap"},
        {},
    ),
    (
        "site-nav-never-wider-than-viewport-1591",
        COMPONENTS / "sitespec.css",
        ".dz-site-nav",
        None,
        {"max-width": "min(72rem, 100%)"},
        {},
    ),
    (
        "site-nav-wraps-narrow-1591",
        COMPONENTS / "sitespec.css",
        ".dz-site-nav",
        "max-width: 767px",
        {"flex-wrap": "wrap"},
        {},
    ),
]


@pytest.mark.parametrize(
    ("path", "selector", "within", "required", "forbidden"),
    [pytest.param(*row[1:], id=row[0]) for row in _RULE_PINS],
)
def test_rule_declares(
    path: Path,
    selector: str,
    within: str | None,
    required: dict[str, object],
    forbidden: dict[str, str],
) -> None:
    decls = _declarations(path, selector, within)
    assert decls is not None, f"no {selector!r} rule in {path.name} (within {within!r})"
    for prop, value in required.items():
        assert prop in decls, f"{selector} lost `{prop}`"
        if value is not ANY:
            assert decls[prop] == value, f"{selector} {prop}: {decls[prop]!r} != {value!r}"
    for prop, value in forbidden.items():
        assert decls.get(prop) != value, f"{selector} regressed to `{prop}: {value}`"


# Selectors that must not come back.
_RETIRED_SELECTORS = (
    re.compile(r"\.dz-row(?![\w-])"),  # L2: Row emits the cluster Hyperpart
    re.compile(r"\.dz-row--"),
    re.compile(r"\.dz-stack--gap-"),  # L2: data-dz-gap replaced the modifier scale
    # #1450: `~ tbody` never matched (tbody is inside the preceding grid), so
    # the empty state showed on every populated list.
    re.compile(re.escape(":has(~ tbody tr[data-dz-row-id])")),
    # #977 / #1001: Quill was removed; its `.ql-*` theme overrides and the vendor
    # import outlived it and 404'd on every rich_text page.
    re.compile(r"\.ql-"),
    re.compile(r"quill", re.IGNORECASE),
)
_TABLE_EMPTY_GUARD = ".dz-table-grid:not(:has(tbody tr td)) ~ .dz-table-empty"


# Classes and selectors the renderer emits; each needs a rule somewhere in the
# bundled sources (build_dist.py concatenates them, so source = bundle).
_RENDERED_SELECTORS: tuple[str, ...] = (
    # Fragment primitives (Surface, Heading, Region, Text, Table, forms, RefPicker)
    ".dz-surface",
    ".dz-surface__header",
    ".dz-surface__body",
    ".dz-heading",
    ".dz-heading--level-1",
    ".dz-region",
    ".dz-region--kind-list",
    ".dz-region--kind-detail",
    ".dz-region--kind-related",
    ".dz-region--kind-form",
    ".dz-text",
    ".dz-text--tone-default",
    ".dz-table",
    ".dz-form-stack",
    ".dz-field",
    ".dz-combobox",
    ".dz-submit",
    ".dz-ref-picker",
    ".dz-ref-picker__label",
    ".dz-ref-picker__select",
    # Page / AppShell / Sidebar / Topbar / SkipLink / ErrorPage (P17)
    ".dz-page",
    ".dz-app-sidebar",
    ".dz-app-header",
    ".dz-app-main",
    ".dz-app-footer",
    ".dz-sidebar",
    ".dz-sidebar__header",
    ".dz-sidebar__items",
    ".dz-nav-item",
    ".dz-nav-link",
    ".dz-nav-group",
    ".dz-nav-group__header",
    ".dz-nav-group__items",
    ".dz-topbar",
    ".dz-topbar-leading",
    ".dz-topbar-title",
    ".dz-topbar-title-text",
    ".dz-topbar-trailing",
    ".dz-skip-link",
    ".dz-error-page",
    ".dz-error-page__code",
    ".dz-error-page__message",
    ".dz-error-page__action",
    # Layout Hyperparts (#1079): stack gaps, cluster alignment, grid columns
    ".dz-stack",
    *(f'.dz-stack[data-dz-gap="{g}"]' for g in ("none", "xs", "sm", "md", "lg", "xl")),
    ".dz-cluster",
    *(f'.dz-cluster[data-dz-align="{a}"]' for a in ("start", "end", "baseline", "stretch")),
    ".dz-grid",
    *(f".dz-grid--columns-{n}" for n in range(1, 13)),
    # Bare-Page error views (#1081)
    ".dz-page > .dz-stack:only-child",
    # List empty state keyed off the grid sibling (#1450)
    _TABLE_EMPTY_GUARD,
    # Site theme toggle + dark-mode site sections (#26)
    ".dz-theme-toggle",
    ".dz-theme-toggle:hover",
    ".dz-theme-toggle__icon",
    ".dz-theme-toggle__sun",
    ".dz-theme-toggle__moon",
    '[data-theme="dark"] .dz-section-features',
    '[data-theme="dark"] .dz-section-pricing',
    '[data-theme="dark"] .dz-section-faq',
    '[data-theme="dark"] .dz-section-testimonials',
    '[data-theme="dark"] .dz-feature-item',
    '[data-theme="dark"] .dz-testimonial-item',
)


def _sheets() -> list[Path]:
    return [
        p
        for p in sorted({*DAZZLE_CSS.rglob("*.css"), *HM.rglob("*.css")})
        if "node_modules" not in p.parts and "tests" not in p.parts
    ]


@cache
def _all_selectors() -> frozenset[str]:
    return frozenset(
        sel for path in _sheets() for _ctx, selectors, _decls in _rules(path) for sel in selectors
    )


def _has_rule(selector: str, selectors: frozenset[str]) -> bool:
    if selector in selectors:
        return True
    # a class may also be styled as part of a compound selector
    pattern = re.compile(rf"{re.escape(selector)}(?![\w-])")
    return selector.startswith(".") and any(pattern.search(s) for s in selectors)


@pytest.mark.parametrize("selector", _RENDERED_SELECTORS)
def test_rendered_selector_has_a_rule(selector: str) -> None:
    assert _has_rule(selector, _all_selectors()), f"{selector!r} is emitted but has no CSS rule"


def test_retired_selectors_stay_gone_from_sources_and_bundle() -> None:
    bundle = DIST_CSS.read_text(encoding="utf-8")
    sources = [_COMMENT.sub("", p.read_text(encoding="utf-8")) for p in _sheets()]
    back = sorted(
        s[:80]
        for s in [*_all_selectors(), *sources, _COMMENT.sub("", bundle)]
        for r in _RETIRED_SELECTORS
        if r.search(s)
    )
    assert not back, f"retired selectors are back: {[b[:80] for b in back]}"
    # #1450: the fixed empty-state guard is what the served bundle carries.
    assert _TABLE_EMPTY_GUARD in bundle


def test_touch_target_token_is_at_least_44px_and_bundled() -> None:
    root = _declarations(TOKENS, ":root", None)
    assert root is not None
    token = root.get("--dz-touch-target-min", "")
    assert token.endswith("px") and int(token.removesuffix("px")) >= 44, token
    bundle = DIST_CSS.read_text(encoding="utf-8")
    assert "--dz-touch-target-min" in bundle
    assert "pointer:coarse" in bundle.replace(" ", "")


_ANIMATION_TOKENS = (
    *(f"--ease-spring-{n}" for n in range(1, 6)),
    *(f"--ease-elastic-{n}" for n in range(1, 4)),
    *(
        f"--animation-{name}"
        for name in (
            "fade-in",
            "fade-out",
            "scale-up",
            "scale-down",
            "slide-in-up",
            "slide-in-down",
            "slide-in-left",
            "slide-in-right",
            "slide-out-up",
            "slide-out-down",
            "slide-out-left",
            "slide-out-right",
            "shake-x",
            "pulse",
        )
    ),
)


def test_animation_tokens_resolve_to_defined_keyframes() -> None:
    """#960: consumers use var(--animation-*); each must name a defined @keyframes."""
    root = _declarations(TOKENS, ":root", None) or {}
    missing = [t for t in _ANIMATION_TOKENS if t not in root]
    assert not missing, f"tokens.css lost {missing}"
    keyframes = set(re.findall(r"@keyframes\s+([\w-]+)", TOKENS.read_text(encoding="utf-8")))
    unresolved = {
        token: value.split()[0]
        for token, value in root.items()
        if token.startswith("--animation-") and value.split()[0] not in keyframes
    }
    assert not unresolved, f"animation tokens naming undefined keyframes: {unresolved}"


def test_no_comment_bombs_in_dazzle_css() -> None:
    """A `*/` inside a comment ends it early; the leaked prose swallows the next
    rule in the bundle (ate the command palette, .dz-auth-page, the spinner).
    HaTchi-MaXchi's own sheets carry the same gate in its package tests."""
    problems: list[str] = []
    sheets = [p for p in sorted(DAZZLE_CSS.rglob("*.css")) if not {"dist", "vendor"} & set(p.parts)]
    assert sheets
    for path in sheets:
        residue = _COMMENT.sub("", path.read_text(encoding="utf-8"))
        rel = path.relative_to(DAZZLE_CSS)
        if "*/" in residue:
            problems.append(f"{rel}: stray '*/' outside any comment")
        if residue.count("{") != residue.count("}"):
            problems.append(f"{rel}: unbalanced braces")
    assert not problems, "\n  ".join(["CSS comment-bomb failures:", *problems])
