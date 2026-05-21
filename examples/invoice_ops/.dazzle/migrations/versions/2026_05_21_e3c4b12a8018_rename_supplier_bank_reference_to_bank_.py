"""rename Supplier.bank_reference to bank_account_ref

Revision ID: e3c4b12a8018
Revises: 08934671d5d5
Create Date: 2026-05-21 20:29:48.582409+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3c4b12a8018"
down_revision: str | None = "08934671d5d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("Supplier", "bank_reference", new_column_name="bank_account_ref")


def downgrade() -> None:
    op.alter_column("Supplier", "bank_account_ref", new_column_name="bank_reference")
