"""Tests for context-aware LSP completion (issue #234)."""

from __future__ import annotations


class TestDetectCompletionContext:
    """_detect_completion_context identifies cursor context."""

    def test_top_level(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'module test\napp test "Test"\n\n'
        assert _detect_completion_context(text, 3, 0) == "top_level"

    def test_mode_value(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'surface task_list "Tasks":\n  uses entity Task\n  mode: '
        lines = text.split("\n")
        assert _detect_completion_context(text, 2, len(lines[2])) == "mode_value"

    def test_ref_target(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'entity Task "Task":\n  id: uuid pk\n  owner: ref '
        lines = text.split("\n")
        assert _detect_completion_context(text, 2, len(lines[2])) == "ref_target"

    def test_uses_entity_target(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'surface task_list "Tasks":\n  uses entity '
        lines = text.split("\n")
        assert _detect_completion_context(text, 1, len(lines[1])) == "ref_target"

    def test_source_target(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'surface task_list "Tasks":\n  source: '
        lines = text.split("\n")
        assert _detect_completion_context(text, 1, len(lines[1])) == "source_target"

    def test_transition_target(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'surface task_list "Tasks":\n  action view:\n    on click -> '
        lines = text.split("\n")
        assert _detect_completion_context(text, 2, len(lines[2])) == "transition_target"

    def test_entity_block(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'entity Task "Task":\n  id: uuid pk\n  '
        assert _detect_completion_context(text, 2, 2) == "entity_block"

    def test_surface_block(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'surface task_list "Tasks":\n  '
        assert _detect_completion_context(text, 1, 2) == "surface_block"

    def test_process_block(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        text = 'process OrderFlow "Order Flow":\n  '
        assert _detect_completion_context(text, 1, 2) == "process_block"

    def test_global_fallback(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        # Indented but no enclosing construct found
        text = "  some_random_context"
        assert _detect_completion_context(text, 0, 10) == "global"

    def test_empty_document(self) -> None:
        from dazzle.lsp.server import _detect_completion_context

        assert _detect_completion_context("", 0, 0) == "top_level"
