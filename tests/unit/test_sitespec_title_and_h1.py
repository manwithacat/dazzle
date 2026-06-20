"""Regression gates for sitespec title + heading fixes.

- **#1107** — ``PageContext.app_name`` lookup probes ``product_name``
  (the actual field on ``SitePageContext``) before falling back to
  ``app_name``/``"Dazzle"``. Without the probe, every sitespec page
  title rendered as ``"<page> — Dazzle"`` regardless of the product
  name set in the spec.

- **#1108** — pages without a ``type: hero`` section auto-inject an
  ``<h1>`` from ``page.title``. Pages that DO have a hero stay
  untouched (hero owns the h1 already, and a second one would
  violate the single-h1 WCAG rule).

The fixes live in
``src/dazzle/http/runtime/site_routes.py::_render_site_inner_html``
and the surrounding ``PageContext`` build site, both inside the
``build_pages_router`` closure. The cleanest test is a content gate
on the source — the refactor to expose the function as module-level
is intentionally not in scope here.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITE_ROUTES = ROOT / "src" / "dazzle" / "http" / "runtime" / "site_routes.py"


def test_app_name_probes_product_name_before_dazzle_fallback() -> None:
    """#1107: app_name now reads product_name (then app_name, then 'Dazzle')."""
    text = SITE_ROUTES.read_text()
    # The lookup chain must mention product_name first.
    assert 'getattr(ctx, "product_name"' in text, (
        "site_routes.py must probe ctx.product_name when building "
        "PageContext.app_name (#1107) — sitespec SitePageContext "
        "exposes `product_name`, not `app_name`."
    )
    # Both later fallbacks remain.
    assert 'getattr(ctx, "app_name"' in text
    assert '"Dazzle"' in text


def test_inner_html_auto_injects_page_h1_when_no_hero() -> None:
    """#1108: pages without a hero section get an auto-injected page-title h1."""
    text = SITE_ROUTES.read_text()
    # The hero-detection comment / loop must be present in the inner builder.
    assert "Page <h1> (#1108)" in text, (
        "_render_site_inner_html must inject a page-title <h1> when no "
        "section.type == 'hero' is present (#1108)."
    )
    # The injection must use the dz-page-title class for downstream styling.
    assert '<h1 class="dz-page-title">' in text


def test_inner_html_does_not_inject_h1_when_hero_present() -> None:
    """The injection is gated on `has_hero`: hero pages skip the auto-h1."""
    text = SITE_ROUTES.read_text()
    # The gating variable must exist and the injected fragment must use it.
    assert "has_hero" in text
    # The page_h1_html must be empty-string by default and only set when not has_hero.
    assert "if not has_hero" in text
    assert 'page_h1_html = ""' in text


def test_h1_threaded_into_main_html_before_sections() -> None:
    """The injected <h1> renders before sections inside <main>, not after."""
    text = SITE_ROUTES.read_text()
    # The main_html f-string must include `{page_h1_html}{sections_html}` in that order.
    assert "{page_h1_html}{sections_html}" in text, (
        "main_html must render the auto-injected h1 BEFORE sections so it "
        "stays the first heading on the page."
    )


def test_has_hero_detects_pretransformed_typed_marker() -> None:
    """#1261: `has_hero` must also accept the `_typed` marker that
    `_render_site_page_chromed` substitutes in for typed hero sections
    before `_render_site_inner_html` runs. Without this, every page
    with a typed hero gets a duplicate `dz-page-title` h1 injected
    on top of the hero's own h1 — the #1108 regression.
    """
    text = SITE_ROUTES.read_text()
    # The marker dict must carry `_original_type` so the inner builder
    # can still classify the section as a hero post-transform.
    assert '"_original_type": section_type' in text, (
        "_render_site_page_chromed must include `_original_type` on the "
        "`_typed` marker dict so the downstream has_hero check survives "
        "the section transform (#1261)."
    )
    # The has_hero predicate must check the transformed marker form too.
    assert '"_original_type"' in text and "_typed" in text
    # The #1261 anchor comment must be present so the gate is greppable.
    assert "#1261" in text
