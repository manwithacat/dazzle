"""Tests for console route deprecation headers."""


def test_ops_routes_have_deprecation_header():
    """Ops routes should include X-Dazzle-Deprecated header."""
    from dazzle_back.runtime.ops_routes import DEPRECATION_HEADER_KEY, DEPRECATION_HEADER_VALUE

    assert DEPRECATION_HEADER_KEY == "X-Dazzle-Deprecated"
    assert "admin workspace" in DEPRECATION_HEADER_VALUE.lower()


def test_console_routes_have_deprecation_header():
    """Console routes should include X-Dazzle-Deprecated header."""
    from dazzle_back.runtime.console_routes import DEPRECATION_HEADER_KEY, DEPRECATION_HEADER_VALUE

    assert DEPRECATION_HEADER_KEY == "X-Dazzle-Deprecated"
    assert "admin workspace" in DEPRECATION_HEADER_VALUE.lower()
