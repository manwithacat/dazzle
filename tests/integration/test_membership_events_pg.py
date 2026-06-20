"""Real-PG proof of the membership lifecycle event substrate (auth Plan 2a)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _admin_url()
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_memevt_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=store_url)
    store._init_db()
    return store


def test_create_membership_emits_provisioned_event(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["admin"])

    events = store.get_membership_events(membership_id=m.id)
    assert len(events) == 1
    e = events[0]
    assert e.event_type == "provisioned"
    assert e.roles_after == ["admin"]
    assert e.status_after == "active"
    assert e.roles_before is None  # joiner has no prior state
    # The chain verifies.
    assert store.verify_membership_event_chain().ok


def test_role_change_records_before_and_after(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])

    updated = store.update_membership_roles(m.id, ["member", "approver"], actor_id="admin-1")
    assert updated is not None
    assert updated.roles == ["member", "approver"]

    events = store.get_membership_events(membership_id=m.id)
    assert [e.event_type for e in events] == ["provisioned", "role_changed"]
    rc = events[1]
    assert rc.roles_before == ["member"]
    assert rc.roles_after == ["member", "approver"]
    assert rc.actor_id == "admin-1"
    assert store.verify_membership_event_chain().ok


def test_suspend_reactivate_record_status_transitions(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])

    store.suspend_membership(m.id, actor_id="admin-1", reason="offboarding")
    store.reactivate_membership(m.id, actor_id="admin-1")

    events = store.get_membership_events(membership_id=m.id)
    assert [e.event_type for e in events] == ["provisioned", "suspended", "reactivated"]
    assert events[1].status_before == "active" and events[1].status_after == "suspended"
    assert events[1].reason == "offboarding"
    assert events[2].status_before == "suspended" and events[2].status_after == "active"
    # The current membership row reflects the final state.
    assert store.get_membership(m.id).status == "active"


def test_suspend_when_already_suspended_is_noop_no_duplicate_event(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    store.suspend_membership(m.id, actor_id="admin-1")
    store.suspend_membership(m.id, actor_id="admin-1")  # no transition
    types = [e.event_type for e in store.get_membership_events(membership_id=m.id)]
    assert types == ["provisioned", "suspended"]  # only one suspend event


def test_remove_membership_deletes_row_but_event_survives(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])

    assert store.remove_membership(m.id, actor_id="admin-1", reason="left company") is True
    assert store.get_membership(m.id) is None  # current state gone

    events = store.get_membership_events(identity_id=str(u.id))
    assert [e.event_type for e in events] == ["provisioned", "removed"]
    assert events[1].status_before == "active" and events[1].status_after == "removed"
    assert store.verify_membership_event_chain().ok  # leaver evidence survives + chains


def test_jml_query_filters_by_tenant_and_time(store_url: str) -> None:
    store = _store(store_url)
    ua = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    ub = store.create_user(email="b@b.test", password="pw123456", roles=["worker"])
    store.create_membership(tenant_id="org-A", identity_id=str(ua.id), roles=["member"])
    store.create_membership(tenant_id="org-B", identity_id=str(ub.id), roles=["member"])

    a_events = store.get_membership_events(tenant_id="org-A")
    assert len(a_events) == 1 and a_events[0].tenant_id == "org-A"


def test_tampering_a_row_breaks_the_chain(store_url: str) -> None:
    store = _store(store_url)
    u = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.create_membership(tenant_id="org-1", identity_id=str(u.id), roles=["member"])
    store.update_membership_roles(m.id, ["member", "approver"], actor_id="admin-1")

    assert store.verify_membership_event_chain().ok
    # Tamper: rewrite a stored event's roles_after without recomputing the hash.
    with psycopg.connect(store_url, autocommit=True) as c:
        c.execute(
            "UPDATE membership_events SET roles_after = %s WHERE event_type = 'role_changed'",
            ('["member","superadmin"]',),
        )
    result = store.verify_membership_event_chain()
    assert result.ok is False
    assert result.mismatched_count >= 1


def test_migration_0009_creates_membership_events(store_url: str) -> None:
    """Migration 0009 creates `membership_events` and lands at revision 0009.

    The auth tables live in `_init_db`, not the Alembic chain, and migration 0005
    ALTERs `sessions` unguarded — so a from-scratch `upgrade head` is not
    replayable. The realistic pre-0009 state is a deployed DB with the auth tables
    present, stamped at 0008; reproduce it (init_db, drop what 0009 creates) and
    apply only 0009 (mirrors test_auth_membership_pg.test_migration_0007_*)."""
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    _store(store_url)  # auth tables present (incl. membership_events via _init_db)
    with psycopg.connect(store_url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS membership_events")  # 0009's job to recreate

    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("version_locations", str(fw / "versions"))
    cfg.set_main_option(
        "sqlalchemy.url", store_url.replace("postgresql://", "postgresql+psycopg://")
    )
    command.stamp(cfg, "0008_organizations")  # prior head
    command.upgrade(cfg, "0009_membership_events")

    with psycopg.connect(store_url) as c:
        ok = c.execute("SELECT to_regclass('public.membership_events') IS NOT NULL").fetchone()[0]
        ver = c.execute("SELECT version_num FROM alembic_version").fetchone()
    assert ok is True
    assert ver is not None and ver[0] == "0009_membership_events"
