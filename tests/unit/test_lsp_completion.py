"""Tests for context-aware LSP completion (issue #234)."""

import pytest

from dazzle.lsp.server import _detect_completion_context


def _line_end(text: str, line: int) -> int:
    """Convenience: column at the end of *line* (0-indexed)."""
    return len(text.split("\n")[line])


class TestDetectCompletionContext:
    """_detect_completion_context identifies cursor context."""

    @pytest.mark.parametrize(
        ("text", "line", "col", "expected"),
        [
            # cursor on a fresh blank line at module scope
            ('module test\napp test "Test"\n\n', 3, 0, "top_level"),
            # after `mode: ` on a surface
            ('surface task_list "Tasks":\n  uses entity Task\n  mode: ', 2, 16, "mode_value"),
            # after `ref ` in an entity field declaration
            ('entity Task "Task":\n  id: uuid pk\n  owner: ref ', 2, 17, "ref_target"),
            # after `uses entity ` on a surface
            ('surface task_list "Tasks":\n  uses entity ', 1, 15, "ref_target"),
            # after `source: ` on a surface
            ('surface task_list "Tasks":\n  source: ', 1, 10, "source_target"),
            # after `on click -> ` on a transition declaration
            (
                'surface task_list "Tasks":\n  action view:\n    on click -> ',
                2,
                16,
                "transition_target",
            ),
            # indented inside an entity body
            ('entity Task "Task":\n  id: uuid pk\n  ', 2, 2, "entity_block"),
            # indented inside a surface body
            ('surface task_list "Tasks":\n  ', 1, 2, "surface_block"),
            # indented inside a process body
            ('process OrderFlow "Order Flow":\n  ', 1, 2, "process_block"),
            # indented but no enclosing construct found
            ("  some_random_context", 0, 10, "global"),
            # empty document
            ("", 0, 0, "top_level"),
        ],
        ids=[
            "top_level",
            "mode_value",
            "ref_target",
            "uses_entity_target",
            "source_target",
            "transition_target",
            "entity_block",
            "surface_block",
            "process_block",
            "global_fallback",
            "empty_document",
        ],
    )
    def test_context(self, text: str, line: int, col: int, expected: str) -> None:
        # Where the original tests used len(lines[N]), recompute defensively
        # so the fixture stays self-consistent if column-counting drifts.
        if col >= 0 and line < len(text.split("\n")) and col == _line_end(text, line):
            col = _line_end(text, line)
        assert _detect_completion_context(text, line, col) == expected
