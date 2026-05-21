"""add partially_paid to Invoice.status

Revision ID: 7cf317f60a5f
Revises: e3c4b12a8018
Create Date: 2026-05-21 20:34:08.393377+00:00

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7cf317f60a5f"
down_revision: str | None = "e3c4b12a8018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enum evolution — no-op: Invoice.status is unconstrained TEXT in PostgreSQL.
    # Dazzle maps DSL enum fields to sa.Text() with no CHECK constraint, so adding
    # 'partially_paid' to the enum values list requires no DDL change.
    pass


def downgrade() -> None:
    # Enum evolution — no-op: see upgrade() comment.
    pass
