"""#1553 — the QA persona panel is an HM-native composition.

The deprecated panel carried 19 bespoke ``dz-qa-*`` classes (frozen in
site-sections.css) and an inline ``<script>`` (CSP-hostile). The
reimplementation composes existing HM primitives — card, badge, button,
auto-grid, stack, cluster — and moves the magic-link wiring into the
delegated ``dz-qa.js`` controller. The ``data-qa-login-persona``
attribute and the ``POST /qa/magic-link`` contract are unchanged (the
dev workflow keeps working).
"""

from pathlib import Path
from types import SimpleNamespace

from dazzle.http.runtime.site_routes import _render_qa_personas_html

_REPO = Path(__file__).resolve().parents[2]


def _personas() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            id="agent",
            display_name="Support Agent",
            email="agent@example.test",
            description="Triage the queue",
            stories=["Resolve a ticket", "Escalate to manager"],
        ),
        SimpleNamespace(
            id="admin",
            display_name="Admin",
            email="admin@example.test",
            description="Full access",
            stories=[],
        ),
    ]


class TestHmNativeMarkup:
    def test_no_bespoke_qa_classes(self) -> None:
        html = _render_qa_personas_html(_personas())
        assert "dz-qa-" not in html

    def test_no_inline_script(self) -> None:
        """CSP-friendly: the magic-link wiring lives in dz-qa.js, not
        an inline block."""
        html = _render_qa_personas_html(_personas())
        assert "<script" not in html

    def test_composes_hm_primitives(self) -> None:
        html = _render_qa_personas_html(_personas())
        assert 'class="dz-card' in html
        assert "dz-auto-grid" in html
        assert 'class="dz-badge"' in html or "dz-badge" in html
        assert 'data-dz-tone="warning"' in html  # the dev-mode banner

    def test_login_contract_preserved(self) -> None:
        """dz-qa.js keys off data-qa-login-persona — same attribute the
        deprecated inline script used."""
        html = _render_qa_personas_html(_personas())
        assert 'data-qa-login-persona="agent"' in html
        assert 'data-qa-login-persona="admin"' in html
        assert "Log in as Support Agent" in html

    def test_content_escaped(self) -> None:
        p = SimpleNamespace(
            id='x"><img src=x>',
            display_name="<b>Bold</b>",
            email="a@b",
            description="d & e",
            stories=["<i>s</i>"],
        )
        html = _render_qa_personas_html([p])
        assert "<b>Bold</b>" not in html
        assert "<i>s</i>" not in html
        assert 'data-qa-login-persona="x&quot;&gt;&lt;img src=x&gt;"' in html

    def test_stories_render_when_present(self) -> None:
        html = _render_qa_personas_html(_personas())
        assert "Resolve a ticket" in html
        assert "Escalate to manager" in html


class TestDelegatedController:
    def test_controller_exists_and_is_delegated(self) -> None:
        js = (_REPO / "src/dazzle/page/runtime/static/js/dz-qa.js").read_text(encoding="utf-8")
        # document-level delegation (the HM idiom), not per-button binds
        assert 'document.addEventListener("click"' in js
        assert "data-qa-login-persona" in js
        assert "/qa/magic-link" in js

    def test_landing_page_threads_the_controller(self) -> None:
        """The site page loads dz-qa.js only when the panel renders."""
        import inspect

        from dazzle.http.runtime import site_routes

        src = inspect.getsource(site_routes)
        assert "/static/js/dz-qa.js" in src
        # the load is CONDITIONAL on the rendered panel's marker — the
        # controller never ships to pages without the panel
        assert '"data-qa-personas" in inner_html' in src


class TestLegacyCssRetired:
    def test_site_sections_has_no_qa_rules(self) -> None:
        css = (_REPO / "src/dazzle/page/runtime/static/css/site-sections.css").read_text(
            encoding="utf-8"
        )
        assert ".dz-qa-" not in css
