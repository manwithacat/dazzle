"""Page-route coverage lint — prevents page templates shipping without routes.

Cycle 306 — implements Track B from cycle 305's template-ship-without-wiring
gap doc. Parallel to cycle 302's orphan_lint_rule but with a narrower
semantic: every **page-like template** must have a corresponding
server-route that serves it via `render_site_page()`.

Why this matters beyond orphan_lint: a page template could be referenced
somewhere (e.g. in an old include that's no longer reachable, or in a
docstring example) and pass the orphan scan — but still be unreachable
to end users because no URL route serves it. EX-055 (cycle 302/303)
found `site/auth/2fa_*.html` in this state: templates EXIST, cycle 298
contract tests pass (source-level assertions), but no `render_site_page`
call serves them.

Scope: only `site/auth/` family for v1 — the original EX-055 site. Can
be extended to `site/`, `app/` top-level, etc. in future cycles if the
pattern proves valuable.

Convention: a template is page-like if (a) it lives under a
PAGE_FAMILY_DIRS prefix AND (b) its filename does not start with `_`
(underscore-prefixed files are partials, scripts, or shared fragments).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "src" / "dazzle_ui" / "templates"
DAZZLE_BACK_ROOT = REPO_ROOT / "src" / "dazzle_back"
DAZZLE_UI_ROOT = REPO_ROOT / "src" / "dazzle_ui"

# Directories whose non-underscore templates are expected to be served by
# a Python page route. Started with `site/auth/` (cycle 306) — the family
# where EX-055 surfaced. Cycle 307 added `app/` once the regex was
# broadened to recognise `_render_app_shell_error(template_name=)`.
#
# NOT including `site/` top-level because:
# - site_base.html is a layout (extended, not served)
# - site/sections/ and site/includes/ are dynamic-loaded fragments
# - the top-level pages (page.html, 403, 404) ARE served but adding
#   `site/` as a prefix would sweep in the subdirectories above
# If we want to cover those individually, add them to a separate
# INDIVIDUAL_REQUIRED list in a future cycle.
PAGE_FAMILY_DIRS: tuple[str, ...] = ("site/auth/", "app/")

# Page templates that genuinely should NOT be served by a page route
# (e.g. the template is consumed by a different mechanism, or the
# feature is pending a separate triage). Each entry requires a reason.
INDIVIDUAL_ALLOWLIST: dict[str, str] = {
    # 2FA pages — templates ship but no page route exists. Filed as
    # EX-055 (cycle 302/303) → #831. Kept allowlisted here so this lint
    # passes while the framework bug is triaged. Remove when #831 lands.
    "site/auth/2fa_challenge.html": "EX-055 → #831; 2FA UI feature half-shipped",
    "site/auth/2fa_setup.html": "EX-055 → #831; 2FA UI feature half-shipped",
    "site/auth/2fa_settings.html": "EX-055 → #831; 2FA UI feature half-shipped",
}

# Render-call patterns. Each matches a known way the runtime serves a
# page template as an HTML response. Extend when new render helpers land.
_RENDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    # `render_site_page("<path>", ...)` — marketing + auth pages (site_routes.py)
    re.compile(r'render_site_page\(\s*["\']([^"\']+)["\']'),
    # `_render_app_shell_error(template_name="<path>", ...)` — app error pages
    # (exception_handlers.py). The regex allows arbitrary preceding kwargs
    # by matching `template_name=` anywhere inside the call's parentheses.
    re.compile(
        r'_render_app_shell_error\([^)]*?template_name\s*=\s*["\']([^"\']+)["\']', re.DOTALL
    ),
)


def _collect_page_templates() -> set[str]:
    """Every non-underscore .html file under a PAGE_FAMILY_DIRS prefix."""
    pages: set[str] = set()
    for p in TEMPLATES_ROOT.rglob("*.html"):
        rel = p.relative_to(TEMPLATES_ROOT).as_posix()
        if not any(rel.startswith(prefix) for prefix in PAGE_FAMILY_DIRS):
            continue
        if p.name.startswith("_"):
            continue  # partial / script / shared fragment
        pages.add(rel)
    return pages


def _collect_rendered_pages() -> set[str]:
    """Extract every template path passed to a known render-helper in Python."""
    rendered: set[str] = set()
    for root in (DAZZLE_BACK_ROOT, DAZZLE_UI_ROOT):
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            text = p.read_text()
            for pattern in _RENDER_PATTERNS:
                for m in pattern.finditer(text):
                    rendered.add(m.group(1))
    return rendered


def _compute_unserved_pages() -> set[str]:
    return _collect_page_templates() - _collect_rendered_pages()


class TestPageRouteCoverage:
    """Every page template under PAGE_FAMILY_DIRS must be served by a route.

    Surfaces EX-055-class bugs at test-time — templates that ship with
    full styling + cycle-298-style source-level test coverage but zero
    server-side glue to reach them.
    """

    def test_every_page_template_is_served(self) -> None:
        """Surface page templates with no corresponding route."""
        unserved = _compute_unserved_pages()
        unallowed = unserved - INDIVIDUAL_ALLOWLIST.keys()
        assert not unallowed, (
            "\n\nPage template(s) under PAGE_FAMILY_DIRS with no "
            "render_site_page() call serving them:\n"
            + "\n".join(f"  - {t}" for t in sorted(unallowed))
            + "\n\nEither wire a page route in "
            "src/dazzle_back/runtime/site_routes.py (or equivalent), "
            "OR add the template to INDIVIDUAL_ALLOWLIST with a reason "
            "citing a gap doc / EX row / GitHub issue."
        )

    def test_every_allowlist_entry_is_still_unserved(self) -> None:
        """Stale allowlist entries (template now served by route) must be removed."""
        unserved = _compute_unserved_pages()
        stale = INDIVIDUAL_ALLOWLIST.keys() - unserved
        assert not stale, (
            "\n\nAllowlist entries that are now served by a page route:\n"
            + "\n".join(f"  - {t}  # was: {INDIVIDUAL_ALLOWLIST[t]}" for t in sorted(stale))
            + "\n\nRemove these from INDIVIDUAL_ALLOWLIST — the route now exists."
        )

    def test_allowlist_entries_exist_as_templates(self) -> None:
        """Allowlist must point at real templates."""
        all_templates = {
            p.relative_to(TEMPLATES_ROOT).as_posix() for p in TEMPLATES_ROOT.rglob("*.html")
        }
        nonexistent = INDIVIDUAL_ALLOWLIST.keys() - all_templates
        assert not nonexistent, (
            "\n\nAllowlist entries that don't exist as templates:\n"
            + "\n".join(f"  - {t}" for t in sorted(nonexistent))
        )

    def test_allowlist_entries_are_in_page_families(self) -> None:
        """Allowlist must target templates in one of PAGE_FAMILY_DIRS.

        A template outside PAGE_FAMILY_DIRS doesn't need this lint — the
        orphan_lint or other coverage handles it. Stale allowlist entries
        (from a directory that used to be a page-family but no longer is)
        should be removed.
        """
        misplaced = {
            t
            for t in INDIVIDUAL_ALLOWLIST
            if not any(t.startswith(prefix) for prefix in PAGE_FAMILY_DIRS)
        }
        assert not misplaced, (
            f"\n\nAllowlist entries outside PAGE_FAMILY_DIRS={PAGE_FAMILY_DIRS}:\n"
            + "\n".join(f"  - {t}" for t in sorted(misplaced))
            + "\n\nThese don't belong in this lint's allowlist."
        )

    def test_every_allowlist_entry_has_reason(self) -> None:
        """Governance: reasons must cite evidence."""
        for path, reason in INDIVIDUAL_ALLOWLIST.items():
            assert reason.strip(), f"Empty reason for allowlist entry {path}"
            assert len(reason) > 15, (
                f"Reason for {path} is too short ({len(reason)} chars) — "
                f"cite a gap doc, EX row, GitHub issue, or cycle number"
            )

    def test_page_family_dirs_match_real_directories(self) -> None:
        """Guard against stale PAGE_FAMILY_DIRS entries."""
        all_templates = {
            p.relative_to(TEMPLATES_ROOT).as_posix() for p in TEMPLATES_ROOT.rglob("*.html")
        }
        for prefix in PAGE_FAMILY_DIRS:
            matching = [t for t in all_templates if t.startswith(prefix)]
            assert matching, (
                f"PAGE_FAMILY_DIRS[{prefix!r}] matches zero templates; remove it from the tuple."
            )


# Manual debugging helper
def print_coverage_report() -> None:
    """Print human-readable page-route-coverage report."""
    pages = _collect_page_templates()
    rendered = _collect_rendered_pages()
    unserved = _compute_unserved_pages()
    print(f"page templates under {PAGE_FAMILY_DIRS}: {len(pages)}")
    print(f"served by render_site_page: {len(pages & rendered)}")
    print(f"unserved: {len(unserved)}")
    if unserved:
        print("\nUnserved:")
        for t in sorted(unserved):
            allow = INDIVIDUAL_ALLOWLIST.get(t, "(NOT ALLOWLISTED)")
            print(f"  {t}  # {allow}")


if __name__ == "__main__":
    print_coverage_report()
