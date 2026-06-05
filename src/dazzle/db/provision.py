"""Single-org provisioning with the 1:1 org<->tenant-root mirror (auth Plan 1d).

For an app with an ``is_tenant_root`` domain entity, the framework
``organizations`` row and the domain tenant-root row share ONE id — so
``membership.tenant_id == tenant_root.id == dazzle.tenant_id`` and a member is
fenced to exactly their org by RLS. For a rootless app the framework org IS the
tenant (no domain row). Sync; one transaction on the given connection.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg import sql

DEFAULT_ORG_SLUG = "default"


class ProvisionError(RuntimeError):
    """Single-org provisioning cannot proceed (e.g. a non-seedable tenant root)."""


def _tenant_root_entity(appspec: Any) -> Any | None:
    for e in appspec.domain.entities:
        if getattr(e, "is_tenant_root", False):
            return e
        if getattr(getattr(e, "archetype_kind", None), "name", "") == "TENANT":
            return e
    return None


def _seed_values_for_root(root_entity: Any, org_id: str, name: str) -> dict[str, Any]:
    """Framework-derivable values for the tenant-root row's columns.

    ``id`` = the shared org id. Required scalar text fields get the org name (or
    a slug); a required field the framework can't derive is a loud error.
    """
    values: dict[str, Any] = {"id": org_id}
    for f in root_entity.fields:
        fname = f.name
        if fname == "id":
            continue
        if fname in ("name", "title", "display_name"):
            values[fname] = name
            continue
        if fname == "slug":
            values[fname] = name.lower().replace(" ", "-")
            continue
        # FieldSpec encodes required/auto_add in `modifiers` (exposed via
        # is_required), NOT bare `.required`/`.auto_add`. A required field with no
        # framework-derivable default is a loud error (else the INSERT raises a
        # raw NotNullViolation).
        from dazzle.core.ir.fields import FieldModifier

        required = f.is_required
        has_default = (
            f.default is not None
            or getattr(f, "default_expr", None) is not None
            or FieldModifier.AUTO_ADD in f.modifiers
        )
        if required and not has_default:
            ftype = getattr(getattr(f, "type", None), "kind", None)
            ftype = getattr(ftype, "value", ftype)
            raise ProvisionError(
                f"cannot auto-provision tenant root {root_entity.name!r}: required "
                f"field {fname!r} ({ftype}) is not framework-derivable — make it "
                "nullable/defaulted or provision the tenant explicitly"
            )
    return values


def provision_single_org(appspec: Any, name: str, *, conn: Any) -> str:
    """Ensure ONE default org (+ its 1:1 tenant-root row for archetype apps).

    Race-safe via the fixed ``DEFAULT_ORG_SLUG`` unique constraint. Returns the
    shared id (== the tenant-root row id when there is a root). Commits on
    success; rolls back on error. ``conn`` must be non-autocommit (one txn).
    """
    if getattr(conn, "autocommit", False):
        raise ProvisionError("provision_single_org requires a non-autocommit connection")
    now = datetime.now(UTC).isoformat()
    try:
        # The org slug is the SINGLE id arbiter (avoids a split where a
        # concurrent caller's root row diverges from the winning org id): insert
        # the org FIRST (ON CONFLICT DO NOTHING), then read back the winning id,
        # then mirror THAT id into the tenant-root row idempotently. A UUID id —
        # `organizations.id` is TEXT (accepts it) and it matches a uuid-typed
        # domain tenant-root pk (the 1:1 mirror target).
        candidate_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO organizations (id, slug, name, status, is_test, created_at, updated_at)
            VALUES (%s, %s, %s, 'active', false, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (candidate_id, DEFAULT_ORG_SLUG, name, now, now),
        )
        row = conn.execute(
            "SELECT id FROM organizations WHERE slug = %s", (DEFAULT_ORG_SLUG,)
        ).fetchone()
        if row is None:
            raise ProvisionError("organization absent after provision insert")
        org_id = str(row["id"] if isinstance(row, dict) else row[0])

        root = _tenant_root_entity(appspec)
        if root is not None:
            # Mirror the WINNING org id into the tenant-root row; ON CONFLICT (id)
            # DO NOTHING so a lost race (the row already exists at this id) and
            # re-provision are both idempotent — never a second/orphan root row.
            vals = _seed_values_for_root(root, org_id, name)
            cols = list(vals.keys())
            insert_root = sql.SQL(
                "INSERT INTO {tbl} ({cols}) VALUES ({ph}) ON CONFLICT (id) DO NOTHING"
            ).format(
                tbl=sql.Identifier(root.name),
                cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                ph=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
            )
            conn.execute(insert_root, tuple(vals[c] for c in cols))

        conn.commit()
        return org_id
    except Exception:
        conn.rollback()
        raise
