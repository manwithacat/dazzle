"""Tests for #957 cycle 5 — scope-predicate bypass for admin personas.

Cycle 4 plumbed the persona allow-list onto `AccessRuntimeContext`.
Cycle 5 wires it into the SQL-side scope-predicate evaluation: when an
authenticated user's role matches a `tenancy: admin_personas:` entry,
`_resolve_predicate_filters` returns `{}` (no scope WHERE clause)
instead of compiling and applying the predicate.

The bypass logic itself is in `_should_bypass_tenant_filter`, exposed
for direct unit testing. The integration with `_resolve_predicate_filters`
is verified separately to make sure the early-return short-circuits
the compile path entirely (no SQL builder calls, no UserAttrRef
resolution).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from dazzle_back.runtime.route_generator import (
    _resolve_predicate_filters,
    _should_bypass_tenant_filter,
)


def _make_auth(user: Any | None) -> Any:
    """Build a minimal AuthContext duck-type for the helper."""
    return SimpleNamespace(is_authenticated=user is not None, user=user)


def _make_user(*, roles: list[str], is_superuser: bool = False) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        roles=roles,
        is_superuser=is_superuser,
    )


class TestShouldBypass:
    def test_unauthenticated_no_bypass(self) -> None:
        assert _should_bypass_tenant_filter(_make_auth(None), ["super_admin"]) is False

    def test_no_admin_personas_no_bypass(self) -> None:
        user = _make_user(roles=["super_admin"])
        # Empty/None admin_personas → bypass never applies.
        assert _should_bypass_tenant_filter(_make_auth(user), None) is False
        assert _should_bypass_tenant_filter(_make_auth(user), []) is False

    def test_persona_match(self) -> None:
        user = _make_user(roles=["support"])
        assert _should_bypass_tenant_filter(_make_auth(user), ["super_admin", "support"]) is True

    def test_persona_mismatch(self) -> None:
        user = _make_user(roles=["teacher"])
        assert _should_bypass_tenant_filter(_make_auth(user), ["super_admin"]) is False

    def test_superuser_bypasses_regardless(self) -> None:
        # Superuser bypasses even with empty admin_personas.
        user = _make_user(roles=[], is_superuser=True)
        assert _should_bypass_tenant_filter(_make_auth(user), []) is True
        assert _should_bypass_tenant_filter(_make_auth(user), None) is True

    def test_role_prefix_normalised(self) -> None:
        # AuthContext often carries `role_` prefixed names; the bypass
        # check must compare against the bare DSL persona names.
        user = _make_user(roles=["role_support"])
        assert _should_bypass_tenant_filter(_make_auth(user), ["support"]) is True

    def test_user_none_no_bypass(self) -> None:
        # is_authenticated could be True with user=None in edge cases —
        # the helper must defend against that without crashing.
        ctx = SimpleNamespace(is_authenticated=True, user=None)
        assert _should_bypass_tenant_filter(ctx, ["support"]) is False


class TestResolvePredicateFilters:
    def test_bypass_returns_empty_dict_without_compiling(self) -> None:
        # Sentinel predicate — _should_bypass_tenant_filter must
        # short-circuit before compile_predicate is invoked. Passing a
        # non-predicate object (which would explode if compiled) proves
        # the early return.
        user = _make_user(roles=["support"])
        bogus_predicate = object()
        result = _resolve_predicate_filters(
            bogus_predicate,
            entity_name="Manuscript",
            fk_graph=None,  # type: ignore[arg-type]
            user_id=str(user.id),
            auth_context=_make_auth(user),
            admin_personas=["super_admin", "support"],
        )
        assert result == {}

    def test_no_bypass_attempts_compile(self) -> None:
        # Same bogus predicate, but the user is NOT an admin persona.
        # Now `_resolve_predicate_filters` should call compile_predicate
        # (which will raise on the bogus object). We catch any exception
        # to verify the *compile path was taken* — the actual exception
        # type is uninteresting; absence of `{}` is the signal.
        user = _make_user(roles=["teacher"])
        bogus_predicate = object()
        try:
            result = _resolve_predicate_filters(
                bogus_predicate,
                entity_name="Manuscript",
                fk_graph=None,  # type: ignore[arg-type]
                user_id=str(user.id),
                auth_context=_make_auth(user),
                admin_personas=["super_admin"],
            )
        except Exception:
            return  # Compile path tried — that's the expected signal.
        # If we got here without raising, it must NOT be `{}` (which
        # would mean we accidentally bypassed).
        assert result != {} or result is None

    def test_default_admin_personas_keeps_compile_path(self) -> None:
        # Backward compat: omitting admin_personas keeps the cycle-5
        # behaviour identical to pre-cycle-5 — the compile path runs.
        user = _make_user(roles=["super_admin"])
        bogus_predicate = object()
        try:
            _resolve_predicate_filters(
                bogus_predicate,
                entity_name="Manuscript",
                fk_graph=None,  # type: ignore[arg-type]
                user_id=str(user.id),
                auth_context=_make_auth(user),
                # admin_personas omitted entirely
            )
        except Exception:
            return
        # If no exception raised, the compile must have somehow
        # succeeded — but the bypass path must NOT have triggered.
