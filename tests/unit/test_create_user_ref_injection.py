"""Tests for manwithacat/dazzle#774 fix: current_user auto-injection for `ref User required` fields.

The cycle-201 `/ux-cycle` explore loop observed that the support_tickets
`ticket_create` surface produced a cryptic "created_by: Field required"
error on submission. Root cause: the Ticket entity declares
``created_by: ref User required`` but the surface section omits it.

The fix adds ``inject_current_user_refs`` which mutates the request body
to fill in any missing required ``ref User`` field with ``current_user``
before pydantic validation. These tests exercise the pure helper
directly; integration with ``create_create_handler`` is covered by the
end-to-end browser repro in the cycle-220 commit message.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from dazzle_back.runtime.route_generator import inject_current_user_refs


class _TicketCreate(BaseModel):
    """Mirror of a generated create schema: required fields + required ref User."""

    title: str = Field(..., description="Title")
    description: str = Field(..., description="Description")
    created_by: UUID = Field(..., description="Creator user")


class _TicketOptionalCreate(BaseModel):
    """Same entity shape but created_by is optional (default None)."""

    title: str = Field(..., description="Title")
    created_by: UUID | None = Field(default=None)


class TestInjectCurrentUserRefs:
    """Rules (all must hold): current_user known, field is ref-User, required,
    declared on schema, and body lacks an explicit value."""

    def test_injects_missing_required_ref_user_field(self) -> None:
        body: dict = {"title": "T", "description": "D"}
        inject_current_user_refs(
            body,
            _TicketCreate,
            user_ref_fields=["created_by"],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        assert body["created_by"] == "11111111-1111-1111-1111-111111111111"
        # model_validate works end-to-end with the injected value
        data = _TicketCreate.model_validate(body)
        assert str(data.created_by) == "11111111-1111-1111-1111-111111111111"

    def test_does_not_override_explicit_value(self) -> None:
        explicit = "22222222-2222-2222-2222-222222222222"
        body: dict = {"title": "T", "description": "D", "created_by": explicit}
        inject_current_user_refs(
            body,
            _TicketCreate,
            user_ref_fields=["created_by"],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        assert body["created_by"] == explicit

    def test_injects_when_body_has_none(self) -> None:
        """Explicit None in the body is treated as 'not supplied' and triggers injection."""
        body: dict = {"title": "T", "description": "D", "created_by": None}
        inject_current_user_refs(
            body,
            _TicketCreate,
            user_ref_fields=["created_by"],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        assert body["created_by"] == "11111111-1111-1111-1111-111111111111"

    def test_no_op_when_current_user_missing(self) -> None:
        """Anonymous create: nothing gets injected; pydantic will correctly reject."""
        body: dict = {"title": "T", "description": "D"}
        inject_current_user_refs(
            body,
            _TicketCreate,
            user_ref_fields=["created_by"],
            current_user=None,
        )
        assert "created_by" not in body

    def test_no_op_when_user_ref_fields_empty(self) -> None:
        """Entities without any ref-User fields behave exactly as before the fix."""
        body: dict = {"title": "T", "description": "D"}
        inject_current_user_refs(
            body,
            _TicketCreate,
            user_ref_fields=None,
            current_user="11111111-1111-1111-1111-111111111111",
        )
        assert "created_by" not in body

        body2: dict = {"title": "T", "description": "D"}
        inject_current_user_refs(
            body2,
            _TicketCreate,
            user_ref_fields=[],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        assert "created_by" not in body2

    def test_does_not_inject_optional_field(self) -> None:
        """Only REQUIRED fields qualify for injection — optional stays optional."""
        body: dict = {"title": "T"}
        inject_current_user_refs(
            body,
            _TicketOptionalCreate,
            user_ref_fields=["created_by"],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        # created_by is optional — not injected
        assert "created_by" not in body

    def test_ignores_unknown_field_name(self) -> None:
        """Field names not on the schema are silently skipped (no KeyError)."""
        body: dict = {"title": "T", "description": "D"}
        inject_current_user_refs(
            body,
            _TicketCreate,
            user_ref_fields=["nonexistent_field", "created_by"],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        assert body["created_by"] == "11111111-1111-1111-1111-111111111111"
        assert "nonexistent_field" not in body

    def test_mutates_body_in_place(self) -> None:
        """The helper modifies the caller's dict; the return value is None."""
        body: dict = {"title": "T", "description": "D"}
        result = inject_current_user_refs(
            body,
            _TicketCreate,
            user_ref_fields=["created_by"],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        assert result is None
        assert body["created_by"] == "11111111-1111-1111-1111-111111111111"

    def test_multiple_ref_user_fields(self) -> None:
        """Entities can have several ref-User fields; each gets injected independently."""

        class _MultiUserRef(BaseModel):
            title: str = Field(...)
            created_by: UUID = Field(...)
            assigned_to: UUID = Field(...)
            reviewer: UUID | None = Field(default=None)

        body: dict = {"title": "T"}
        inject_current_user_refs(
            body,
            _MultiUserRef,
            user_ref_fields=["created_by", "assigned_to", "reviewer"],
            current_user="11111111-1111-1111-1111-111111111111",
        )
        # Both required fields injected
        assert body["created_by"] == "11111111-1111-1111-1111-111111111111"
        assert body["assigned_to"] == "11111111-1111-1111-1111-111111111111"
        # Optional reviewer not injected
        assert "reviewer" not in body
