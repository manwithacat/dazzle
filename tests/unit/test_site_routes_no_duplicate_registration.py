"""Regression: site page routes (`/`, `/site.js`, `/styles/dazzle.css`)
must be registered exactly once across the boot sequence.

The duplicate-registration bug was caught by the cycle-4 fuzz sweep
across contact_manager, support_tickets, and ops_dashboard — all
three logged ``GET / registered twice: serve_page, serve_root_page``
plus the same warning for `/site.js` and `/styles/dazzle.css` at
boot.

Root cause: `create_site_page_routes` was called from two places —
`app_factory.py` (the canonical full-featured wiring with auth/
persona/analytics context) and `subsystems/system_routes.py` (a
bare-bones leftover from the v0.16 era). Both fired when
``ctx.sitespec_data`` was set, producing duplicate handlers on the
same paths.

This test pins the call-site count to one so any future re-addition
fails CI before reaching a release.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _count_calls(text: str, name: str) -> int:
    """Count `<name>(` invocations, ignoring imports and definitions."""
    pattern = re.compile(rf"\b{re.escape(name)}\s*\(")
    hits = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("from ", "import ", "def ", "#")):
            continue
        if pattern.search(line):
            hits += 1
    return hits


class TestSitePageRouteCallSitesUnique:
    def test_create_site_page_routes_called_once(self) -> None:
        """Across the boot wiring (app_factory + subsystems), the page-
        router factory must be invoked exactly once. system_routes.py
        keeps the API-only `create_site_routes` call; the page router
        belongs solely to app_factory.py where the auth/persona/analytics
        context is in scope."""
        files = [
            ROOT / "src" / "dazzle" / "http" / "runtime" / "app_factory.py",
            ROOT / "src" / "dazzle" / "http" / "runtime" / "subsystems" / "system_routes.py",
        ]
        total = sum(_count_calls(p.read_text(), "create_site_page_routes") for p in files)
        assert total == 1, (
            f"create_site_page_routes invoked {total} times across "
            f"{[p.name for p in files]} — must be exactly 1 to avoid the "
            "duplicate `GET /` / `GET /site.js` / `GET /styles/dazzle.css` "
            "handler-registration bug. If a second call was added "
            "intentionally, dedupe the routes the factory registers and "
            "update this gate with the new contract."
        )

    def test_subsystems_keeps_api_router_call(self) -> None:
        """system_routes.py still registers the API-only `create_site_routes`
        — that endpoint set (`/api/site/*`) doesn't conflict with the
        page handlers and is a separate concern."""
        text = (
            ROOT / "src" / "dazzle" / "http" / "runtime" / "subsystems" / "system_routes.py"
        ).read_text()
        assert "create_site_routes(" in text
        assert "create_site_page_routes(" not in text
