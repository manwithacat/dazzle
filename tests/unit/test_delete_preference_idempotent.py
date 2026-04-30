"""Tests for #971 — DELETE /auth/preferences/{key} idempotent semantics.

Per RFC 7231 §4.3.5, DELETE is idempotent. Repeating the same DELETE
should produce the same observable side effect (the resource is absent).
The HTTP convention is 204 No Content for both "deleted just now" and
"already absent" — clients shouldn't have to distinguish the two.

Pre-#971 the handler raised 404 when the key didn't exist, breaking
idempotency.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES = REPO_ROOT / "src" / "dazzle_back" / "runtime" / "auth" / "routes.py"


def test_delete_preference_returns_204_response() -> None:
    """The handler must return Response(status_code=204), not a dict + 404."""
    src = ROUTES.read_text()
    # Locate the function body.
    start = src.find("async def _delete_preference(")
    assert start >= 0, "missing _delete_preference handler"
    # End at the next `async def` or the next top-level `def`.
    end = src.find("\n\nasync def ", start + 1)
    if end < 0:
        end = src.find("\n\ndef ", start + 1)
    assert end > start
    body = src[start:end]
    assert "Response(status_code=204)" in body, (
        "_delete_preference must return Response(status_code=204) — "
        "DELETE is idempotent per RFC 7231 §4.3.5 (#971)."
    )


def test_delete_preference_does_not_raise_404() -> None:
    """The handler must not raise HTTPException(404) for missing keys."""
    src = ROUTES.read_text()
    start = src.find("async def _delete_preference(")
    end = src.find("\n\nasync def ", start + 1)
    if end < 0:
        end = src.find("\n\ndef ", start + 1)
    body = src[start:end]
    # Tolerate "404" appearing in a comment that explains the prior
    # behaviour, but the actual raise must be gone.
    assert "raise HTTPException(status_code=404" not in body, (
        "_delete_preference must not raise 404 — DELETE is idempotent. "
        "If the key is absent, return 204 anyway (#971)."
    )
