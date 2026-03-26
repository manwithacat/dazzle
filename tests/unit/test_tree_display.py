"""Tests for tree/hierarchy workspace region display mode (#565)."""

import textwrap
from pathlib import Path

from dazzle.core.ir.workspaces import DisplayMode
from dazzle.core.lexer import Lexer, TokenType
from dazzle.core.parser import parse_dsl
from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP


class TestDisplayModeTree:
    """DisplayMode enum includes TREE."""

    def test_tree_member_exists(self) -> None:
        assert DisplayMode.TREE == "tree"

    def test_tree_from_value(self) -> None:
        assert DisplayMode("tree") is DisplayMode.TREE


class TestLexerTreeToken:
    """Lexer recognises the 'tree' keyword."""

    def test_tree_keyword(self) -> None:
        lexer = Lexer("tree", Path("test.dz"))
        tokens = lexer.tokenize()
        kw_tokens = [t for t in tokens if t.type not in (TokenType.NEWLINE, TokenType.EOF)]
        assert len(kw_tokens) >= 1
        assert kw_tokens[0].type == TokenType.TREE


class TestTemplateMap:
    """DISPLAY_TEMPLATE_MAP includes TREE."""

    def test_tree_template_mapping(self) -> None:
        assert "TREE" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["TREE"] == "workspace/regions/tree.html"


class TestParserTree:
    """Parser handles display: tree with group_by for parent reference."""

    def test_parse_tree_region(self) -> None:
        dsl = textwrap.dedent("""\
            module test_app
            app test "Test"

            entity Department "Department":
              id: uuid pk
              name: str(200) required
              parent_department: ref Department

            workspace org_chart "Organisation Chart":
              departments:
                source: Department
                display: tree
                group_by: parent_department
        """)
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dz"))
        ws = fragment.workspaces[0]
        region = ws.regions[0]
        assert region.display == DisplayMode.TREE
        assert region.group_by == "parent_department"
        assert region.source == "Department"

    def test_parse_tree_without_group_by(self) -> None:
        dsl = textwrap.dedent("""\
            module test_app
            app test "Test"

            entity Category "Category":
              id: uuid pk
              name: str(200) required

            workspace cats "Categories":
              all_cats:
                source: Category
                display: tree
        """)
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dz"))
        region = fragment.workspaces[0].regions[0]
        assert region.display == DisplayMode.TREE
        assert region.group_by is None


class TestTreeBuilder:
    """Tree-building logic produces correct nested structure from flat items."""

    def _build_tree(self, items: list[dict], group_by: str) -> list[dict]:
        """Replicate the tree-building logic from workspace_rendering.py."""
        items_by_id = {str(item.get("id", "")): item for item in items}
        children_map: dict[str, list] = {}
        for item in items:
            parent_id = str(item.get(group_by, "") or "")
            children_map.setdefault(parent_id, []).append(item)

        roots = [item for item in items if str(item.get(group_by, "") or "") not in items_by_id]

        def _build_subtree(node: dict) -> dict:
            node_id = str(node.get("id", ""))
            node["_children"] = children_map.get(node_id, [])
            for child in node["_children"]:
                _build_subtree(child)
            return node

        return [_build_subtree(r) for r in roots]

    def test_simple_hierarchy(self) -> None:
        items = [
            {"id": "1", "name": "Root", "parent_department": None},
            {"id": "2", "name": "Child A", "parent_department": "1"},
            {"id": "3", "name": "Child B", "parent_department": "1"},
        ]
        tree = self._build_tree(items, "parent_department")
        assert len(tree) == 1
        root = tree[0]
        assert root["name"] == "Root"
        assert len(root["_children"]) == 2
        child_names = {c["name"] for c in root["_children"]}
        assert child_names == {"Child A", "Child B"}

    def test_nested_hierarchy(self) -> None:
        items = [
            {"id": "1", "name": "Root", "parent": None},
            {"id": "2", "name": "Mid", "parent": "1"},
            {"id": "3", "name": "Leaf", "parent": "2"},
        ]
        tree = self._build_tree(items, "parent")
        assert len(tree) == 1
        root = tree[0]
        assert root["name"] == "Root"
        assert len(root["_children"]) == 1
        mid = root["_children"][0]
        assert mid["name"] == "Mid"
        assert len(mid["_children"]) == 1
        assert mid["_children"][0]["name"] == "Leaf"
        assert mid["_children"][0]["_children"] == []

    def test_multiple_roots(self) -> None:
        items = [
            {"id": "1", "name": "Root A", "parent": None},
            {"id": "2", "name": "Root B", "parent": ""},
            {"id": "3", "name": "Child of A", "parent": "1"},
        ]
        tree = self._build_tree(items, "parent")
        assert len(tree) == 2
        root_names = {t["name"] for t in tree}
        assert root_names == {"Root A", "Root B"}

    def test_empty_items(self) -> None:
        tree = self._build_tree([], "parent")
        assert tree == []

    def test_flat_items_no_parent(self) -> None:
        """All items are roots when no parent references match."""
        items = [
            {"id": "1", "name": "A", "parent": None},
            {"id": "2", "name": "B", "parent": None},
        ]
        tree = self._build_tree(items, "parent")
        assert len(tree) == 2
        for node in tree:
            assert node["_children"] == []
