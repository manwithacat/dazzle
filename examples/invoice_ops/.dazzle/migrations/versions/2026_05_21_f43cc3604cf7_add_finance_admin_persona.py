"""add finance_admin persona

Revision ID: f43cc3604cf7
Revises: 321d3b7c99d8
Create Date: 2026-05-21 20:50:52.586656+00:00

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f43cc3604cf7"
down_revision: str | None = "321d3b7c99d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # RBAC-only change — no schema impact
    pass


def downgrade() -> None:
    # RBAC-only change — no schema impact
    pass
