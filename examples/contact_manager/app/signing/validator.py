"""Project-side signing_validator hook for EngagementLetter.

Reads DAZZLE_QA_SIGNING_REJECT_IDS (comma-separated row ids) and
raises SigningError when the row being signed is in the set. Used by
the trial harness to exercise the validator-rejected scenario.
"""

from __future__ import annotations

import os
from typing import Any

from dazzle.signing import SigningError


def _rejected_ids() -> set[str]:
    raw = os.environ.get("DAZZLE_QA_SIGNING_REJECT_IDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def validate_engagement_letter(*, entity: Any, row: Any) -> None:
    row_id = str(getattr(row, "id", ""))
    if row_id and row_id in _rejected_ids():
        raise SigningError("Signatory lacks authority to sign on behalf of this party")
