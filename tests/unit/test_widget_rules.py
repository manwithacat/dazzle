"""Tests for widget annotation relevance rules.

Covers all six rules plus edge-cases (already annotated, wrong mode).
"""

from dazzle.core.discovery.widget_rules import check_widget_relevance
from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.surfaces import (
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field(name: str, kind: FieldTypeKind, **kwargs) -> FieldSpec:
    """Create a minimal FieldSpec."""
    return FieldSpec(name=name, type=FieldType(kind=kind, **kwargs))


def _entity(name: str, fields: list[FieldSpec]) -> EntitySpec:
    """Create a minimal EntitySpec."""
    return EntitySpec(name=name, fields=fields)


def _surface(
    name: str,
    entity_ref: str,
    mode: SurfaceMode,
    elements: list[SurfaceElement],
) -> SurfaceSpec:
    """Create a minimal SurfaceSpec with a single section."""
    section = SurfaceSection(name="main", elements=elements)
    return SurfaceSpec(name=name, entity_ref=entity_ref, mode=mode, sections=[section])


def _element(field_name: str, options: dict | None = None) -> SurfaceElement:
    return SurfaceElement(field_name=field_name, options=options or {})


# ---------------------------------------------------------------------------
# Rule tests
# ---------------------------------------------------------------------------


class TestWidgetRules:
    """Rule: text field without widget → widget=rich_text."""

    def test_text_field_without_widget_returns_rich_text(self):
        entity = _entity("Post", [_field("body", FieldTypeKind.TEXT)])
        surface = _surface("post_create", "Post", SurfaceMode.CREATE, [_element("body")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        r = results[0]
        assert r.capability == "widget=rich_text"
        assert r.category == "widget"
        assert r.kg_entity == "capability:widget_rich_text"
        assert "body" in r.context
        assert "post_create" in r.context

    def test_ref_field_without_widget_no_source_returns_combobox(self):
        entity = _entity(
            "Task",
            [_field("assignee", FieldTypeKind.REF, ref_entity="User")],
        )
        surface = _surface("task_edit", "Task", SurfaceMode.EDIT, [_element("assignee")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=combobox"
        assert results[0].kg_entity == "capability:widget_combobox"

    def test_ref_field_with_source_option_no_relevance(self):
        entity = _entity(
            "Task",
            [_field("assignee", FieldTypeKind.REF, ref_entity="User")],
        )
        surface = _surface(
            "task_edit",
            "Task",
            SurfaceMode.EDIT,
            [_element("assignee", options={"source": "/api/users"})],
        )
        results = check_widget_relevance([entity], [surface])
        assert results == []

    def test_date_field_without_widget_returns_picker(self):
        entity = _entity("Event", [_field("starts_on", FieldTypeKind.DATE)])
        surface = _surface("event_create", "Event", SurfaceMode.CREATE, [_element("starts_on")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=picker"
        assert results[0].kg_entity == "capability:widget_picker"

    def test_datetime_field_without_widget_returns_picker(self):
        entity = _entity("Meeting", [_field("scheduled_at", FieldTypeKind.DATETIME)])
        surface = _surface(
            "meeting_edit",
            "Meeting",
            SurfaceMode.EDIT,
            [_element("scheduled_at")],
        )
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=picker"

    def test_str_field_named_tags_returns_tags_widget(self):
        entity = _entity("Article", [_field("tags", FieldTypeKind.STR)])
        surface = _surface("article_create", "Article", SurfaceMode.CREATE, [_element("tags")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=tags"
        assert results[0].kg_entity == "capability:widget_tags"

    def test_str7_field_named_color_returns_color_widget(self):
        entity = _entity("Theme", [_field("color_hex", FieldTypeKind.STR, max_length=7)])
        surface = _surface("theme_edit", "Theme", SurfaceMode.EDIT, [_element("color_hex")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=color"
        assert results[0].kg_entity == "capability:widget_color"

    def test_int_field_named_score_returns_slider_widget(self):
        entity = _entity("Review", [_field("score", FieldTypeKind.INT)])
        surface = _surface("review_create", "Review", SurfaceMode.CREATE, [_element("score")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=slider"
        assert results[0].kg_entity == "capability:widget_slider"

    def test_field_with_widget_annotation_returns_no_relevance(self):
        entity = _entity("Post", [_field("body", FieldTypeKind.TEXT)])
        surface = _surface(
            "post_create",
            "Post",
            SurfaceMode.CREATE,
            [_element("body", options={"widget": "rich_text"})],
        )
        results = check_widget_relevance([entity], [surface])
        assert results == []

    def test_list_mode_surface_returns_no_relevance(self):
        entity = _entity("Post", [_field("body", FieldTypeKind.TEXT)])
        surface = _surface("post_list", "Post", SurfaceMode.LIST, [_element("body")])
        results = check_widget_relevance([entity], [surface])
        assert results == []

    def test_view_mode_surface_returns_no_relevance(self):
        entity = _entity("Post", [_field("body", FieldTypeKind.TEXT)])
        surface = _surface("post_view", "Post", SurfaceMode.VIEW, [_element("body")])
        results = check_widget_relevance([entity], [surface])
        assert results == []

    # ------------------------------------------------------------------
    # Additional edge cases
    # ------------------------------------------------------------------

    def test_examples_list_is_empty(self):
        entity = _entity("Post", [_field("body", FieldTypeKind.TEXT)])
        surface = _surface("post_create", "Post", SurfaceMode.CREATE, [_element("body")])
        results = check_widget_relevance([entity], [surface])
        assert results[0].examples == []

    def test_multiple_fields_in_one_surface(self):
        fields = [
            _field("body", FieldTypeKind.TEXT),
            _field("score", FieldTypeKind.INT),
        ]
        entity = _entity("Item", fields)
        surface = _surface(
            "item_create",
            "Item",
            SurfaceMode.CREATE,
            [_element("body"), _element("score")],
        )
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 2
        capabilities = {r.capability for r in results}
        assert "widget=rich_text" in capabilities
        assert "widget=slider" in capabilities

    def test_str7_without_color_in_name_no_color_widget(self):
        """str(7) but name doesn't match *color* → no color widget."""
        entity = _entity("Post", [_field("hex_val", FieldTypeKind.STR, max_length=7)])
        surface = _surface("post_create", "Post", SurfaceMode.CREATE, [_element("hex_val")])
        results = check_widget_relevance([entity], [surface])
        assert results == []

    def test_int_name_rating_returns_slider(self):
        entity = _entity("Review", [_field("rating", FieldTypeKind.INT)])
        surface = _surface("review_edit", "Review", SurfaceMode.EDIT, [_element("rating")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=slider"

    def test_str_label_field_returns_tags(self):
        entity = _entity("Doc", [_field("label_list", FieldTypeKind.STR)])
        surface = _surface("doc_create", "Doc", SurfaceMode.CREATE, [_element("label_list")])
        results = check_widget_relevance([entity], [surface])
        assert len(results) == 1
        assert results[0].capability == "widget=tags"

    def test_no_entity_ref_surface_skipped(self):
        """Surface with no entity_ref should be skipped without error."""
        surface = SurfaceSpec(
            name="orphan_surface",
            entity_ref=None,
            mode=SurfaceMode.CREATE,
            sections=[SurfaceSection(name="main", elements=[])],
        )
        results = check_widget_relevance([], [surface])
        assert results == []

    def test_unknown_entity_ref_surface_skipped(self):
        """Surface referencing an entity not in entities list is skipped."""
        surface = _surface("x_create", "Ghost", SurfaceMode.CREATE, [_element("name")])
        results = check_widget_relevance([], [surface])
        assert results == []
