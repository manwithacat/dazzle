"""Avatar user-chip defaults for person refs."""

from __future__ import annotations

from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.user_chip import (
    initials_from_display,
    looks_like_person_ref,
    render_user_chip_html,
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
