"""Test validator hook for signing_validation fixture."""

from __future__ import annotations

import os
from typing import Any

from dazzle.signing import SigningError


def validate_test_doc(*, entity: Any, row: Any) -> None:
    """Validate TestDoc signing; reject if ID is in DAZZLE_QA_SIGNING_REJECT_IDS."""
    row_id = str(getattr(row, "id", ""))
    rejected = {
        p.strip()
        for p in os.environ.get("DAZZLE_QA_SIGNING_REJECT_IDS", "").split(",")
        if p.strip()
    }
    if row_id and row_id in rejected:
        raise SigningError("Test rejection: id in reject set")
