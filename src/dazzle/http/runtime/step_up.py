"""Second-factor freshness and the step-up URL (DD-014).

A leaf module (no auth imports) so the state-machine guard
(``guard: session.second_factor``) and the auth step-up API
(``require_second_factor``) share one predicate and one URL without an import
cycle: ``dazzle.http.runtime.auth`` already imports the state machine.
"""

from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

STEP_UP_PATH = "/2fa/step-up"


def second_factor_fresh(
    verified_at: datetime | None,
    max_age_seconds: int | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    """True when a second factor was completed, and within ``max_age_seconds`` if given."""
    if verified_at is None:
        return False
    if max_age_seconds is None:
        return True
    age = ((now or datetime.now(UTC)) - verified_at).total_seconds()
    return age <= max_age_seconds


def step_up_url(next_path: str = "") -> str:
    """The step-up page, returning to ``next_path`` when it is a same-site path."""
    parts = urlsplit(next_path or "")
    same_site = (
        next_path.startswith("/")
        and not next_path.startswith("//")
        and not parts.scheme
        and not parts.netloc
        and "\\" not in next_path
    )
    if not same_site:
        return STEP_UP_PATH
    return f"{STEP_UP_PATH}?next={quote(next_path, safe='/')}"
