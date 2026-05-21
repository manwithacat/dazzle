"""split SupplierBankAccount out of Supplier

Revision ID: 7b4f5f16a753
Revises: 7cf317f60a5f
Create Date: 2026-05-21 20:38:33.063382+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b4f5f16a753"
down_revision: str | None = "7cf317f60a5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "SupplierBankAccount",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier", sa.Uuid(), nullable=False),
        sa.Column("bank_account_ref", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("iban", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier"],
            ["Supplier.id"],
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["Tenant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id"),
    )
    # Backfill: one bank-account row per existing supplier, BEFORE dropping the column.
    op.execute(
        """
        INSERT INTO "SupplierBankAccount"
            (id, tenant_id, supplier, bank_account_ref, account_name, created_at, updated_at)
        SELECT gen_random_uuid(), tenant_id, id, bank_account_ref, name, now(), now()
        FROM "Supplier"
        WHERE bank_account_ref IS NOT NULL
        """
    )
    op.drop_column("Supplier", "bank_account_ref")


def downgrade() -> None:
    op.add_column("Supplier", sa.Column("bank_account_ref", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE "Supplier" s
        SET bank_account_ref = sba.bank_account_ref
        FROM "SupplierBankAccount" sba
        WHERE sba.supplier = s.id
        """
    )
    op.alter_column("Supplier", "bank_account_ref", nullable=False)
    op.drop_table("SupplierBankAccount")
