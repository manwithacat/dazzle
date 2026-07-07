"""Tests for the byte-access boundary static proof (#1551 task 7).

These tests are NOT marked e2e so they run on every CI push.
"""

from pathlib import Path

from dazzle.testing.byte_route_proof import find_byte_route_violations

REPO = Path(__file__).resolve().parents[2]


def test_main_tree_has_no_byte_route_violations():
    """Every stored-byte route in the real tree goes through serve_bytes.

    If this test goes RED, a route is self-building a streaming response
    outside the serve_bytes boundary. DO NOT loosen the walk or expand
    the ALLOWLIST to hide it — either fix the route to call serve_bytes
    (genuine bypass) or add an ALLOWLIST entry with a precise reason
    (legitimate non-storage streamer).
    """
    assert find_byte_route_violations(REPO) == []


def test_planted_bypass_is_detected(tmp_path: Path) -> None:
    """The proof correctly flags a route that bypasses serve_bytes."""
    routes = tmp_path / "src" / "dazzle" / "http" / "runtime"
    routes.mkdir(parents=True)
    (routes / "evil_routes.py").write_text(
        "from fastapi.responses import StreamingResponse\n"
        "async def h():\n    return StreamingResponse(open('x', 'rb'))\n"
    )
    violations = find_byte_route_violations(tmp_path)
    assert any("evil_routes.py" in v for v in violations)
