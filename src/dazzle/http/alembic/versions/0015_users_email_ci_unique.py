"""Mirror the case-insensitive `users.email` unique index into the alembic chain (#1342 M2).

Guarded safety-net mirroring ``AuthStore._ensure_email_ci_uniqueness`` (the primary creator).
A plain ``email TEXT UNIQUE`` is case-SENSITIVE, so ``Foo@x.com`` and ``foo@x.com`` could coexist
— a *split identity*. A functional unique index on ``LOWER(email)`` closes that structurally
(no CITEXT extension needed). Pre-existing case-duplicate rows must fail the upgrade loudly
(data integrity) rather than letting an opaque duplicate-key abort the migration mid-way.
Idempotent: a DB already bootstrapped by ``_init_db`` no-ops (IF NOT EXISTS + clean-data check).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0015_users_email_ci_unique"
down_revision = "0014_memberships_external_id_unique"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("users"):
        return
    bind = op.get_bind()
    collisions = bind.execute(
        sa.text(
            "SELECT LOWER(email) AS k, COUNT(*) AS n FROM users "
            "GROUP BY LOWER(email) HAVING COUNT(*) > 1 LIMIT 5"
        )
    ).fetchall()
    if collisions:
        examples = ", ".join(f"{r.k} (x{r.n})" for r in collisions)
        raise RuntimeError(
            "Cannot enforce case-insensitive email uniqueness (#1342 M2): the users table has "
            f"rows that collide on LOWER(email): {examples}. Merge the duplicate user rows "
            "(one identity per lowercased email), then re-run the migration."
        )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (LOWER(email))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS users_email_lower_key")
