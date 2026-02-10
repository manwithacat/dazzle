"""Tests for the Story Wall handler (story get view=wall)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from dazzle.mcp.server.handlers.stories import wall_stories_handler


def _mock_story(story_id: str, title: str, actor: str, status: str = "accepted") -> MagicMock:
    """Create a mock StorySpec."""
    s = MagicMock()
    s.story_id = story_id
    s.title = title
    s.actor = actor
    s.status = MagicMock(value=status)
    s.scope = []
    return s


def _coverage_response(stories: list[dict[str, Any]] | None = None) -> str:
    """Mock stories_coverage_handler JSON output."""
    if stories is None:
        stories = [
            {"story_id": "ST-001", "title": "Login", "status": "covered"},
            {"story_id": "ST-002", "title": "Dashboard", "status": "partial"},
            {"story_id": "ST-003", "title": "Submit Order", "status": "covered"},
            {"story_id": "ST-004", "title": "Track Shipment", "status": "uncovered"},
        ]
    return json.dumps(
        {
            "total_stories": len(stories),
            "covered": sum(1 for s in stories if s["status"] == "covered"),
            "partial": sum(1 for s in stories if s["status"] == "partial"),
            "uncovered": sum(1 for s in stories if s["status"] == "uncovered"),
            "stories": stories,
        }
    )


MOCK_STORIES = [
    _mock_story("ST-001", "Login", "admin"),
    _mock_story("ST-002", "Dashboard", "admin"),
    _mock_story("ST-003", "Submit Order", "customer"),
    _mock_story("ST-004", "Track Shipment", "customer"),
]


class TestWallStoriesHandler:
    """Test the story wall handler."""

    @patch("dazzle.mcp.server.handlers.process.stories_coverage_handler")
    @patch("dazzle.core.stories_persistence.get_stories_by_status")
    def test_groups_by_coverage_status(
        self,
        mock_get: Any,
        mock_coverage: Any,
        tmp_path: Any,
    ) -> None:
        mock_get.return_value = MOCK_STORIES
        mock_coverage.return_value = _coverage_response()

        result = wall_stories_handler(tmp_path, {})
        data = json.loads(result)

        assert data["view"] == "wall"
        assert len(data["working"]) == 2  # ST-001, ST-003
        assert len(data["needs_polish"]) == 1  # ST-002
        assert len(data["not_started"]) == 1  # ST-004
        assert data["total"] == 4

    @patch("dazzle.mcp.server.handlers.process.stories_coverage_handler")
    @patch("dazzle.core.stories_persistence.get_stories_by_status")
    def test_filters_by_persona(
        self,
        mock_get: Any,
        mock_coverage: Any,
        tmp_path: Any,
    ) -> None:
        mock_get.return_value = MOCK_STORIES
        mock_coverage.return_value = _coverage_response()

        result = wall_stories_handler(tmp_path, {"persona": "admin"})
        data = json.loads(result)

        assert data["total"] == 2  # Only admin stories
        assert data["filtered_by"] == "admin"

    @patch("dazzle.mcp.server.handlers.process.stories_coverage_handler")
    @patch("dazzle.core.stories_persistence.get_stories_by_status")
    def test_lists_personas(
        self,
        mock_get: Any,
        mock_coverage: Any,
        tmp_path: Any,
    ) -> None:
        mock_get.return_value = MOCK_STORIES
        mock_coverage.return_value = _coverage_response()

        result = wall_stories_handler(tmp_path, {})
        data = json.loads(result)

        assert "admin" in data["personas"]
        assert "customer" in data["personas"]

    @patch("dazzle.mcp.server.handlers.process.stories_coverage_handler")
    @patch("dazzle.core.stories_persistence.get_stories_by_status")
    def test_markdown_output(
        self,
        mock_get: Any,
        mock_coverage: Any,
        tmp_path: Any,
    ) -> None:
        mock_get.return_value = MOCK_STORIES
        mock_coverage.return_value = _coverage_response()

        result = wall_stories_handler(tmp_path, {})
        data = json.loads(result)

        md = data["markdown"]
        assert "Story Wall" in md
        assert "Working (2)" in md
        assert "Needs polish (1)" in md
        assert "Not started (1)" in md
        assert "[ok] Login" in md
        assert "[..] Dashboard" in md
        assert "[  ] Track Shipment" in md

    @patch("dazzle.mcp.server.handlers.process.stories_coverage_handler")
    @patch("dazzle.core.stories_persistence.get_stories_by_status")
    def test_partial_persona_match(
        self,
        mock_get: Any,
        mock_coverage: Any,
        tmp_path: Any,
    ) -> None:
        mock_get.return_value = MOCK_STORIES
        mock_coverage.return_value = _coverage_response()

        result = wall_stories_handler(tmp_path, {"persona": "cust"})
        data = json.loads(result)

        # "cust" partially matches "customer"
        assert data["total"] == 2

    @patch("dazzle.mcp.server.handlers.process.stories_coverage_handler")
    @patch("dazzle.core.stories_persistence.get_stories_by_status")
    def test_no_stories(
        self,
        mock_get: Any,
        mock_coverage: Any,
        tmp_path: Any,
    ) -> None:
        mock_get.return_value = []
        mock_coverage.return_value = json.dumps({"total_stories": 0, "stories": []})

        result = wall_stories_handler(tmp_path, {})
        data = json.loads(result)

        assert data["total"] == 0
        assert len(data["working"]) == 0
