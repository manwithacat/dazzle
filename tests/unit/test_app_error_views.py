"""Unit tests for the Phase 2.B full in-app error views.

Covers `build_app_403_view`, `build_app_404_view`, `build_app_500_view`:
shape, suggestion/forbidden-detail rendering, back-affordance threading,
CWE-209 leak prevention (500), and escape safety.
"""

from __future__ import annotations

from dazzle.http.runtime.app_error_views import (
    build_app_403_view,
    build_app_404_view,
    build_app_500_view,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(page: object) -> str:
    return FragmentRenderer().render(page)  # type: ignore[arg-type]


# ───────────────── build_app_403_view ─────────────────


def test_app_403_announces_403_and_app_name() -> None:
    html = _render(build_app_403_view(app_name="Acme"))
    assert "403" in html
    assert "Acme" in html


def test_app_403_default_message_when_none() -> None:
    html = _render(build_app_403_view(app_name="Acme"))
    assert "permission" in html


def test_app_403_renders_supplied_message() -> None:
    html = _render(build_app_403_view(app_name="Acme", message="No dice for you"))
    assert "No dice for you" in html


def test_app_403_renders_forbidden_detail_panel() -> None:
    html = _render(
        build_app_403_view(
            app_name="Acme",
            forbidden_detail={
                "entity": "Task",
                "operation": "delete",
                "permitted_personas": ["admin", "owner"],
                "current_roles": ["viewer"],
            },
        )
    )
    assert "Entity: Task" in html
    assert "Operation: delete" in html
    assert "admin" in html and "owner" in html
    assert "viewer" in html


def test_app_403_no_panel_when_forbidden_detail_missing() -> None:
    html = _render(build_app_403_view(app_name="Acme"))
    assert "Entity:" not in html
    assert "Allowed for:" not in html


def test_app_403_renders_back_affordance_when_supplied() -> None:
    html = _render(
        build_app_403_view(
            app_name="Acme",
            back_url="/app/tasks",
            back_label="Back to Tasks",
        )
    )
    assert 'href="/app/tasks"' in html
    assert "Back to Tasks" in html


def test_app_403_always_links_dashboard() -> None:
    html = _render(build_app_403_view(app_name="Acme"))
    assert 'href="/app"' in html
    assert "Go to Dashboard" in html


def test_app_403_escapes_message() -> None:
    html = _render(
        build_app_403_view(
            app_name="Acme",
            message="<script>alert(1)</script>",
        )
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_app_403_handles_empty_current_roles_in_detail() -> None:
    html = _render(
        build_app_403_view(
            app_name="Acme",
            forbidden_detail={
                "entity": "X",
                "permitted_personas": ["admin"],
                "current_roles": [],
            },
        )
    )
    assert "(none)" in html


# ───────────────── build_app_404_view ─────────────────


def test_app_404_announces_404() -> None:
    html = _render(build_app_404_view(app_name="Acme"))
    assert "404" in html


def test_app_404_default_message() -> None:
    html = _render(build_app_404_view(app_name="Acme"))
    assert "doesn" in html and "exist" in html


def test_app_404_renders_supplied_message() -> None:
    html = _render(build_app_404_view(app_name="Acme", message="Custom miss copy"))
    assert "Custom miss copy" in html


def test_app_404_renders_suggestions_block_when_present() -> None:
    html = _render(
        build_app_404_view(
            app_name="Acme",
            suggestions=[
                {"url": "/app/tasks", "label": "Tasks workspace"},
                {"url": "/app/contacts", "label": "Contacts workspace"},
            ],
        )
    )
    assert "Did you mean" in html
    assert 'href="/app/tasks"' in html
    assert "Tasks workspace" in html
    assert 'href="/app/contacts"' in html


def test_app_404_omits_suggestions_block_when_empty() -> None:
    html = _render(build_app_404_view(app_name="Acme"))
    assert "Did you mean" not in html


def test_app_404_skips_malformed_suggestion_entries() -> None:
    """A suggestion missing url or label is silently dropped."""
    html = _render(
        build_app_404_view(
            app_name="Acme",
            suggestions=[
                {"url": "/app/x", "label": "X"},
                {"url": "", "label": "Missing URL"},
                {"url": "/app/y", "label": ""},
            ],
        )
    )
    assert "/app/x" in html
    assert "Missing URL" not in html


def test_app_404_links_back_and_dashboard() -> None:
    html = _render(
        build_app_404_view(
            app_name="Acme",
            back_url="/app/things",
            back_label="Back to Things",
        )
    )
    assert 'href="/app/things"' in html
    assert "Back to Things" in html
    assert "Go to Dashboard" in html


# ───────────────── build_app_500_view ─────────────────


def test_app_500_announces_500_and_app_name() -> None:
    html = _render(build_app_500_view(app_name="Acme"))
    assert "500" in html
    assert "Acme" in html


def test_app_500_generic_apology() -> None:
    html = _render(build_app_500_view(app_name="Acme"))
    assert "Something went wrong" in html or "try again" in html


def test_app_500_links_dashboard() -> None:
    html = _render(build_app_500_view(app_name="Acme"))
    assert 'href="/app"' in html
    assert "Go to Dashboard" in html


def test_app_500_renders_back_affordance_when_supplied() -> None:
    html = _render(
        build_app_500_view(
            app_name="Acme",
            back_url="/app/tasks",
            back_label="Back to Tasks",
        )
    )
    assert "Back to Tasks" in html


def test_app_500_no_form_no_inline_script() -> None:
    html = _render(build_app_500_view(app_name="Acme"))
    assert "<form" not in html
    assert "<script>" not in html


def test_app_500_signature_does_not_expose_message_kwarg() -> None:
    """CWE-209 guard — the view deliberately doesn't accept a
    `message=` kwarg, so handlers can't accidentally pass through
    the raw exception text."""
    import inspect

    sig = inspect.signature(build_app_500_view)
    assert "message" not in sig.parameters
