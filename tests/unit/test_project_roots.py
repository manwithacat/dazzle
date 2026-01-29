"""Tests for MCP roots-based project resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.mcp.server.state import (
    _roots_cache,
    resolve_project_path_from_roots,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the roots cache before each test."""
    _roots_cache.clear()
    yield
    _roots_cache.clear()


def _make_root(uri: str) -> MagicMock:
    root = MagicMock()
    root.uri = uri
    return root


def _make_session(root_uris: list[str]) -> AsyncMock:
    session = AsyncMock()
    roots_result = MagicMock()
    roots_result.roots = [_make_root(uri) for uri in root_uris]
    session.list_roots.return_value = roots_result
    return session


@pytest.mark.asyncio
async def test_explicit_path_takes_priority(tmp_path: Path):
    """Explicit project_path bypasses roots resolution."""
    project = tmp_path / "myproject"
    project.mkdir()
    (project / "dazzle.toml").write_text("")

    session = _make_session(["file:///other/path"])

    result = await resolve_project_path_from_roots(session, str(project))

    assert result == project
    session.list_roots.assert_not_called()


@pytest.mark.asyncio
async def test_root_with_dazzle_toml_is_used(tmp_path: Path):
    """A root containing dazzle.toml is selected."""
    project = tmp_path / "cyfuture"
    project.mkdir()
    (project / "dazzle.toml").write_text("")

    uri = project.as_uri()
    session = _make_session([uri])

    result = await resolve_project_path_from_roots(session)

    assert result == project
    session.list_roots.assert_awaited_once()


@pytest.mark.asyncio
async def test_root_without_dazzle_toml_falls_back(tmp_path: Path):
    """A root without dazzle.toml falls back to default resolution."""
    no_project = tmp_path / "nope"
    no_project.mkdir()

    uri = no_project.as_uri()
    session = _make_session([uri])

    # Should not raise — falls back to resolve_project_path(None)
    result = await resolve_project_path_from_roots(session)
    assert result is not None  # falls back to project root


@pytest.mark.asyncio
async def test_list_roots_exception_falls_back():
    """If list_roots() raises, fall back gracefully."""
    session = AsyncMock()
    session.list_roots.side_effect = Exception("not supported")

    result = await resolve_project_path_from_roots(session)
    assert result is not None  # falls back to project root


@pytest.mark.asyncio
async def test_caching_avoids_repeated_filesystem_checks(tmp_path: Path):
    """Second call with same roots uses cached result."""
    project = tmp_path / "cached"
    project.mkdir()
    (project / "dazzle.toml").write_text("")

    uri = project.as_uri()
    session = _make_session([uri])

    result1 = await resolve_project_path_from_roots(session)
    # Remove dazzle.toml — cached result should still return project
    (project / "dazzle.toml").unlink()
    result2 = await resolve_project_path_from_roots(session)

    assert result1 == result2 == project


@pytest.mark.asyncio
async def test_first_matching_root_wins(tmp_path: Path):
    """When multiple roots have dazzle.toml, the first one wins."""
    proj_a = tmp_path / "a"
    proj_a.mkdir()
    (proj_a / "dazzle.toml").write_text("")

    proj_b = tmp_path / "b"
    proj_b.mkdir()
    (proj_b / "dazzle.toml").write_text("")

    session = _make_session([proj_a.as_uri(), proj_b.as_uri()])

    result = await resolve_project_path_from_roots(session)
    assert result == proj_a
