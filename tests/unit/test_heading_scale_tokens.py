"""Tests for #983 — heading scale tokens + page-title landmark.

Pre-#983 the three rendering paths (workspace shell, list view,
marketing) hardcoded their own font-sizes — there was no
heading-scale token layer adopters could reason about. Cycle 1
(this release) adds:

- `--dz-heading-app-{page-title,section-title,subsection-title}`
  tokens in tokens.css for the app shell.
- `--dz-heading-marketing-{hero,cta,section}` tokens (mirror the
  existing site-section variables defined in design-system.css).
- `--dz-font-size-cta-headline` defined canonically in
  design-system.css (was previously only an inline fallback in
  site-sections.css).
- Promoted `.dz-workspace-title` and `.dz-table-title` to consume
  the canonical app page-title token (visible bump for the table
  title from --text-base to --text-lg so workspace + list-page
  share the same emphasis).
- Added a `visually-hidden` h1 landmark in filterable_table.html
  so screenreaders see a proper page title on list views.

Approach 1 from the issue: token-first, two scales, additive.
Approach 2 (collapse marketing into the app's compact scale) is
intentionally deferred.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CSS_ROOT = Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/css"
TOKENS_CSS = CSS_ROOT / "tokens.css"
DESIGN_SYSTEM_CSS = CSS_ROOT / "design-system.css"
DASHBOARD_CSS = CSS_ROOT / "components/dashboard.css"
TABLE_CSS = CSS_ROOT / "components/table.css"
FILTERABLE_TABLE = (
    Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/components/filterable_table.html"
)


@pytest.fixture(scope="module")
def tokens_css() -> str:
    return TOKENS_CSS.read_text()


@pytest.fixture(scope="module")
def design_system_css() -> str:
    return DESIGN_SYSTEM_CSS.read_text()


@pytest.fixture(scope="module")
def dashboard_css() -> str:
    return DASHBOARD_CSS.read_text()


@pytest.fixture(scope="module")
def table_css() -> str:
    return TABLE_CSS.read_text()


@pytest.fixture(scope="module")
def filterable_table() -> str:
    return FILTERABLE_TABLE.read_text()


# ---------------------------------------------------------------------------
# Token presence
# ---------------------------------------------------------------------------


APP_TOKENS = [
    "--dz-heading-app-page-title",
    "--dz-heading-app-section-title",
    "--dz-heading-app-subsection-title",
]


@pytest.mark.parametrize("name", APP_TOKENS)
def test_app_heading_token_present(tokens_css: str, name: str) -> None:
    """Each app heading slot must declare a value in tokens.css.
    Drift here = a heading-using component reverts to hardcoded
    font-sizes."""
    assert f"{name}:" in tokens_css


MARKETING_TOKENS = [
    "--dz-heading-marketing-hero",
    "--dz-heading-marketing-cta",
    "--dz-heading-marketing-section",
]


@pytest.mark.parametrize("name", MARKETING_TOKENS)
def test_marketing_heading_token_present(tokens_css: str, name: str) -> None:
    """Marketing tokens mirror the site-section variables for
    discoverability — adopters scanning tokens.css see the full
    heading scale in one place."""
    assert f"{name}:" in tokens_css


def test_cta_headline_canonically_defined(design_system_css: str) -> None:
    """`--dz-font-size-cta-headline` was an inline fallback in
    site-sections.css. Cycle adds a canonical declaration in
    design-system.css alongside hero / section."""
    assert "--dz-font-size-cta-headline:" in design_system_css


# ---------------------------------------------------------------------------
# Component CSS consumes tokens
# ---------------------------------------------------------------------------


def test_workspace_title_uses_token(dashboard_css: str) -> None:
    """`.dz-workspace-title` must consume `--dz-heading-app-page-title`,
    not the underlying `--text-lg`. Pre-#983 it was hardcoded."""
    # Widen the window to comfortably cover the comment + the rule body.
    idx = dashboard_css.find(".dz-workspace-title")
    assert idx != -1
    block = dashboard_css[idx : idx + 800]
    assert "var(--dz-heading-app-page-title)" in block


def test_table_title_uses_token(table_css: str) -> None:
    """`.dz-table-title` was `--text-base`; promoting to the
    canonical app page-title token lifts list-page titles to the
    same scale as workspace titles. Visible 16px → 18px bump."""
    idx = table_css.find(".dz-table-title")
    assert idx != -1
    block = table_css[idx : idx + 800]
    assert "var(--dz-heading-app-page-title)" in block


# ---------------------------------------------------------------------------
# Page-title landmark
# ---------------------------------------------------------------------------


def test_filterable_table_emits_h1_landmark(filterable_table: str) -> None:
    """Pre-#983 the table emitted only h2 — no h1 in the document
    accessibility tree on list pages. Add a visually-hidden h1 so
    screenreaders have a page-title anchor."""
    assert '<h1 class="dz-page-title visually-hidden"' in filterable_table


def test_landmark_gated_on_page_title_present(filterable_table: str) -> None:
    """Don't emit an empty h1 when the parent didn't supply one —
    `{% if page_title %}` guard."""
    # Find the h1 emission
    h1_idx = filterable_table.find("dz-page-title visually-hidden")
    assert h1_idx != -1
    # Walk back ~150 chars to find the gating `{% if page_title %}`
    block = filterable_table[max(0, h1_idx - 200) : h1_idx]
    assert "{% if page_title %}" in block


def test_visible_h2_table_title_unchanged(filterable_table: str) -> None:
    """The visible h2 stays — promoting it to h1 would conflict
    with the workspace shell h1 on dashboard pages where a list
    sits inside the dashboard. The cycle-1 design keeps h2 visible
    + adds an invisible h1 for accessibility-tree completeness."""
    assert '<h2 class="dz-table-title">{{ table.title }}</h2>' in filterable_table


# ---------------------------------------------------------------------------
# Token resolution chain — values are sane
# ---------------------------------------------------------------------------


def test_app_page_title_resolves_to_text_lg(tokens_css: str) -> None:
    """The app page-title scale is `--text-lg` — preserves the
    pre-#983 workspace title size while giving it a name. A
    refactor that points it at a different size should fail this
    test as a forcing function to think about the visual impact."""
    idx = tokens_css.find("--dz-heading-app-page-title:")
    assert idx != -1
    line_end = tokens_css.find("\n", idx)
    line = tokens_css[idx:line_end]
    assert "var(--text-lg)" in line


def test_marketing_hero_resolves_to_existing_var_with_fallback(
    tokens_css: str,
) -> None:
    """Marketing hero token must reference the existing
    `--dz-font-size-hero-headline` var (defined in design-system.css)
    so the visible size stays the same."""
    idx = tokens_css.find("--dz-heading-marketing-hero:")
    assert idx != -1
    line_end = tokens_css.find("\n", idx)
    line = tokens_css[idx:line_end]
    assert "--dz-font-size-hero-headline" in line


# ---------------------------------------------------------------------------
# Bundle inclusion
# ---------------------------------------------------------------------------


def test_tokens_in_dist_bundle() -> None:
    dist_css = (
        Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/dist/dazzle.min.css"
    )
    if not dist_css.is_file():
        pytest.skip("dist not built")
    text = dist_css.read_text()
    for name in APP_TOKENS + MARKETING_TOKENS:
        assert name in text
