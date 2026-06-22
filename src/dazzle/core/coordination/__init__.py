"""Postgres coordination primitives — claim/lease queue mechanism.

The five public names are the complete surface area for Phase 1 (process adapter)
and Phase 2 (job queue). Import directly from this package:

    from dazzle.core.coordination import claim_due_work, complete_work, fail_work
"""

from dazzle.core.coordination.claim import (
    claim_due_work,
    complete_work,
    fail_work,
    queue_columns_ddl,
    renew_lease,
)

__all__ = [
    "claim_due_work",
    "complete_work",
    "fail_work",
    "queue_columns_ddl",
    "renew_lease",
]
