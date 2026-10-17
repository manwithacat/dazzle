"""Real-PostgreSQL proof of ``dazzle db dump`` / ``restore-check`` (#1788).

The cyfuture failure: on a single-role host the app role owns the tables and is
filtered by ``FORCE ROW LEVEL SECURITY``, so ``heroku pg:backups`` (a plain
``pg_dump``) errors and ``pg_dump --enable-row-security`` writes every fenced
table empty. The tenant-aware dump binds each tenant through PGOPTIONS.

A scratch DB gets a uniquely-suffixed LOGIN NOSUPERUSER NOBYPASSRLS owner role
which — as the owner — creates the ``fixtures/tenant_rls`` schema + auth tables
and applies RLS (the single-role Heroku shape). Two tenants are seeded through
the superuser admin connection. Then:

1. control: an unbound plain ``pg_dump`` errors and an unbound
   ``--enable-row-security`` dump carries zero fenced rows (the bug);
2. ``db dump`` as the owner writes one dump per tenant + a manifest whose
   counts are right, and ``restore-check`` into a second scratch DB exits 0;
3. from the superuser: ``db dump`` refuses without ``--role`` and works with it;
4. ``restore-check`` refuses the source DB and a non-empty target, and
   ``--drop-first`` wipes a scratch target;
5. ``db snapshot`` refuses and ``apply-rls --check-dumpable`` exits 1 for the
   owner (0 for the superuser).

Marked ``e2e`` + ``postgres``: skipped without ``TEST_DATABASE_URL`` /
``DATABASE_URL`` or without ``pg_dump`` / ``pg_restore`` on PATH.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls").resolve()
_OWNER_PW = "tenant_dump_owner_pw"  # fixture-only test password, never a real secret
_MEMBERS = {"a": 2, "b": 3}  # members seeded per tenant

runner = CliRunner()


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


def _with_db(url: str, db: str, *, user: str | None = None, pw: str | None = None) -> str:
    head, _, rest = url.partition("://")
    creds, _, hostpart = rest.rpartition("@")
    host_only = hostpart.rpartition("/")[0]
    prefix = (f"{creds}@" if creds else "") if user is None else f"{user}:{pw}@"
    return f"{head}://{prefix}{host_only}/{db}"


@dataclass
class _Harness:
    admin_url: str  # superuser, scratch DB
    owner_url: str  # NOSUPERUSER NOBYPASSRLS owner, scratch DB
    owner: str
    target_url: str  # superuser, second (empty) scratch DB
    tenants: dict[str, str]  # key → tenant id


def _drop(admin_url: str, db: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (db,),
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{db}"')  # nosemgrep — uuid-derived


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Harness]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        pytest.skip("pg_dump/pg_restore not on PATH (install the PostgreSQL client tools)")

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.db.connection import get_connection
    from dazzle.db.rls_apply import apply_rls_policies
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.auth.store import ensure_auth_core_tables
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    suffix = uuid.uuid4().hex[:8]
    scratch = f"dazzle_tenant_dump_{suffix}"
    target = f"dazzle_tenant_dump_tgt_{suffix}"
    owner = f"dazzle_dump_owner_{suffix}"
    admin_url = _admin_url()
    scratch_admin = _with_db(admin_url, scratch)
    owner_url = _with_db(admin_url, scratch, user=owner, pw=_OWNER_PW)
    owner_engine: sa.Engine | None = None
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived db name
            admin.execute(f'CREATE DATABASE "{target}"')  # nosemgrep — uuid-derived db name
            admin.execute(  # nosemgrep — uuid-derived role; fixture password
                f"CREATE ROLE \"{owner}\" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{_OWNER_PW}'"
            )
        with psycopg.connect(scratch_admin, autocommit=True) as admin:
            admin.execute(f'GRANT CREATE, USAGE ON SCHEMA public TO "{owner}"')  # nosemgrep

        appspec = load_project_appspec(_PROJECT_ROOT)
        pk = appspec.tenancy.isolation.partition_key
        entities = convert_entities(appspec.domain.entities)
        scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))

        # As the owner: it owns the tables, so FORCE RLS governs it (single-role host).
        owner_engine = sa.create_engine(owner_url.replace("postgresql://", "postgresql+psycopg://"))
        build_metadata(entities, partition_key=pk, tenant_scoped=scoped).create_all(owner_engine)
        with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
            ensure_auth_core_tables(cur)

        async def _apply() -> int:
            conn = await get_connection(explicit_url=owner_url)
            try:
                return await apply_rls_policies(conn, appspec, entities)
            finally:
                await conn.close()

        assert asyncio.run(_apply()) > 0

        tenants = {k: str(uuid.uuid4()) for k in _MEMBERS}
        with psycopg.connect(scratch_admin) as admin:
            for key, tid in tenants.items():
                admin.execute(
                    "INSERT INTO organizations (id, slug, name, created_at, updated_at) "
                    "VALUES (%s, %s, %s, now()::text, now()::text)",
                    (tid, f"org-{key}", f"Org {key}"),
                )
                admin.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (tid, key))
                for i in range(_MEMBERS[key]):
                    admin.execute(
                        'INSERT INTO "Member" (tenant_id, id, email) VALUES (%s, %s, %s)',
                        (tid, str(uuid.uuid4()), f"{key}{i}@example.test"),
                    )
        # The CLI loads the appspec from the cwd; never let a host DATABASE_URL leak in.
        monkeypatch.chdir(_PROJECT_ROOT)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        yield _Harness(
            admin_url=scratch_admin,
            owner_url=owner_url,
            owner=owner,
            target_url=_with_db(admin_url, target),
            tenants=tenants,
        )
    finally:
        if owner_engine is not None:
            owner_engine.dispose()
        _drop(admin_url, scratch)
        _drop(admin_url, target)
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'DROP ROLE IF EXISTS "{owner}"')  # nosemgrep — uuid-derived role


def _libpq_env(url: str) -> dict[str, str]:
    from dazzle.db.tenant_dump import pg_client_env

    return pg_client_env(os.environ, url)


def _dump(h: _Harness, out: Path, *extra: str, url: str | None = None) -> object:
    from dazzle.cli.db import db_app

    return runner.invoke(
        db_app, ["dump", "--out", str(out), *extra, "--database-url", url or h.owner_url]
    )


def _expected_member_counts(h: _Harness) -> dict[str, int]:
    return {h.tenants[k]: n for k, n in _MEMBERS.items()}


def test_unbound_dumps_fail_or_carry_no_fenced_rows(harness: _Harness) -> None:
    """The bug: what `heroku pg:backups` and a naive --enable-row-security dump do."""
    env = _libpq_env(harness.owner_url)
    plain = subprocess.run(
        ["pg_dump", "--data-only", "--table", '"Member"'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert plain.returncode != 0
    assert "row-level security" in plain.stderr

    unbound = subprocess.run(
        ["pg_dump", "--data-only", "--enable-row-security", "--table", '"Member"'],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    copy = unbound.stdout.split('COPY public."Member"', 1)[1]
    rows = copy.split("\n", 1)[1].split("\\.", 1)[0]
    assert rows.strip() == "", "an unbound --enable-row-security dump must carry no fenced rows"


def test_dump_as_owner_then_restore_check(harness: _Harness, tmp_path: Path) -> None:
    from dazzle.cli.db import db_app

    h = harness
    result = _dump(h, tmp_path, "--label", "nightly")
    assert result.exit_code == 0, result.output

    dump_dir = tmp_path / "nightly"
    manifest = json.loads((dump_dir / "manifest.json").read_text())
    assert sorted(manifest["files"]) == ["a.dump", "b.dump"]
    assert {t["id"]: t["slug"] for t in manifest["tenants"]} == {v: k for k, v in h.tenants.items()}
    assert manifest["partition_key"] == "tenant_id"
    assert manifest["tenant_entity"] == "Workspace"
    assert "Member" in manifest["rls_tables"]
    assert {"Workspace", "organizations", "users"} <= set(manifest["non_rls_tables"])
    assert {t: c["Member"] for t, c in manifest["counts"].items()} == _expected_member_counts(h)
    assert manifest["globals"]["organizations"] == len(_MEMBERS)
    assert manifest["globals"]["Workspace"] == len(_MEMBERS)
    for name, size in manifest["files"].items():
        assert (dump_dir / name).stat().st_size == size

    check = runner.invoke(
        db_app, ["restore-check", "--from", str(dump_dir), "--target-url", h.target_url]
    )
    assert check.exit_code == 0, check.output
    assert "counts match" in check.output
    with psycopg.connect(h.target_url) as conn:
        rows = conn.execute('SELECT tenant_id::text, count(*) FROM "Member" GROUP BY 1').fetchall()
        forced = conn.execute(
            "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'Member'"
        ).fetchone()
    assert dict(rows) == _expected_member_counts(h)
    assert forced == (True,), "post-data must restore FORCE ROW LEVEL SECURITY"

    # A second restore into the now-populated target refuses, --drop-first wipes it.
    again = runner.invoke(
        db_app, ["restore-check", "--from", str(dump_dir), "--target-url", h.target_url]
    )
    assert again.exit_code == 2, again.output
    wiped = runner.invoke(
        db_app,
        ["restore-check", "--from", str(dump_dir), "--target-url", h.target_url, "--drop-first"],
    )
    assert wiped.exit_code == 0, wiped.output

    # Never into the source.
    source = runner.invoke(
        db_app, ["restore-check", "--from", str(dump_dir), "--target-url", h.admin_url]
    )
    assert source.exit_code == 2, source.output


def test_superuser_dump_needs_a_non_bypass_role(harness: _Harness, tmp_path: Path) -> None:
    h = harness
    refused = _dump(h, tmp_path, "--label", "su", url=h.admin_url)
    assert refused.exit_code == 2, refused.output
    assert not (tmp_path / "su").exists()

    ok = _dump(h, tmp_path, "--label", "su", "--role", h.owner, url=h.admin_url)
    assert ok.exit_code == 0, ok.output
    manifest = json.loads((tmp_path / "su" / "manifest.json").read_text())
    assert {t: c["Member"] for t, c in manifest["counts"].items()} == _expected_member_counts(h)


def test_plain_snapshot_refuses_and_check_dumpable_flags_owner(
    harness: _Harness, tmp_path: Path
) -> None:
    from dazzle.cli.db import db_app

    h = harness
    snap = runner.invoke(
        db_app,
        ["snapshot", "pre", "--database-url", h.owner_url, "--project", str(tmp_path)],
    )
    assert snap.exit_code == 2, snap.output
    assert "dazzle db dump" in snap.output

    owner = runner.invoke(db_app, ["apply-rls", "--check-dumpable", "--database-url", h.owner_url])
    assert owner.exit_code == 1, owner.output
    su = runner.invoke(db_app, ["apply-rls", "--check-dumpable", "--database-url", h.admin_url])
    assert su.exit_code == 0, su.output
