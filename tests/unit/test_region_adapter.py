"""WorkspaceRegionAdapter tests (Phase 4A)."""

import pytest

from dazzle.render.fragment import KanbanBoard, Region, Surface
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle_back.runtime.renderers.region_adapter import WorkspaceRegionAdapter


class _FakeRegion:
    """Lightweight WorkspaceRegion stub — we only consult `display`,
    `title`, `name`, and `empty_message`. The real WorkspaceRegion
    has ~20 fields; for unit tests we duck-type."""

    def __init__(
        self,
        name: str,
        display: str = "",
        title: str | None = None,
        empty_message: str | None = None,
    ) -> None:
        self.name = name
        self.title = title
        self.display = display
        self.empty_message = empty_message


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── Dispatch ────────────────────────


def test_unsupported_display_raises_with_actionable_hint() -> None:
    """Bar chart isn't wired yet — raises NotImplementedError with a
    pointer at the audit's aggregated_blockers report."""
    adapter = WorkspaceRegionAdapter()
    with pytest.raises(NotImplementedError, match="bar_chart"):
        adapter.build(_FakeRegion("r", display="bar_chart"), {})


def test_empty_display_routes_to_list_path() -> None:
    """Default display (empty string) is the list view."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("task_list", title="Tasks"),
        {"items": [], "columns": []},
    )
    assert isinstance(fragment, Surface)
    region = fragment.body
    assert isinstance(region, Region)
    assert region.kind == "list"


def test_explicit_list_display_routes_to_list_path() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("r", display="list"),
        {"items": [], "columns": []},
    )
    assert isinstance(fragment, Surface)
    assert fragment.body.kind == "list"


# ───────────────── Kanban ─────────────────────────


def test_kanban_with_items_grouped_into_columns() -> None:
    """Items bucket by `group_by_field`; declared `group_keys` set the
    column order."""
    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion("task_board", display="kanban", title="Task Board")
    ctx = {
        "items": [
            {"id": "1", "title": "Buy milk", "status": "todo"},
            {"id": "2", "title": "Walk dog", "status": "doing"},
            {"id": "3", "title": "Read book", "status": "todo"},
            {"id": "4", "title": "Stretch", "status": "done"},
        ],
        "group_keys": ["todo", "doing", "done"],
        "group_by_field": "status",
    }
    fragment = adapter.build(region, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "kanban"
    board = fragment.body.body
    assert isinstance(board, KanbanBoard)
    by_key = dict(board.columns)
    assert list(by_key.keys()) == ["todo", "doing", "done"]
    assert len(by_key["todo"]) == 2
    assert len(by_key["doing"]) == 1
    assert len(by_key["done"]) == 1


def test_kanban_unknown_group_keys_go_to_other_column() -> None:
    """Items grouped under a key not in `group_keys` collect under
    a synthetic 'Other' column at the end."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {"id": "1", "title": "X", "status": "blocked"},  # not in keys
            {"id": "2", "title": "Y", "status": "todo"},
        ],
        "group_keys": ["todo", "doing"],
        "group_by_field": "status",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban"), ctx)
    board = fragment.body.body
    by_key = dict(board.columns)
    assert "Other" in by_key
    assert len(by_key["Other"]) == 1
    assert len(by_key["todo"]) == 1


def test_kanban_empty_columns_still_render() -> None:
    """A column with declared group_key but zero items still renders
    as an empty column — important UX so authors can see all states
    even when none have items today."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"id": "1", "title": "X", "status": "todo"}],
        "group_keys": ["todo", "doing", "done"],
        "group_by_field": "status",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban"), ctx)
    board = fragment.body.body
    by_key = dict(board.columns)
    assert by_key["doing"] == ()
    assert by_key["done"] == ()


def test_kanban_no_items_renders_empty_state_or_minimal_board() -> None:
    """Edge case: no items AND no group_keys — empty state."""
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("b", display="kanban", empty_message="No tasks yet."),
        {},
    )
    # Surface body is a Region containing either EmptyState or a
    # placeholder KanbanBoard — both are acceptable; what matters
    # is no crash and meaningful output.
    html = _render(fragment)
    # One of these strings should appear
    assert "No tasks yet." in html or "All" in html or "dz-kanban" in html


# ───────────────── End-to-end render ──────────────


def test_kanban_renders_to_html_with_dz_kanban_marker() -> None:
    """Rendered output carries the `dz-kanban` CSS hook so workspace
    layout CSS can target the kanban column structure."""
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"id": "1", "title": "Buy milk", "status": "todo"}],
        "group_keys": ["todo", "doing", "done"],
        "group_by_field": "status",
    }
    fragment = adapter.build(_FakeRegion("b", display="kanban", title="Tasks"), ctx)
    html = _render(fragment)
    assert "dz-kanban" in html
    assert "Tasks" in html
    assert "Buy milk" in html


def test_list_renders_with_table() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"name": "Alice"}, {"name": "Bob"}],
        "columns": [{"key": "name", "label": "Name"}],
    }
    fragment = adapter.build(_FakeRegion("users", display="list"), ctx)
    html = _render(fragment)
    assert "<table" in html
    assert "Alice" in html
    assert "Bob" in html


def test_list_empty_renders_empty_state() -> None:
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(
        _FakeRegion("users", display="list", empty_message="No users."),
        {"items": [], "columns": []},
    )
    html = _render(fragment)
    assert "No users." in html
