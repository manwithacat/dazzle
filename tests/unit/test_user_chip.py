"""Avatar user-chip defaults for person refs."""

from __future__ import annotations

from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.user_chip import (
    initials_from_display,
    looks_like_person_ref,
    render_user_chip_html,
    render_user_chip_linked_html,
    wrap_user_chip_link,
)


class TestLooksLikePersonRef:
    def test_user_entity(self) -> None:
        assert looks_like_person_ref({"name": "Ada"}, {"key": "owner", "ref_entity": "User"})

    def test_assigned_to_key(self) -> None:
        assert looks_like_person_ref({"name": "Ada"}, {"key": "assigned_to"})

    def test_org_ref_not_person(self) -> None:
        assert not looks_like_person_ref(
            {"name": "Acme"}, {"key": "org", "ref_entity": "Organisation"}
        )

    def test_opt_out(self) -> None:
        assert not looks_like_person_ref({"name": "Ada"}, {"key": "assigned_to", "avatar": False})


class TestRenderUserChip:
    def test_initials_chip(self) -> None:
        html = render_user_chip_html(
            {"name": "Ada Lovelace", "id": "u1"},
            {"key": "assigned_to", "ref_entity": "User"},
        )
        assert "dz-avatar" in html
        assert "dz-user-chip" in html
        assert "AL" in html
        assert "Ada Lovelace" in html

    def test_image_chip(self) -> None:
        html = render_user_chip_html(
            {"name": "Ada", "avatar_url": "https://example.com/a.png"},
            {"key": "author", "ref_entity": "User"},
        )
        assert "<img" in html
        assert "https://example.com/a.png" in html

    def test_initials_helper(self) -> None:
        assert initials_from_display("Ada Lovelace") == "AL"
        assert initials_from_display("Prince") == "PR"


class TestDataRowIntegration:
    def test_ref_cell_emits_avatar_for_user(self) -> None:
        out = _render_cell_display(
            {"type": "ref", "key": "assigned_to", "ref_entity": "User"},
            {"name": "Maya Chen", "id": "u9"},
        )
        assert "dz-avatar" in out
        assert "Maya Chen" in out

    def test_ref_cell_plain_for_non_person(self) -> None:
        out = _render_cell_display(
            {"type": "ref", "key": "client", "ref_entity": "Client"},
            {"name": "Acme Corp", "id": "c1"},
        )
        assert "dz-avatar" not in out
        assert "Acme Corp" in out

    def test_display_sibling_still_emits_avatar(self) -> None:
        """``{key}_display`` must not short-circuit Avatar (cycle 1363)."""
        from dazzle.render.fragment.primitives import RowCapabilities
        from dazzle.render.fragment.renderer._data_row import render_data_row

        html = render_data_row(
            (
                {
                    "key": "assigned_to",
                    "type": "ref",
                    "ref_entity": "User",
                    "label": "Assigned",
                },
            ),
            {
                "id": "t1",
                "assigned_to": {"id": "u9", "__display__": "Maya Chen"},
                "assigned_to_display": "Maya Chen",
            },
            RowCapabilities(),
            entity_name="Task",
        )
        assert "dz-avatar" in html
        assert "Maya Chen" in html

    def test_ref_entity_alone_detects_person(self) -> None:
        """Non-heuristic field key + ref_entity=User still chips."""
        out = _render_cell_display(
            {"type": "ref", "key": "sponsor", "ref_entity": "User"},
            {"name": "Pat Lee", "id": "u2"},
        )
        assert "dz-avatar" in out
        assert "Pat Lee" in out

    def test_list_cell_chip_links_when_ref_route(self) -> None:
        """List/detail cell core must wrap chips in dz-user-chip-link (cycle 1364)."""
        out = _render_cell_display(
            {
                "type": "ref",
                "key": "assigned_to",
                "ref_entity": "User",
                "ref_route": "/app/user/{id}",
            },
            {"name": "Maya Chen", "id": "u9"},
        )
        assert "dz-user-chip-link" in out
        assert "/app/user/u9" in out
        assert "dz-avatar" in out

    def test_list_row_chip_links_with_display_sibling(self) -> None:
        from dazzle.render.fragment.primitives import RowCapabilities
        from dazzle.render.fragment.renderer._data_row import render_data_row

        html = render_data_row(
            (
                {
                    "key": "assigned_to",
                    "type": "ref",
                    "ref_entity": "User",
                    "ref_route": "/users/{id}",
                    "label": "Assigned",
                },
            ),
            {
                "id": "t1",
                "assigned_to": {"id": "u9", "__display__": "Maya Chen"},
                "assigned_to_display": "Maya Chen",
            },
            RowCapabilities(),
            entity_name="Task",
        )
        assert "dz-user-chip-link" in html
        assert "/users/u9" in html
        assert "dz-avatar" in html


class TestChipLinkHelpers:
    def test_wrap_without_route_is_identity(self) -> None:
        chip = render_user_chip_html(
            {"name": "Ada", "id": "u1"},
            {"key": "author", "ref_entity": "User"},
        )
        assert wrap_user_chip_link(chip, {"name": "Ada", "id": "u1"}, {"key": "author"}) == chip

    def test_linked_html_builds_href(self) -> None:
        html = render_user_chip_linked_html(
            {"name": "Ada", "id": "u1"},
            {"key": "author", "ref_entity": "User", "ref_route": "/people/{id}"},
        )
        assert 'href="/people/u1"' in html
        assert "dz-user-chip-link" in html


class TestRegionPersonRef:
    def test_workspace_ref_emits_avatar_chip(self) -> None:
        from dazzle.render.fragment.region._shared import _render_typed_value

        frag = _render_typed_value(
            {"assigned_to": {"id": "u1", "name": "Ada Lovelace", "__display__": "Ada Lovelace"}},
            {
                "key": "assigned_to",
                "type": "ref",
                "ref_entity": "User",
                "ref_route": "/app/user/{id}",
            },
        )
        assert hasattr(frag, "html")
        assert "dz-avatar" in frag.html
        assert "dz-user-chip" in frag.html
        assert "dz-user-chip-link" in frag.html
        assert "/app/user/u1" in frag.html
