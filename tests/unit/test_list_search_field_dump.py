"""Workspace list find-by chrome must not dump schema keys (oral #182)."""

from __future__ import annotations

from pathlib import Path

from dazzle.render.filters import clerk_list_search_field_label
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer

CONTACT = Path("examples/contact_manager/dsl")


class _FakeRegion:
    def __init__(self, name: str, display: str = "list") -> None:
        self.name = name
        self.title = "Contacts"
        self.display = display
        self.empty_message = None


def _render_list(search_fields: list[str]) -> str:
    ctx = {
        "items": [{"first_name": "Ada", "last_name": "Lovelace"}],
        "columns": [{"key": "first_name", "label": "First Name"}],
        "endpoint": "/api/workspaces/home/regions/contact_list",
        "region_name": "contact_list",
        "search_fields": search_fields,
        "active_search": "",
    }
    return FragmentRenderer().render(
        WorkspaceRegionAdapter().build(_FakeRegion("contact_list"), ctx)
    )


def test_contact_manager_list_search_is_live() -> None:
    block = (CONTACT / "app.dsl").read_text()
    surface = block.split('surface contact_list "Contacts":', 1)[1].split("surface ", 1)[0]
    assert "search: first_name, last_name, email, company, job_title" in surface
    assert 'field first_name "First Name"' in surface
    assert 'field job_title "Job Title"' in surface
    region = block.split("  contact_list:", 1)[1].split("  contact_detail:", 1)[0]
    assert "display: list" in region


def test_clerk_list_search_leftover_and_empty() -> None:
    assert clerk_list_search_field_label("first_name") == "First Name"
    assert clerk_list_search_field_label("job_title") == "Job Title"
    assert clerk_list_search_field_label("zzz") == "zzz"
    assert clerk_list_search_field_label("ghost") == "ghost"
    assert clerk_list_search_field_label("") == ""
    assert clerk_list_search_field_label(None) == ""


def test_list_find_by_is_clerk_not_schema_key() -> None:
    html = _render_list(["first_name", "last_name", "email", "job_title"])
    assert "Find by First Name, Last Name, Email, Job Title" in html
    assert "Find by first name" not in html
    assert "job_title" not in html
    leftover = _render_list(["zzz", "ghost"])
    assert "Find by zzz, ghost" in leftover
    assert "Find by Zzz" not in leftover
    assert "Ghost" not in leftover


def test_empty_invents_no_find_by_chrome() -> None:
    html = _render_list([])
    assert "dz-list-search" not in html
    assert "Find by" not in html
