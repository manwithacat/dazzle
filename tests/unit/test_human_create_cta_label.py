"""#1626 P0-2 — primary CTAs must be singular record language."""

from __future__ import annotations

from dazzle.http.runtime.renderers.fragment_adapter import human_create_cta_label


def test_prefers_entity_title_when_explicit_is_collection() -> None:
    assert (
        human_create_cta_label(
            explicit="Contact List",
            entity_title="Contact",
            entity_name="Contact",
        )
        == "New Contact"
    )


def test_strips_create_verb_from_create_surface_title() -> None:
    assert (
        human_create_cta_label(
            explicit="Create Contact",
            entity_title="Contact",
            entity_name="Contact",
        )
        == "New Contact"
    )


def test_issue_board_surface_title_does_not_leak() -> None:
    assert (
        human_create_cta_label(
            explicit="Issue Board",
            entity_title="Issue Report",
            entity_name="IssueReport",
        )
        == "New Issue Report"
    )


def test_staff_directory_surface_title_does_not_leak() -> None:
    assert (
        human_create_cta_label(
            explicit="Staff Directory",
            entity_title="Person",
            entity_name="Person",
        )
        == "New Person"
    )


def test_empty_explicit_uses_entity_title() -> None:
    assert (
        human_create_cta_label(
            explicit="",
            entity_title="Invoice",
            entity_name="Invoice",
        )
        == "New Invoice"
    )
