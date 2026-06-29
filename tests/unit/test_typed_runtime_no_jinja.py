"""Phase 5 prep (v0.67.38): CI gates that prevent Jinja2 regrowth in
runtime modules that completed the typed-Fragment migration.

These tests scan source files for `import jinja2` / `from jinja2` /
`render_site_page(...)` / `render_fragment(...)` patterns and fail if
they reappear in modules that should now be 100% typed-Fragment. They
complement (not replace) the broader test sweep — those tests assert
runtime behavior; these assert provenance.

If a check fails it means a regression has reintroduced Jinja2 in a
file that the retirement plan explicitly cleaned. Either:
  (a) revert the regression and stay on the typed substrate, or
  (b) deliberately downgrade and update this allow-list with a
      CHANGELOG entry under Removed/Changed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

_ROOT = Path(__file__).resolve().parents[2]

# Modules that completed the migration. Each entry MUST NOT contain
# `import jinja2`, `from jinja2`, `render_site_page`, or `render_fragment`.
_TYPED_ONLY_MODULES = (
    "src/dazzle/documents/__init__.py",
    "src/dazzle/documents/api.py",
    "src/dazzle/http/runtime/app_error_views.py",
    "src/dazzle/http/runtime/auth/auth_views.py",
    "src/dazzle/http/runtime/auth/magic_link_routes.py",
    "src/dazzle/http/runtime/auth/mailer.py",
    "src/dazzle/http/runtime/auth/password_login_routes.py",
    "src/dazzle/http/runtime/auth/password_reset_routes.py",
    "src/dazzle/http/runtime/auth/sso_config.py",
    "src/dazzle/http/runtime/auth/sso_routes.py",
    "src/dazzle/http/runtime/auth/sso_views.py",
    "src/dazzle/http/runtime/auth/two_factor_form_routes.py",
    "src/dazzle/http/runtime/auth/two_factor_views.py",
    "src/dazzle/http/runtime/error_views.py",
    # Phase 4 app-shell completion (v0.67.55–v0.67.57):
    "src/dazzle/http/runtime/exception_handlers.py",
    "src/dazzle/render/dispatch.py",  # was back/runtime/renderers/page_builder.py until #1094
    # `shell.py` and `render_in_app_shell` were retired entirely in v0.67.84
    # (closes #1040); the path is gone from disk.
    "src/dazzle/http/runtime/page_routes.py",
    "src/dazzle/page/runtime/workspace_renderer.py",
    # v0.67.58 — audit-history detail-page render inlined via html.escape.
    "src/dazzle/http/runtime/audit_region.py",
    # v0.67.59 — dual_path renderers retired (legacy templates gone).
    "src/dazzle/http/runtime/renderers/html_normalise.py",
    # legacy_ctx.py was retired entirely in v0.67.60 (dead code; tests
    # were the only consumer after v0.67.59 removed render_via_typed).
    # v0.67.61 — htmx_error_response inline-rendered (form_errors.html
    # template stays — Jinja `{% include %}` consumers in components/
    # form.html and experience/_content.html still use it).
    "src/dazzle/http/runtime/htmx.py",
    # v0.67.62 — htmx-fragment endpoints inline-render via html.escape.
    "src/dazzle/http/runtime/fragment_routes.py",
    "src/dazzle/http/runtime/fts_routes.py",
    # v0.67.65 — fragment_registry is a manifest table; rephrased
    # docstring to clear the gate's regex.
    "src/dazzle/page/runtime/fragment_registry.py",
    # v0.67.68 — route_generator detail-fields, table-pagination,
    # table-sentinel, table-empty, table-rows, and inline-edit all
    # now inline-render. The 3 list-fragment templates
    # (table_rows.html, table_pagination.html, table_sentinel.html)
    # are no longer reached from this code path.
    "src/dazzle/http/runtime/route_generator.py",
    # #1361 slice 2 — the inline HTMX/HTML renderers above were extracted
    # verbatim from route_generator.py; the gate must keep covering the
    # moved HTML.
    "src/dazzle/http/runtime/htmx_render.py",
    # #1361 slice 3 — audit context + auth wrapping extracted verbatim from
    # route_generator.py; keep the gate covering code that originated in a
    # covered file (no HTML here, cheap insurance).
    "src/dazzle/http/runtime/audit_wrap.py",
    # #1361 final slice — CRUD + graph handler factories extracted verbatim
    # from route_generator.py into handlers/. list_handlers carries the
    # inline HTMX error-row + pagination-OOB HTML; the other three have no
    # HTML but originated in a covered file (cheap insurance).
    "src/dazzle/http/runtime/handlers/__init__.py",
    "src/dazzle/http/runtime/handlers/graph_handlers.py",
    "src/dazzle/http/runtime/handlers/list_handlers.py",
    "src/dazzle/http/runtime/handlers/read_handlers.py",
    "src/dazzle/http/runtime/handlers/write_handlers.py",
    # v0.67.69 — marketing-page render fully Python-orchestrated.
    # inner_only.html + nav.html + footer.html + theme_toggle.html +
    # qa_personas.html + all 19 site/sections/*.html templates deleted.
    "src/dazzle/http/runtime/site_routes.py",
    # v0.67.70 — radar wired through typed primitive; AUDIT_HISTORY +
    # TAB_DATA fall through to typed shim (no DSL consumer, no adapter).
    # The render_fragment fallback path is gone.
    # v0.67.116 (#1057 cut 17): workspace_rendering.py was decomposed
    # across 17 cuts and the back-compat shim deleted. The typed-only
    # invariant now applies to every sibling module the handler delegates to.
    "src/dazzle/http/runtime/workspace_region_handler.py",
    "src/dazzle/http/runtime/workspace_region_prelude.py",
    "src/dazzle/http/runtime/workspace_region_fetch.py",
    "src/dazzle/http/runtime/workspace_region_orchestration.py",
    "src/dazzle/http/runtime/workspace_region_render.py",
    "src/dazzle/http/runtime/workspace_region_computes.py",
    "src/dazzle/http/runtime/workspace_aggregation.py",
    "src/dazzle/render/fragment/region/workspace_card_bodies.py",
    "src/dazzle/http/runtime/workspace_card_data.py",
    "src/dazzle/http/runtime/workspace_card_fetchers.py",
    "src/dazzle/http/runtime/workspace_columns.py",
    "src/dazzle/http/runtime/workspace_context.py",
    "src/dazzle/http/runtime/workspace_csv.py",
    "src/dazzle/http/runtime/workspace_handlers.py",
    "src/dazzle/http/runtime/workspace_scope.py",
    "src/dazzle/http/runtime/workspace_user.py",
    # v0.67.71 — experience-shell rendering owned by
    # `experience_renderer.render_experience_inner_html` (inline Python).
    "src/dazzle/http/runtime/experience_routes.py",
    # v0.67.74 — form_field/form_stepper/search_select inlined.
    "src/dazzle/page/runtime/form_renderer.py",
    # v0.67.75 — detail_view + related-* fragments inlined.
    "src/dazzle/page/runtime/detail_renderer.py",
    # v0.67.76 — filterable_table + search_input + filter_bar + bulk_actions
    # inlined; the whole module deleted in ADR-0049 (lists render via the
    # typed substrate now), so there is no file left to scan.
    # v0.67.71 — experience flow shell (form/detail/table dispatcher) is
    # now fully Python. Renamed file kept under the same path.
    "src/dazzle/page/runtime/experience_renderer.py",
    # v0.67.78 — journey_reporter inline-renders via html.escape (closes #1041).
    "src/dazzle/agent/journey_reporter.py",
    # v0.67.87 — agent_commands templates ported to Python f-strings (closes #1049).
    "src/dazzle/services/agent_commands/renderer.py",
    # v0.67.88 — llm_executor prompt rendering migrated to string.Template (closes #1048).
    "src/dazzle/http/runtime/llm_executor.py",
    # v0.67.92 — jinja2 dropped entirely (closes #1042/#1044). The
    # framework's last Jinja env users were retired here.
    "src/dazzle/core/expander.py",
    "src/dazzle/compliance/renderer.py",
    "src/dazzle/page/runtime/template_renderer.py",
    "src/dazzle/http/runtime/combined_server.py",
    "src/dazzle/page/runtime/hot_reload.py",
    "src/dazzle/http/runtime/subsystems/system_routes.py",
)

# Patterns that indicate Jinja2 use. Each is a regex matched against
# source-line content.
_JINJA_PATTERNS = (
    re.compile(r"^\s*import\s+jinja2\b"),
    re.compile(r"^\s*from\s+jinja2\b"),
    re.compile(r"\brender_site_page\("),
    re.compile(r"\brender_fragment\("),
)


def _scan_module(rel_path: str) -> list[tuple[int, str, str]]:
    """Return `[(lineno, pattern, line)]` for each Jinja2 hit in ``rel_path``."""
    path = _ROOT / rel_path
    assert path.is_file(), f"missing typed-only module: {rel_path}"
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        for pat in _JINJA_PATTERNS:
            if pat.search(line):
                hits.append((lineno, pat.pattern, line.strip()))
    return hits


def test_typed_only_modules_have_no_jinja2_imports() -> None:
    """Each migrated runtime module must stay free of Jinja2."""
    failures: list[str] = []
    for rel_path in _TYPED_ONLY_MODULES:
        for lineno, pattern, line in _scan_module(rel_path):
            failures.append(f"  {rel_path}:{lineno} matched {pattern!r}: {line}")
    if failures:
        raise AssertionError(
            "Jinja2 regrowth detected in typed-only runtime modules. "
            "These files completed the Phase 1/2 retirement and must "
            "stay on the typed-Fragment substrate:\n" + "\n".join(failures)
        )


def test_site_auth_template_dir_does_not_exist() -> None:
    """The `site/auth/` Jinja template directory was retired in
    Phase 1.D.2 (v0.67.37). Re-creating it would mean someone
    re-introduced a Jinja auth template — that's the regression
    this gate is designed to catch."""
    auth_dir = _ROOT / "src" / "dazzle" / "page" / "templates" / "site" / "auth"
    assert not auth_dir.exists(), (
        f"site/auth/ Jinja template directory has reappeared at {auth_dir}. "
        "The auth Jinja retirement (Phases 1.A–1.D.2) deliberately emptied "
        "this directory. New auth surfaces must be typed-Fragment views in "
        "`dazzle_http.runtime.auth.auth_views` or `two_factor_views`."
    )


def test_legacy_auth_context_builders_are_retired() -> None:
    """`build_site_auth_context`, `build_site_404_context`, and
    `build_site_error_context` were retired across Phases 1.D.2,
    2.A. Re-introducing them in `site_context.py` would mean someone
    rebuilt the legacy Jinja path."""
    src = (_ROOT / "src" / "dazzle" / "page" / "runtime" / "site_context.py").read_text()
    for legacy in (
        "def build_site_auth_context(",
        "def build_site_404_context(",
        "def build_site_error_context(",
    ):
        assert legacy not in src, (
            f"retired context builder reappeared: {legacy} in site_context.py. "
            "Auth + error coverage now lives in the typed-Fragment views; "
            "this builder shouldn't be needed."
        )


def test_retired_jinja_templates_stay_deleted() -> None:
    """The 13 templates deleted across Phases 1.A–2.A must not
    reappear under `src/dazzle/page/templates/`."""
    templates_root = _ROOT / "src" / "dazzle" / "page" / "templates"
    retired = (
        "site/auth/login.html",
        "site/auth/signup.html",
        "site/auth/forgot_password.html",
        "site/auth/reset_password.html",
        "site/auth/2fa_challenge.html",
        "site/auth/2fa_setup.html",
        "site/auth/2fa_settings.html",
        "site/auth/_auth_form_script.html",
        "site/auth/_forgot_password_script.html",
        "site/auth/_reset_password_script.html",
        "site/403.html",
        "site/404.html",
        "macros/auth_page_wrapper.html",
        # Phase 2.B full (v0.67.40):
        "app/403.html",
        "app/404.html",
        # Phase 4 chrome-flag flip (v0.67.43):
        "site/page.html",
    )
    failures: list[str] = []
    for rel in retired:
        if (templates_root / rel).exists():
            failures.append(rel)
    if failures:
        raise AssertionError(
            "Templates retired during Jinja2 retirement have reappeared:\n  "
            + "\n  ".join(failures)
            + "\nThese surfaces are typed-Fragment views now; rebuilding them "
            "as Jinja templates is a regression."
        )
