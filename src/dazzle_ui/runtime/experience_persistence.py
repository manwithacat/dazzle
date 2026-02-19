"""
Experience flow progress persistence.

Saves and loads experience flow progress to JSON files in `.dazzle/experience_progress/`.
This allows users to resume multi-step flows after cookie expiry, browser close,
or agent takeover scenarios.

File key: ``{experience_name}.json`` (single-user) or
``{experience_name}_{user_hash}.json`` (multi-user with auth).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_PROGRESS_DIR = "experience_progress"

# Progress records expire after 7 days of inactivity
_MAX_AGE_SECONDS = 7 * 24 * 3600


class ExperienceProgress(BaseModel):
    """Durable record of experience flow progress."""

    experience_name: str
    current_step: str
    completed_steps: list[str] = Field(default_factory=list)
    step_data: dict[str, Any] = Field(default_factory=dict)
    started_at: float = Field(default_factory=time.time)
    last_activity: float = Field(default_factory=time.time)
    user_email: str = ""


class ExperienceProgressStore:
    """File-based experience progress persistence.

    Stores progress as JSON files under ``{project_root}/.dazzle/experience_progress/``.

    Args:
        project_root: Root directory of the Dazzle project.
    """

    def __init__(self, project_root: Path) -> None:
        self._dir = project_root / ".dazzle" / _PROGRESS_DIR

    def _progress_path(self, experience_name: str, user_email: str = "") -> Path:
        """Compute the file path for a progress record."""
        if user_email:
            user_hash = hashlib.sha256(user_email.encode()).hexdigest()[:12]
            filename = f"{experience_name}_{user_hash}.json"
        else:
            filename = f"{experience_name}.json"
        return self._dir / filename

    def save(self, progress: ExperienceProgress) -> None:
        """Save progress to disk.

        Creates the progress directory if it doesn't exist.
        Updates ``last_activity`` to the current time.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        progress = progress.model_copy(update={"last_activity": time.time()})
        path = self._progress_path(progress.experience_name, progress.user_email)
        path.write_text(progress.model_dump_json(indent=2))
        logger.debug("Saved experience progress: %s", path.name)

    def load(self, experience_name: str, user_email: str = "") -> ExperienceProgress | None:
        """Load progress from disk.

        Returns:
            ExperienceProgress if found and not expired, None otherwise.
        """
        path = self._progress_path(experience_name, user_email)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            progress = ExperienceProgress.model_validate(data)
        except Exception:
            logger.warning("Corrupt experience progress file: %s", path.name)
            path.unlink(missing_ok=True)
            return None

        # Check expiry
        if time.time() - progress.last_activity > _MAX_AGE_SECONDS:
            logger.debug("Experience progress expired: %s", path.name)
            path.unlink(missing_ok=True)
            return None

        return progress

    def delete(self, experience_name: str, user_email: str = "") -> None:
        """Delete a progress record (e.g. on flow completion)."""
        path = self._progress_path(experience_name, user_email)
        if path.exists():
            path.unlink()
            logger.debug("Deleted experience progress: %s", path.name)
