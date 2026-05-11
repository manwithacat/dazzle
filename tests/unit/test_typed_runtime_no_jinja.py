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

_ROOT = Path(__file__).resolve().parents[2]

# Modules that completed the migration. Each entry MUST NOT contain
# `import jinja2`, `from jinja2`, `render_site_page`, or `render_fragment`.
_TYPED_ONLY_MODULES = (
    "src/dazzle/documents/__init__.py",
    "src/dazzle/documents/api.py",
    "src/dazzle_back/runtime/app_error_views.py",
    "src/dazzle_back/runtime/auth/auth_views.py",
    "src/dazzle_back/runtime/auth/magic_link_routes.py",
    "src/dazzle_back/runtime/auth/mailer.py",
    "src/dazzle_back/runtime/auth/password_login_routes.py",
    "src/dazzle_back/runtime/auth/password_reset_routes.py",
    "src/dazzle_back/runtime/auth/sso_config.py",
    "src/dazzle_back/runtime/auth/sso_routes.py",
    "src/dazzle_back/runtime/auth/sso_views.py",
    "src/dazzle_back/runtime/auth/two_factor_form_routes.py",
    "src/dazzle_back/runtime/auth/two_factor_views.py",
    "src/dazzle_back/runtime/error_views.py",
    # Phase 4 app-shell completion (v0.67.55–v0.67.57):
    "src/dazzle_back/runtime/exception_handlers.py",
    "src/dazzle_back/runtime/renderers/page_builder.py",
    "src/dazzle_back/runtime/shell.py",
    "src/dazzle_ui/runtime/page_routes.py",
    "src/dazzle_ui/runtime/workspace_renderer.py",
    # v0.67.58 — audit-history detail-page render inlined via html.escape.
    "src/dazzle_back/runtime/audit_region.py",
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
    auth_dir = _ROOT / "src" / "dazzle_ui" / "templates" / "site" / "auth"
    assert not auth_dir.exists(), (
        f"site/auth/ Jinja template directory has reappeared at {auth_dir}. "
        "The auth Jinja retirement (Phases 1.A–1.D.2) deliberately emptied "
        "this directory. New auth surfaces must be typed-Fragment views in "
        "`dazzle_back.runtime.auth.auth_views` or `two_factor_views`."
    )


def test_legacy_auth_context_builders_are_retired() -> None:
    """`build_site_auth_context`, `build_site_404_context`, and
    `build_site_error_context` were retired across Phases 1.D.2,
    2.A. Re-introducing them in `site_context.py` would mean someone
    rebuilt the legacy Jinja path."""
    src = (_ROOT / "src" / "dazzle_ui" / "runtime" / "site_context.py").read_text()
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
    reappear under `src/dazzle_ui/templates/`."""
    templates_root = _ROOT / "src" / "dazzle_ui" / "templates"
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
