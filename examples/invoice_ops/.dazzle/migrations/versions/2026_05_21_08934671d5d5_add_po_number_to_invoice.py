"""add po_number to Invoice

Revision ID: 08934671d5d5
Revises: 5c144ea092ef
Create Date: 2026-05-21 20:23:12.118105+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "08934671d5d5"
down_revision: str | None = "5c144ea092ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Hand-edited: stripped spurious _dazzle_params drop and unnamed
    # unique-constraint ops emitted by autogenerate. Column type kept as
    # sa.Text() — Dazzle maps str/str(N) to TEXT (back/runtime/sa_schema.py);
    # the (40) length is an application-layer concern, not a DB column type.
    op.add_column("Invoice", sa.Column("po_number", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("Invoice", "po_number")
