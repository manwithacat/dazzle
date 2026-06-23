"""Backfill an existing deployment onto the membership model (auth Plan 1d follow-up).

For a deployment that predates the membership model, this mirrors each domain
tenant-root row into the framework ``organizations`` table at the SAME id (the
1:1 mirror) and creates a membership for each auth ``users`` row, resolving the
user's tenant via the domain user entity (matched by email). Idempotent
(``ON CONFLICT DO NOTHING`` + skip-existing) and ``dry_run``-able. Sync; one
transaction on the given (non-autocommit) connection.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from psycopg import sql

from dazzle.db.provision import _tenant_root_entity


class MigrateError(RuntimeError):
    """Migration cannot proceed safely."""


@dataclass
class MigrateResult:
    dry_run: bool
    orgs_mirrored: int = 0
    memberships_created: int = 0
    users_skipped: list[str] = field(default_factory=list)  # emails with no resolvable tenant


def _slugify(name: str) -> str:
    keep = "".join(c if c.isalnum() else "-" for c in name.lower())
    return "-".join(p for p in keep.split("-") if p)[:40] or "org"


def _scalar(row: Any, key: str) -> Any:
    if row is None:
        return None
    return row[key] if isinstance(row, dict) else row[0]


def migrate_to_memberships(
    appspec: Any, *, conn: Any, dry_run: bool = False, user_entity: str | None = None
) -> MigrateResult:
    """Backfill organizations (mirroring tenant-root rows) + a membership per user.

    ``conn`` must be non-autocommit (one transaction). Requires the app to have an
    ``is_tenant_root`` entity and an ``auth.user_entity`` carrying the partition
    key + an ``email`` — otherwise there's nothing to resolve and it raises.
    """
    if getattr(conn, "autocommit", False):
        raise MigrateError("migrate_to_memberships requires a non-autocommit connection")

    root = _tenant_root_entity(appspec)
    if root is None:
        raise MigrateError(
            "no is_tenant_root entity — nothing to mirror (a rootless app uses the "
            "framework org at signup; migration is for tenant-root deployments)"
        )
    partition_key = "tenant_id"
    tenancy = getattr(appspec, "tenancy", None)
    isolation = getattr(tenancy, "isolation", None) if tenancy is not None else None
    if isolation is not None:
        partition_key = getattr(isolation, "partition_key", "tenant_id")
    resolved_user_entity = (
        user_entity or getattr(getattr(appspec, "auth", None), "user_entity", "User") or "User"
    )

    result = MigrateResult(dry_run=dry_run)
    now = datetime.now(UTC).isoformat()
    try:
        # 1. Mirror each domain tenant-root row → organizations (shared id).
        root_rows = conn.execute(
            sql.SQL("SELECT id, name FROM {tbl}").format(tbl=sql.Identifier(root.name))
        ).fetchall()
        for r in root_rows:
            rid = str(_scalar_at(r, "id", 0))
            rname = _scalar_at(r, "name", 1) or rid
            already = conn.execute("SELECT 1 FROM organizations WHERE id = %s", (rid,)).fetchone()
            if already is not None:
                continue
            result.orgs_mirrored += 1
            if not dry_run:
                conn.execute(
                    """
                    INSERT INTO organizations
                        (id, slug, name, status, is_test, created_at, updated_at)
                    VALUES (%s, %s, %s, 'active', false, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (rid, f"{_slugify(str(rname))}-{rid[:8]}", str(rname), now, now),
                )

        # 2. A membership per auth user, tenant resolved via the domain user
        #    entity (email → partition_key). Skip users with no resolvable tenant.
        users = conn.execute("SELECT id, email, roles FROM users").fetchall()
        for u in users:
            uid = str(_scalar_at(u, "id", 0))
            email = _scalar_at(u, "email", 1)
            tid_row = conn.execute(
                sql.SQL("SELECT {pk} FROM {tbl} WHERE email = %s LIMIT 1").format(
                    pk=sql.Identifier(partition_key), tbl=sql.Identifier(resolved_user_entity)
                ),
                (email,),
            ).fetchone()
            tenant_id = _scalar(tid_row, partition_key)
            if tenant_id is None:
                result.users_skipped.append(str(email))
                continue
            tenant_id = str(tenant_id)
            exists = conn.execute(
                "SELECT 1 FROM memberships WHERE tenant_id = %s AND identity_id = %s",
                (tenant_id, uid),
            ).fetchone()
            if exists is not None:
                continue
            result.memberships_created += 1
            if not dry_run:
                roles = _scalar_at(u, "roles", 2)
                # #1463: this tool resolves tenant_id from the user entity's
                # partition_key column, which already carries the archetype:tenant
                # root (RLS partitions at the root), so partition_root_id == tenant_id
                # here. Set it explicitly so these rows are self-describing and not
                # left NULL (the boot reconcile would otherwise have to backfill them).
                conn.execute(
                    """
                    INSERT INTO memberships
                        (id, tenant_id, identity_id, roles, status, partition_root_id,
                         joined_at, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, identity_id) DO NOTHING
                    """,
                    (uuid.uuid4().hex, tenant_id, uid, roles or "[]", tenant_id, now, now, now),
                )

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return result


def _scalar_at(row: Any, key: str, idx: int) -> Any:
    return row[key] if isinstance(row, dict) else row[idx]
