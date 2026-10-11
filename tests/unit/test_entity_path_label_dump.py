"""Shell breadcrumbs must not dump Issuereport for Issue Report (oral #191)."""

from __future__ import annotations

from dazzle.render.breadcrumb_fragment import build_shell_breadcrumb
from dazzle.render.context import PageContext
from dazzle.render.fragment import FragmentRenderer

_ISSUE_ID = "c3000000-0000-4000-8000-000000000001"


def test_page_title_override_still_wins_on_leaf() -> None:
    labels = {"issuereport": "Issue Report"}
    ctx = PageContext(
        page_title="Login loop on Probe-01",
        current_route=f"/app/issuereport/{_ISSUE_ID}",
        entity_path_labels=labels,
    )
    html = FragmentRenderer().render(build_shell_breadcrumb(ctx))
    assert ">Login loop on Probe-01</li>" in html
    assert ">Issue Report</a>" in html
    assert ">Issuereport</a>" not in html
    assert ">Issuereport</li>" not in html
