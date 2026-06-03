"""Phase 1 of the declarative-CSRF spec: the token is session-bound."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from dazzle.back.runtime.auth.models import SessionRecord


def _session() -> SessionRecord:
    return SessionRecord(
        user_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


class TestSessionRecordCsrfSecret:
    def test_session_record_has_csrf_secret(self) -> None:
        s = _session()
        assert isinstance(s.csrf_secret, str) and len(s.csrf_secret) >= 32

    def test_csrf_secret_is_unique_per_session(self) -> None:
        assert _session().csrf_secret != _session().csrf_secret
