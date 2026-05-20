"""Tests for capability discovery engine and rule modules."""

from pathlib import Path

from dazzle.core.discovery.models import ExampleRef, Relevance


class TestModels:
    def test_example_ref_is_frozen(self):
        ref = ExampleRef(
            app="project_tracker",
            file="dsl/app.dsl",
            line=152,
            context='field description "Description" widget=rich_text',
        )
        assert ref.app == "project_tracker"
        assert ref.file == "dsl/app.dsl"
        assert ref.line == 152

    def test_relevance_is_frozen(self):
        ref = ExampleRef(app="pt", file="dsl/app.dsl", line=1, context="example")
        rel = Relevance(
            context="field 'description' (text) on surface 'task_create'",
            capability="widget=rich_text",
            category="widget",
            examples=[ref],
            kg_entity="capability:widget_rich_text",
        )
        assert rel.capability == "widget=rich_text"
        assert rel.category == "widget"
        assert len(rel.examples) == 1
        assert rel.kg_entity == "capability:widget_rich_text"

    def test_relevance_with_empty_examples(self):
        rel = Relevance(
            context="field 'desc' (text)",
            capability="widget=rich_text",
            category="widget",
            examples=[],
            kg_entity="capability:widget_rich_text",
        )
        assert rel.examples == []


class TestLintIntegration:
    """Test that lint_appspec returns relevance as a third tuple element."""

    def test_lint_appspec_returns_three_tuple(self, tmp_path: Path):
        from dazzle.core.linker import build_appspec
        from dazzle.core.lint import lint_appspec
        from dazzle.core.parser import parse_modules

        dsl_file = tmp_path / "app.dsl"
        dsl_file.write_text(
            """
module test_lint.core

app test_lint "Test Lint Integration"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text

surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field title "Title"
    field description "Description"
"""
        )

        modules = parse_modules([dsl_file])
        appspec = build_appspec(modules, "test_lint.core")

        result = lint_appspec(appspec)
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"
        errors, warnings, relevance = result
        assert isinstance(errors, list)
        assert isinstance(warnings, list)
        assert isinstance(relevance, list)

    def test_lint_appspec_relevance_items_are_relevance_type(self, tmp_path: Path):
        from dazzle.core.linker import build_appspec
        from dazzle.core.lint import lint_appspec
        from dazzle.core.parser import parse_modules

        dsl_file = tmp_path / "app.dsl"
        dsl_file.write_text(
            """
module test_rel.core

app test_rel "Test Relevance"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text

surface task_create "Create Task":
  uses entity Task
  mode: create

  section main "New Task":
    field title "Title"
    field description "Description"
"""
        )

        modules = parse_modules([dsl_file])
        appspec = build_appspec(modules, "test_rel.core")

        _errors, _warnings, relevance = lint_appspec(appspec)
        for item in relevance:
            assert isinstance(item, Relevance)

    def test_lint_appspec_suggest_false_skips_capability_discovery(self, tmp_path: Path):
        """`suggest=False` skips `suggest_capabilities` — that pass parses
        every bundled example app's DSL, pure overhead for the serve-boot
        validation path (#1168). `relevance` comes back empty."""
        from unittest.mock import patch

        from dazzle.core.linker import build_appspec
        from dazzle.core.lint import lint_appspec
        from dazzle.core.parser import parse_modules

        dsl_file = tmp_path / "app.dsl"
        dsl_file.write_text(
            'module t.core\n\napp t "T"\n\nentity Task "Task":\n'
            "  id: uuid pk\n  title: str(200) required\n"
        )
        appspec = build_appspec(parse_modules([dsl_file]), "t.core")

        with patch("dazzle.core.lint.suggest_capabilities") as spy:
            _errors, _warnings, relevance = lint_appspec(appspec, suggest=False)

        spy.assert_not_called()
        assert relevance == []

    def test_lint_appspec_suggest_true_is_the_default(self, tmp_path: Path):
        """The default path still computes capability suggestions, so
        `dazzle lint` keeps its hints."""
        from unittest.mock import patch

        from dazzle.core.linker import build_appspec
        from dazzle.core.lint import lint_appspec
        from dazzle.core.parser import parse_modules

        dsl_file = tmp_path / "app.dsl"
        dsl_file.write_text(
            'module t.core\n\napp t "T"\n\nentity Task "Task":\n'
            "  id: uuid pk\n  title: str(200) required\n"
        )
        appspec = build_appspec(parse_modules([dsl_file]), "t.core")

        with patch("dazzle.core.lint.suggest_capabilities", return_value=[]) as spy:
            lint_appspec(appspec)

        spy.assert_called_once()
