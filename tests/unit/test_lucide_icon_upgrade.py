"""
Regression tests for lucide icon upgrade wiring (#846).

`lucide.min.js` is loaded with `defer` in `base.html`. The old
`<script>if(window.lucide)lucide.createIcons();</script>` in
`app_shell.html` ran synchronously before the deferred script loaded,
so `window.lucide` was always `undefined` at that point — every
`<i data-lucide>` stayed blank on initial render. There was also no
re-invocation after HTMX swaps.

Fix pins the hook in `base.html` on `DOMContentLoaded` and
`htmx:afterSettle`. These tests guard the hook + its removal from the
stale app_shell location.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "templates"
BASE = TEMPLATES / "base.html"
APP_SHELL = TEMPLATES / "layouts" / "app_shell.html"


class TestLucideUpgradeHook:
    def test_base_html_invokes_createIcons(self) -> None:
        content = BASE.read_text()
        assert "lucide.createIcons()" in content, (
            "base.html no longer calls lucide.createIcons — #846 regression."
        )

    def test_hook_binds_dom_content_loaded(self) -> None:
        """Upgrade must fire on initial load via DOMContentLoaded."""
        content = BASE.read_text()
        assert "DOMContentLoaded" in content, (
            "Lucide upgrade hook dropped its DOMContentLoaded listener — #846."
        )

    def test_hook_binds_htmx_after_settle(self) -> None:
        """Upgrade must fire after every HTMX swap."""
        content = BASE.read_text()
        assert "htmx:afterSettle" in content, (
            "Lucide upgrade hook dropped htmx:afterSettle — icons won't "
            "re-render after nav swaps (#846)."
        )

    def test_app_shell_no_longer_carries_stale_inline_hook(self) -> None:
        """The broken one-shot in app_shell.html must stay removed."""
        content = APP_SHELL.read_text()
        assert "if(window.lucide)lucide.createIcons()" not in content, (
            "The stale `if(window.lucide)lucide.createIcons()` inline script "
            "has reappeared in app_shell.html — it runs before the deferred "
            "lucide.min.js loads and leaves icons blank (#846)."
        )
