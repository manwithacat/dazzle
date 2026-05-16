"""Pure dataclass for one ``onboarding_state`` row (v0.71.3).

Extracted from ``back/runtime/onboarding/state_repository`` so the
render + resolver layers can construct + read these values without
importing the DB-bound repository.

The repository in ``back/`` still hydrates instances of this class
from psycopg rows; the type lives here so the UI layer can pass
it around without violating the import boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OnboardingProgress:
    """In-memory view of one ``onboarding_state`` row."""

    id: str
    user_id: str
    guide_name: str
    guide_version: int
    current_step: str | None
    completed_steps: list[str] = field(default_factory=list)
    dismissed_steps: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
