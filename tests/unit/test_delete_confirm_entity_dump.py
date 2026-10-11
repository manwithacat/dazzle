"""Destructive confirm must not dump issuereport (oral #194)."""

from __future__ import annotations

from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter


def test_detail_confirm_issue_report_not_issuereport() -> None:
    adapter = FragmentSurfaceAdapter()
    actions = adapter._build_detail_actions(
        {
            "delete_url": "/_dazzle/issuereport/c3000000-0000-4000-8000-000000000001",
            "entity_name": "IssueReport",
            "entity_title": "Issue Report",
        }
    )
    confirm = getattr(actions[0], "hx_confirm", None) or ""
    assert confirm == "Delete this issue report?"
    bare = adapter._build_detail_actions(
        {
            "delete_url": "/_dazzle/issuereport/c3000000-0000-4000-8000-000000000001",
            "entity_name": "IssueReport",
        }
    )
    assert getattr(bare[0], "hx_confirm", None) == "Delete this issue report?"
