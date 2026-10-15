"""
Tests for unified the Dazzle runtime server.

Tests the unified development server that runs a single FastAPI app
with both backend API and server-rendered UI on one port.
"""

import inspect

import pytest

from dazzle.http.runtime.combined_server import (
    _clickable_url,
    run_backend_only,
    run_unified_server,
)

# =============================================================================
# Terminal hyperlinks (OSC 8)
# =============================================================================


@pytest.mark.parametrize(
    ("env", "label", "expected"),
    [
        # Fallback: NO_COLOR, no TERM or TERM=dumb print plain text.
        pytest.param({"NO_COLOR": "1", "TERM": "xterm-256color"}, None, "http://x", id="no-color"),
        pytest.param({}, None, "http://x", id="no-term"),
        pytest.param({"TERM": "dumb"}, None, "http://x", id="term-dumb"),
        pytest.param({}, "my app", "my app", id="fallback-uses-label"),
        pytest.param(
            {"TERM": "xterm-256color"},
            "my app",
            "\x1b]8;;http://x\x1b\\my app\x1b]8;;\x1b\\",
            id="capable-terminal-emits-osc8",
        ),
    ],
)
def test_clickable_url(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], label: str | None, expected: str
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert _clickable_url("http://x", label) == expected


# =============================================================================
# Server entry-point signatures
# =============================================================================


@pytest.mark.parametrize(
    ("fn", "expected"),
    [
        pytest.param(
            run_unified_server,
            {
                "appspec",
                "port",
                "enable_test_mode",
                "enable_dev_mode",
                "enable_auth",
                "auth_config",
                "host",
                "project_root",
                "personas",
                "scenarios",
                "sitespec_data",
                "theme_preset",
                "theme_overrides",
                "redis_url",
                "config",
                "local_assets",
                "storage_defs",
                "tenant_config",
                "workers",
                "dark_mode_toggle",  # #1445 slice 3 — threaded to the typed render context
            },
            id="run_unified_server",
        ),
        pytest.param(
            run_backend_only,
            {
                "appspec",
                "host",
                "port",
                "enable_test_mode",
                "enable_dev_mode",
                "enable_auth",
                "auth_config",
                "sitespec_data",
                "project_root",
                "redis_url",
                "storage_defs",
                "workers",
            },
            id="run_backend_only",
        ),
    ],
)
def test_entry_point_parameters(fn: object, expected: set[str]) -> None:
    assert set(inspect.signature(fn).parameters) == expected  # type: ignore[arg-type]


def test_unified_server_binds_localhost_3000_by_default() -> None:
    params = inspect.signature(run_unified_server).parameters
    assert (params["host"].default, params["port"].default) == ("127.0.0.1", 3000)


def test_old_combined_server_not_exported() -> None:
    """DNRCombinedHandler / DNRCombinedServer / run_combined_server are removed."""
    import dazzle.page.runtime as mod

    assert not hasattr(mod, "DNRCombinedHandler")
    assert not hasattr(mod, "DNRCombinedServer")
    assert not hasattr(mod, "run_combined_server")
    assert not hasattr(mod, "run_frontend_only")
