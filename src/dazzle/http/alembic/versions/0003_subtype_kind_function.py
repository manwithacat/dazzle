"""Register assert_subtype_kind() plpgsql function

Registers the shared plpgsql function called by per-child triggers that
enforce TPT discriminator consistency (#1217 Phase 3e.iii). The function
is project-agnostic — one declaration shared across all subtype-using apps.

Per-child triggers are applied by the runtime DB bootstrap (slice 3e.iii
Task 15), not by this migration, because the trigger declarations depend
on per-project subtype declarations in the parsed AppSpec.

Revision ID: 0003_subtype_kind_function
Revises: 0002_drop_dazzle_migrations
Created: 2026-05-24
"""

from __future__ import annotations

from alembic import op

from dazzle.http.runtime.triggers import build_assert_subtype_kind_function

revision = "0003_subtype_kind_function"
down_revision = "0002_drop_dazzle_migrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(build_assert_subtype_kind_function())


def downgrade() -> None:
    # CASCADE required: any per-child trigger installed by runtime bootstrap
    # depends on this function; naked DROP would fail.
    op.execute("DROP FUNCTION IF EXISTS assert_subtype_kind() CASCADE")
