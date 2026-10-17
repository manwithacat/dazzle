"""#1772: the public RLS binder — one resolver, three binders, no drift.

``resolve_rls_gucs`` is the single truth for the ``dazzle.tenant_id`` /
``dazzle.user_<attr>`` GUCs. ``bind_rls_context`` (the per-request contextvars the
framework's leased connection reads) and ``bind_rls`` (an app-owned DB-API
connection — AegisMark's custom routes / renderers) both derive from it. This file
is AegisMark's ``tests/serve/test_rls_bind_contract.py`` moved upstream: for every
case the connection GUCs, the contextvar GUCs and the resolver agree.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from typing import Any

import pytest

from dazzle.http.runtime.auth import (
    RBAC_DENY,
    RlsBinding,
    bind_rls,
    bind_rls_context,
    resolve_rls_gucs,
)
from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord
from dazzle.http.runtime.tenant_isolation import (
    get_current_rls_user_attrs,
    get_current_tenant_id,
    get_rls_user_attr_names,
    register_rls_user_attr_names,
    set_current_rls_user_attrs,
    set_current_tenant_id,
)

TRUST = "11111111-1111-1111-1111-111111111111"
SCHOOL = "22222222-2222-2222-2222-222222222222"
DEPT = "33333333-3333-3333-3333-333333333333"


class _Cursor:
    """psycopg2-shaped cursor: context manager + ``execute(sql, params)``, nothing else."""

    def __init__(self, calls: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._calls = calls

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self._calls.append((sql, params))


class _Conn:
    """Cursor-only connection stub (no ``conn.execute`` — psycopg2 has none)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def cursor(self) -> _Cursor:
        return _Cursor(self.calls)

    def gucs(self) -> dict[str, str]:
        """Decode the recorded calls, asserting the two allowed shapes on the way."""
        out: dict[str, str] = {}
        for sql, params in self.calls:
            if sql == "SELECT set_config('dazzle.tenant_id', %s, %s)":
                value, _local = params
                out["dazzle.tenant_id"] = value
            else:
                assert sql == "SELECT set_config(%s, %s, %s)"
                name, value, _local = params
                assert name.startswith("dazzle.user_")
                out[name] = value
            # Values only ever travel as bind parameters.
            assert value not in sql
        return out


def _user(**extra: Any) -> UserRecord:
    return UserRecord(email="t@example.org", password_hash="x", **extra)


def _membership(tenant_id: str, partition_root_id: str | None = None) -> MembershipRecord:
    return MembershipRecord(
        id="m1",
        tenant_id=tenant_id,
        identity_id="i1",
        roles=["teacher"],
        partition_root_id=partition_root_id,
    )


def _ctx(membership: MembershipRecord | None = None, **prefs: Any) -> AuthContext:
    # model_construct: a None preference (#591) is not a valid str for the
    # validator, but stores do hand the resolver one.
    return AuthContext.model_construct(
        user=_user(), is_authenticated=True, active_membership=membership, preferences=prefs
    )


def _contextvar_gucs(auth: AuthContext) -> tuple[str | None, dict[str, str]]:
    """Run bind_rls_context in a fresh context; return (returned tenant, GUC map)."""

    def run() -> tuple[str | None, dict[str, str]]:
        bound = bind_rls_context(auth)
        out: dict[str, str] = {}
        if get_current_tenant_id():
            out["dazzle.tenant_id"] = get_current_tenant_id() or ""
        for attr, value in get_current_rls_user_attrs().items():
            out[f"dazzle.user_{attr}"] = value
        return bound, out

    return contextvars.copy_context().run(run)


def _binding_gucs(binding: RlsBinding) -> dict[str, str]:
    out = {f"dazzle.user_{a}": v for a, v in binding.user_attrs.items()}
    if binding.tenant_id is not None:
        out["dazzle.tenant_id"] = binding.tenant_id
    return out


@pytest.fixture(autouse=True)
def _attr_names() -> Iterator[None]:
    before = set(get_rls_user_attr_names())
    register_rls_user_attr_names({"school", "department"})
    yield
    register_rls_user_attr_names(before)


CASES: dict[str, tuple[AuthContext, dict[str, str]]] = {
    "flat membership": (_ctx(_membership(TRUST)), {"dazzle.tenant_id": TRUST}),
    "leaf membership binds partition root": (
        _ctx(_membership(SCHOOL, partition_root_id=TRUST)),
        {"dazzle.tenant_id": TRUST},
    ),
    "scope attrs from preferences": (
        _ctx(_membership(TRUST), school=SCHOOL, department=DEPT),
        {"dazzle.tenant_id": TRUST, "dazzle.user_school": SCHOOL, "dazzle.user_department": DEPT},
    ),
    "unresolvable / empty / None / deny attrs stay unbound": (
        _ctx(_membership(TRUST), school="", department=None),
        {"dazzle.tenant_id": TRUST},
    ),
    "deny sentinel value is never bound": (
        _ctx(_membership(TRUST), school=RBAC_DENY),
        {"dazzle.tenant_id": TRUST},
    ),
    "no membership: no tenant, attrs still bind": (
        _ctx(None, tenant_id="tenant-legacy", school=SCHOOL),
        {"dazzle.user_school": SCHOOL},
    ),
    "anonymous binds nothing": (AuthContext(is_authenticated=False, preferences={}), {}),
}


@pytest.mark.parametrize(("auth", "expected"), CASES.values(), ids=CASES.keys())
def test_resolver_contextvars_and_connection_agree(
    auth: AuthContext, expected: dict[str, str]
) -> None:
    binding = resolve_rls_gucs(auth)
    assert _binding_gucs(binding) == expected

    bound_ctx, ctx_gucs = _contextvar_gucs(auth)
    assert ctx_gucs == expected
    assert bound_ctx == binding.tenant_id

    conn = _Conn()
    assert bind_rls(conn, auth) == binding.tenant_id
    assert conn.gucs() == expected


@pytest.mark.parametrize(("session", "is_local"), [(False, True), (True, False)])
def test_session_flag_flips_is_local(session: bool, is_local: bool) -> None:
    conn = _Conn()
    bind_rls(conn, _ctx(_membership(TRUST), school=SCHOOL), session=session)
    assert len(conn.calls) == 2
    assert all(params[-1] is is_local for _sql, params in conn.calls)


def test_hostile_value_never_reaches_sql_text() -> None:
    evil = "'; DROP TABLE users; --"
    conn = _Conn()
    bind_rls(conn, _ctx(_membership(TRUST), school=evil))
    assert all("DROP TABLE" not in sql for sql, _params in conn.calls)
    assert conn.gucs()["dazzle.user_school"] == evil


def test_no_auth_copies_bound_contextvars_verbatim() -> None:
    """A renderer with no request copies what the page request already bound —
    including keys beyond the registered attr names (#1626 ``id``/``entity_id``)."""

    def run() -> tuple[str | None, dict[str, str]]:
        set_current_tenant_id(TRUST)
        set_current_rls_user_attrs({"school": SCHOOL, "id": "u-1", "entity_id": "u-1"})
        conn = _Conn()
        return bind_rls(conn), conn.gucs()

    bound, gucs = contextvars.copy_context().run(run)
    assert bound == TRUST
    assert gucs == {
        "dazzle.tenant_id": TRUST,
        "dazzle.user_school": SCHOOL,
        "dazzle.user_id": "u-1",
        "dazzle.user_entity_id": "u-1",
    }


def test_no_auth_and_nothing_bound_emits_nothing() -> None:
    def run() -> tuple[str | None, list[tuple[str, tuple[Any, ...]]]]:
        conn = _Conn()
        return bind_rls(conn), conn.calls

    assert contextvars.Context().run(run) == (None, [])
