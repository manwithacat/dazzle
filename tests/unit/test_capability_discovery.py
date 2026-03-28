"""Tests for capability discovery engine and rule modules."""

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
