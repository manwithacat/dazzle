"""Tests for LSP document symbol positions (issue #233)."""

from __future__ import annotations


class TestScanDocumentSymbols:
    """_scan_document_symbols finds constructs with correct positions."""

    def test_entity_position(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = 'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 1
        sym = symbols[0]
        assert sym.name == "Task"
        assert sym.range.start.line == 0
        assert sym.detail == "entity — Task"

    def test_entity_selection_range_highlights_name(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = 'entity Task "Task":\n  id: uuid pk\n'
        symbols = _scan_document_symbols(text)
        sym = symbols[0]
        # "entity " is 7 chars, "Task" starts at col 7
        assert sym.selection_range.start.character == 7
        assert sym.selection_range.end.character == 11

    def test_entity_range_spans_to_next_construct(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = (
            'entity Task "Task":\n'
            "  id: uuid pk\n"
            "  title: str(200)\n"
            "\n"
            'entity User "User":\n'
            "  id: uuid pk\n"
        )
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 2
        # Task should end at line 3 (the blank line before User)
        assert symbols[0].range.end.line == 3
        # User starts at line 4
        assert symbols[1].range.start.line == 4

    def test_surface_symbol(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = 'surface task_list "Task List":\n  uses entity Task\n  mode: list\n'
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 1
        assert symbols[0].name == "task_list"
        assert symbols[0].detail == "surface — Task List"
        assert symbols[0].range.start.line == 0

    def test_process_symbol(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = 'process OrderFulfillment "Order Fulfillment":\n  state pending:\n    on submit -> processing\n'
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 1
        assert symbols[0].name == "OrderFulfillment"

    def test_children_detected(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = (
            'surface task_list "Tasks":\n'
            "  uses entity Task\n"
            "  mode: list\n"
            '  section main "Main":\n'
            '    field title "Title"\n'
            '    field status "Status"\n'
            '  action create "New":\n'
            "    on click -> surface task_create\n"
        )
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 1
        children = symbols[0].children
        assert children is not None
        assert len(children) == 4  # section, 2 fields, action
        assert children[0].name == "main"
        assert children[0].detail == "section — Main"
        assert children[1].name == "title"
        assert children[2].name == "status"
        assert children[3].name == "create"

    def test_entity_fields_as_children(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = 'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n  status: enum[draft,done]\n'
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 1
        children = symbols[0].children
        assert children is not None
        # 'id' is excluded (common infrastructure field), title and status are fields
        names = [c.name for c in children]
        assert "title" in names
        assert "status" in names

    def test_multiple_construct_types(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = (
            'entity Task "Task":\n'
            "  id: uuid pk\n"
            "\n"
            'view TaskListView "Task List View":\n'
            "  source: Task\n"
            "\n"
            'ledger Revenue "Revenue":\n'
            "  account_code: 1001\n"
        )
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 3
        assert symbols[0].name == "Task"
        assert symbols[1].name == "TaskListView"
        assert symbols[2].name == "Revenue"

    def test_empty_document(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        assert _scan_document_symbols("") == []
        assert _scan_document_symbols("# just a comment\n") == []

    def test_child_positions_are_correct(self) -> None:
        from dazzle.lsp.server import _scan_document_symbols

        text = 'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'
        symbols = _scan_document_symbols(text)
        children = symbols[0].children or []
        # title is on line 2 (0-indexed)
        title_children = [c for c in children if c.name == "title"]
        assert len(title_children) == 1
        assert title_children[0].range.start.line == 2

    def test_no_appspec_needed(self) -> None:
        """Document symbols should work even without a loaded AppSpec."""
        from dazzle.lsp.server import _scan_document_symbols

        # This is pure text scanning — no IR needed
        text = 'entity Foo "Foo":\n  bar: str(100)\n'
        symbols = _scan_document_symbols(text)
        assert len(symbols) == 1
