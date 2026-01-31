"""Unit tests for the structural fidelity scorer."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.fidelity_scorer import (
    W_SEMANTIC,
    W_STORY,
    W_STRUCTURAL,
    parse_html,
    score_surface_fidelity,
)
from dazzle.core.ir.fidelity import FidelityGapCategory

# ── Helpers ────────────────────────────────────────────────────────────


def _make_id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _make_entity(
    name: str = "Task",
    extra_fields: list[ir.FieldSpec] | None = None,
) -> ir.EntitySpec:
    fields = [_make_id_field()]
    if extra_fields:
        fields.extend(extra_fields)
    return ir.EntitySpec(
        name=name,
        title=name,
        fields=fields,
    )


def _make_list_surface(
    name: str = "task_list",
    entity_ref: str = "Task",
    field_names: list[str] | None = None,
) -> ir.SurfaceSpec:
    if field_names is None:
        field_names = ["title", "completed"]
    return ir.SurfaceSpec(
        name=name,
        title="Task List",
        entity_ref=entity_ref,
        mode=ir.SurfaceMode.LIST,
        sections=[
            ir.SurfaceSection(
                name="main",
                elements=[ir.SurfaceElement(field_name=fn) for fn in field_names],
            )
        ],
    )


def _make_create_surface(
    name: str = "task_create",
    entity_ref: str = "Task",
    field_names: list[str] | None = None,
) -> ir.SurfaceSpec:
    if field_names is None:
        field_names = ["title", "due_date"]
    return ir.SurfaceSpec(
        name=name,
        title="Create Task",
        entity_ref=entity_ref,
        mode=ir.SurfaceMode.CREATE,
        sections=[
            ir.SurfaceSection(
                name="main",
                elements=[ir.SurfaceElement(field_name=fn) for fn in field_names],
            )
        ],
    )


# ── Tests ──────────────────────────────────────────────────────────────


class TestParseHTML:
    def test_parse_html(self) -> None:
        root = parse_html("<div><p>Hello</p></div>")
        divs = root.find_all("div")
        assert len(divs) == 1
        ps = root.find_all("p")
        assert len(ps) == 1
        assert ps[0].get_text() == "Hello"

    def test_void_elements(self) -> None:
        root = parse_html("<div><input type='text'><br><span>X</span></div>")
        inputs = root.find_all("input")
        assert len(inputs) == 1
        assert inputs[0].get_attr("type") == "text"
        spans = root.find_all("span")
        assert len(spans) == 1


class TestScoreListSurface:
    def test_score_list_perfect(self) -> None:
        surface = _make_list_surface()
        html = """
        <style>:root { --color-primary: blue; }</style>
        <table hx-get="/api/tasks">
            <thead><tr><th>Title</th><th>Completed</th></tr></thead>
            <tbody hx-target="#tasks"></tbody>
        </table>
        <a href="/tasks/new">Add</a>
        """
        score = score_surface_fidelity(surface, None, html)
        assert score.structural == 1.0
        assert score.overall > 0.9

    def test_score_list_missing_field(self) -> None:
        surface = _make_list_surface()
        html = """
        <style>:root{}</style>
        <table>
            <thead><tr><th>Title</th></tr></thead>
            <tbody hx-target="#t"></tbody>
        </table>
        """
        score = score_surface_fidelity(surface, None, html)
        missing = [g for g in score.gaps if g.category == FidelityGapCategory.MISSING_FIELD]
        assert len(missing) >= 1
        assert score.structural < 1.0

    def test_score_no_table(self) -> None:
        surface = _make_list_surface()
        html = "<div>No table here</div>"
        score = score_surface_fidelity(surface, None, html)
        critical = [g for g in score.gaps if g.severity == "critical"]
        assert len(critical) >= 1
        assert score.structural < 0.6


class TestScoreFormSurface:
    def test_score_form_incorrect_type(self) -> None:
        entity = _make_entity(
            extra_fields=[
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                    modifiers=[ir.FieldModifier.REQUIRED],
                ),
                ir.FieldSpec(
                    name="due_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
            ]
        )
        surface = _make_create_surface()
        # due_date rendered as text instead of date
        html = """
        <style>:root{}</style>
        <form hx-post="/api/tasks">
            <input name="title" type="text" required>
            <input name="due_date" type="text">
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert len(type_gaps) >= 1

    def test_score_form_missing_required(self) -> None:
        entity = _make_entity(
            extra_fields=[
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                    modifiers=[ir.FieldModifier.REQUIRED],
                ),
                ir.FieldSpec(
                    name="due_date",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
                ),
            ]
        )
        surface = _make_create_surface()
        html = """
        <style>:root{}</style>
        <form hx-post="/api/tasks">
            <input name="title" type="text">
            <input name="due_date" type="date">
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        req_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.MISSING_VALIDATION_ATTRIBUTE
        ]
        assert len(req_gaps) >= 1


class TestSemanticChecks:
    def test_score_semantic_raw_field_names(self) -> None:
        surface = _make_list_surface(field_names=["due_date", "is_active"])
        html = """
        <style>:root{}</style>
        <table>
            <thead><tr><th>due_date</th><th>is_active</th></tr></thead>
            <tbody hx-target="#t"></tbody>
        </table>
        """
        score = score_surface_fidelity(surface, None, html)
        name_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.MISSING_DISPLAY_NAME
        ]
        assert len(name_gaps) >= 1


class TestCompositeWeighting:
    def test_composite_weighting(self) -> None:
        """Verify the 0.4/0.35/0.25 composite weights."""
        surface = _make_list_surface()
        # Perfect HTML for all dimensions
        html = """
        <style>:root { --color-primary: blue; }</style>
        <table hx-get="/api/tasks">
            <thead><tr><th>Title</th><th>Completed</th></tr></thead>
            <tbody hx-target="#tasks"></tbody>
        </table>
        """
        score = score_surface_fidelity(surface, None, html)
        expected = (
            W_STRUCTURAL * score.structural + W_SEMANTIC * score.semantic + W_STORY * score.story
        )
        assert abs(score.overall - round(expected, 4)) < 0.001
