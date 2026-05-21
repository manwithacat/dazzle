"""invoice_events retention + InvoiceApproved.currency

Revision ID: 321d3b7c99d8
Revises: 7b4f5f16a753
Create Date: 2026-05-21 20:47:24.114835+00:00

Change 5 — event-schema change.

Finding: event_model topics and events are NOT backed by PostgreSQL tables.
The DSL changes (retention: 365→730, InvoiceApproved.currency field) are
runtime-only / config-only. Alembic autogenerate produced only F2/F3 noise
(drop _dazzle_params + spurious unique-constraint ops) which has been
stripped. This migration intentionally contains no DDL.

HLESS versioning note: HLESS (hless DSL keyword) has StreamSchema with
version/compatibility fields (ADDITIVE/BREAKING) in its IR, but this is a
separate construct from event_model. The simpler event_model DSL used here
has NO event-versioning mechanism — no version tag, no schema-registry,
no upcaster. Adding a field to an event is a silent breaking change for
existing consumers reading stored events that pre-date the new field.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "321d3b7c99d8"
down_revision: str | None = "7b4f5f16a753"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # event_model is runtime-only — no DDL produced
    pass


def downgrade() -> None:
    # event_model is runtime-only — no DDL produced
    pass
