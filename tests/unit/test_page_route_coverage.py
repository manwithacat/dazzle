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

Coverage evolution:
- Cycle 306: `site/auth/` family only (EX-055 site, 7 templates)
- Cycle 307: added `app/` + 2nd render regex (`_render_app_shell_error`)
- Cycle 308: added `site/` top-level + layout-template detection so
  `site_base.html` is correctly excluded (it's extended by children,
  not served directly)
- Post-342: widened to `workspace/`, `experience/`, `reports/` top-level
  templates + added `render_fragment()` and `env.get_template(...)`
  render patterns (half-finished-internals shape #1 follow-up).

Convention: a template is page-like if ALL of:
(a) matches a `PAGE_TEMPLATE_PATTERNS` glob (Path.match: `*` doesn't cross `/`)
(b) filename does not start with `_` (underscore = partial / script / fragment)
(c) is NOT in `_collect_layout_templates()` (not extended by any other template)
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = REPO_ROOT / "src" / "dazzle_ui" / "templates"
SRC_ROOT = REPO_ROOT / "src"
# Python trees where render-call sites may live. `src/dazzle/` was added
# post-342 to cover `journey_reporter.py` (reports/e2e_journey.html).
RENDER_CALLER_ROOTS = (
    REPO_ROOT / "src" / "dazzle",
    REPO_ROOT / "src" / "dazzle_back",
    REPO_ROOT / "src" / "dazzle_ui",
)

# Glob patterns matching templates that are expected to be served by a
# Python page route. Pattern semantics use `Path.match()` which does NOT
# cross `/` with `*` — so `site/*.html` matches site/page.html but NOT
# site/auth/foo.html.
#
# Started with `site/auth/` (cycle 306) — the family where EX-055
# surfaced. Cycle 307 added `app/`. Cycle 308 added `site/` top-level
# + layout-template detection so site_base.html (extended, not served)
# is correctly excluded.
PAGE_TEMPLATE_PATTERNS: tuple[str, ...] = (
    "site/auth/*.html",
    "app/*.html",
    "site/*.html",
    "workspace/*.html",
    "experience/*.html",
    "reports/*.html",
)

# Page templates that genuinely should NOT be served by a page route
# (e.g. the template is consumed by a different mechanism, or the
# feature is pending a separate triage). Each entry requires a reason.
INDIVIDUAL_ALLOWLIST: dict[str, str] = {}

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
    # `render_fragment("<path>", ...)` — htmx fragments + composite pages
    # (workspace/experience are served this way via the route layer).
    re.compile(r'render_fragment\(\s*["\']([^"\']+)["\']'),
    # `env.get_template("<path>")` — direct Jinja usage (reports/e2e_journey.html).
    # Note: renderer helpers in template_renderer.py pass a variable, not a literal,
    # so they don't self-match.
    re.compile(r'\.get_template\(\s*["\']([^"\']+)["\']'),
)


_EXTENDS_RE = re.compile(r'{%\s*extends\s+["\']([^"\']+)["\']')


def _collect_layout_templates() -> set[str]:
    """Find templates that are extended by others — these are layouts, not pages.

    A page is something a route SERVES. A layout is something other templates
    EXTEND via `{% extends %}`. Layout templates shouldn't be flagged as
    unserved — they're structurally not meant to be served directly.

    Example: `site/site_base.html` is extended by `site/page.html`,
    `site/403.html`, `site/404.html`, `site/auth/login.html` etc. The base
    itself is not served — only its children are.
    """
    layouts: set[str] = set()
    for p in TEMPLATES_ROOT.rglob("*.html"):
        for m in _EXTENDS_RE.finditer(p.read_text()):
            layouts.add(m.group(1))
    return layouts


def _collect_page_templates() -> set[str]:
    """Every non-underscore .html file matching PAGE_TEMPLATE_PATTERNS, excluding layouts."""
    layouts = _collect_layout_templates()
    pages: set[str] = set()
    for p in TEMPLATES_ROOT.rglob("*.html"):
        rel = p.relative_to(TEMPLATES_ROOT).as_posix()
        if not any(Path(rel).match(pattern) for pattern in PAGE_TEMPLATE_PATTERNS):
            continue
        if p.name.startswith("_"):
            continue  # partial / script / shared fragment
        if rel in layouts:
            continue  # layout, extended by others, not served directly
        pages.add(rel)
    return pages


def _collect_rendered_pages() -> set[str]:
    """Extract every template path passed to a known render-helper in Python."""
    rendered: set[str] = set()
    seen: set[Path] = set()  # dazzle and dazzle_ui may overlap — dedup by path
    for root in RENDER_CALLER_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if p in seen:
                continue
            seen.add(p)
            text = p.read_text()
            for pattern in _RENDER_PATTERNS:
                for m in pattern.finditer(text):
                    rendered.add(m.group(1))
    return rendered


def _compute_unserved_pages() -> set[str]:
    return _collect_page_templates() - _collect_rendered_pages()


class TestPageRouteCoverage:
    """Every page template under PAGE_TEMPLATE_PATTERNS must be served by a route.

    Surfaces EX-055-class bugs at test-time — templates that ship with
    full styling + cycle-298-style source-level test coverage but zero
    server-side glue to reach them.
    """

    def test_every_page_template_is_served(self) -> None:
        """Surface page templates with no corresponding route."""
        unserved = _compute_unserved_pages()
        unallowed = unserved - INDIVIDUAL_ALLOWLIST.keys()
        assert not unallowed, (
            "\n\nPage template(s) under PAGE_TEMPLATE_PATTERNS with no "
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
        """Allowlist must target templates matching PAGE_TEMPLATE_PATTERNS.

        A template outside the patterns doesn't need this lint — the
        orphan_lint or other coverage handles it. Stale allowlist entries
        (from a pattern that no longer matches) should be removed.
        """
        misplaced = {
            t
            for t in INDIVIDUAL_ALLOWLIST
            if not any(Path(t).match(pattern) for pattern in PAGE_TEMPLATE_PATTERNS)
        }
        assert not misplaced, (
            f"\n\nAllowlist entries outside PAGE_TEMPLATE_PATTERNS={PAGE_TEMPLATE_PATTERNS}:\n"
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

    def test_page_template_patterns_match_real_templates(self) -> None:
        """Guard against stale PAGE_TEMPLATE_PATTERNS entries."""
        all_templates = {
            p.relative_to(TEMPLATES_ROOT).as_posix() for p in TEMPLATES_ROOT.rglob("*.html")
        }
        for pattern in PAGE_TEMPLATE_PATTERNS:
            matching = [t for t in all_templates if Path(t).match(pattern)]
            assert matching, (
                f"PAGE_TEMPLATE_PATTERNS[{pattern!r}] matches zero templates; remove it from the tuple."
            )


# Manual debugging helper
def print_coverage_report() -> None:
    """Print human-readable page-route-coverage report."""
    pages = _collect_page_templates()
    rendered = _collect_rendered_pages()
    unserved = _compute_unserved_pages()
    print(f"page templates under {PAGE_TEMPLATE_PATTERNS}: {len(pages)}")
    print(f"served by render_site_page: {len(pages & rendered)}")
    print(f"unserved: {len(unserved)}")
    if unserved:
        print("\nUnserved:")
        for t in sorted(unserved):
            allow = INDIVIDUAL_ALLOWLIST.get(t, "(NOT ALLOWLISTED)")
            print(f"  {t}  # {allow}")


if __name__ == "__main__":
    print_coverage_report()
