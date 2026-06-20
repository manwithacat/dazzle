"""ADR-0039 (#778/#1398) Slice 4 — D3b: `ref User` create-injection resolves the domain
`User` row by the declared `link_via` (email) and injects **its** id, not the auth id.

The route_generator routes a declared-`User` ref field into the same `persona_ref_map`
link-resolution proven for `backed_by` entities (cycle 249). This exercises that
resolution path for a `User` target whose domain id differs from the auth id — the
generality D3b adds over the #774 auth-id assumption.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from dazzle.http.runtime.handlers.write_handlers import resolve_backed_entity_refs


class _Create(BaseModel):
    title: str = Field(...)
    created_by: str = Field(...)  # required ref User


class _FakeUserRepo:
    """Resolves a domain `User` row by email; its id is NOT the auth id."""

    def __init__(self, domain_id: str, email: str) -> None:
        self._domain_id = domain_id
        self._email = email

    async def get_one(self, filters: dict[str, Any]) -> Any:
        if filters.get("email") == self._email:
            return {"id": self._domain_id}
        return None


def test_ref_user_resolves_domain_id_by_email() -> None:
    repo = _FakeUserRepo(domain_id="domain-99", email="alice@corp.test")
    body: dict[str, Any] = {"title": "T"}
    asyncio.run(
        resolve_backed_entity_refs(
            body,
            _Create,
            persona_ref_map={"created_by": ("User", "email", repo)},
            user_roles=["author"],
            current_user="auth-1",  # the auth id — must NOT be what lands
            user_email="alice@corp.test",
        )
    )
    # D3b: the DOMAIN row's id is injected, resolved by the email link — not the auth id.
    assert body["created_by"] == "domain-99"


def test_explicit_value_not_overridden() -> None:
    repo = _FakeUserRepo(domain_id="domain-99", email="alice@corp.test")
    body: dict[str, Any] = {"title": "T", "created_by": "explicit-7"}
    asyncio.run(
        resolve_backed_entity_refs(
            body,
            _Create,
            persona_ref_map={"created_by": ("User", "email", repo)},
            user_roles=["author"],
            current_user="auth-1",
            user_email="alice@corp.test",
        )
    )
    assert body["created_by"] == "explicit-7"
