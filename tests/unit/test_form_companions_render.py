"""Render-side tests for companion regions on create/edit surfaces (#923).

The IR + parser are pinned by `test_parser.py::TestSurfaceCompanions`.
These tests cover the full render path: FormContext → form.html →
companion macro. We pin:

1. CompanionContext shape (renders all three positions correctly).
2. Display-mode coverage: summary_row, status_list, pipeline_steps,
   placeholder for source-bound, fallback for unknown.
3. Compiler conversion: IR `CompanionSpec` → `CompanionContext`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.runtime.template_context import (  # noqa: E402
    CompanionContext,
    CompanionEntryContext,
    CompanionStageContext,
    FormContext,
    FormSectionContext,
)
from dazzle_ui.runtime.template_renderer import create_jinja_env  # noqa: E402


@pytest.fixture
def jinja_env():
    return create_jinja_env()


def _render_form(jinja_env, form: FormContext) -> str:
    tmpl = jinja_env.get_template("components/form.html")
    return tmpl.render(form=form)


def _make_form(
    companions: list[CompanionContext],
    sections: list[FormSectionContext] | None = None,
    layout: str = "single_page",
) -> FormContext:
    return FormContext(
        entity_name="Doc",
        title="Create Doc",
        fields=[],
        action_url="/api/doc",
        sections=sections or [FormSectionContext(name="main", title="Main", fields=[])],
        layout=layout,
        companions=companions,
    )


class TestCompanionPositions:
    def test_top_companion_renders_before_sections(self, jinja_env) -> None:
        c = CompanionContext(
            name="summary",
            title="Batch summary",
            position="top",
            display="summary_row",
            aggregate={"pages": "max(page_count)"},
        )
        html = _render_form(jinja_env, _make_form([c]))
        # The companion <aside> appears in the rendered output.
        assert 'data-dazzle-companion="summary"' in html
        assert "Batch summary" in html
        # And it sits BEFORE the section title in source order.
        assert html.index("Batch summary") < html.index("Main")

    def test_bottom_companion_renders_after_sections(self, jinja_env) -> None:
        c = CompanionContext(
            name="footer",
            title="Footer note",
            position="bottom",
            display="status_list",
            entries=[CompanionEntryContext(title="Done")],
        )
        html = _render_form(jinja_env, _make_form([c]))
        assert html.index("Main") < html.index("Footer note")

    def test_below_section_pins_to_anchor(self, jinja_env) -> None:
        sections = [
            FormSectionContext(name="alpha", title="Alpha", fields=[]),
            FormSectionContext(name="beta", title="Beta", fields=[]),
        ]
        c = CompanionContext(
            name="alpha_helper",
            title="Helper for alpha",
            position="below_section",
            section_anchor="alpha",
            display="status_list",
            entries=[CompanionEntryContext(title="A")],
        )
        html = _render_form(jinja_env, _make_form([c], sections))
        # Helper sits between the alpha and beta section titles.
        alpha_idx = html.index("Alpha")
        helper_idx = html.index("Helper for alpha")
        beta_idx = html.index("Beta")
        assert alpha_idx < helper_idx < beta_idx


class TestCompanionDisplayModes:
    def test_summary_row_renders_metric_tiles(self, jinja_env) -> None:
        c = CompanionContext(
            name="m",
            title="Metrics",
            position="top",
            display="summary_row",
            aggregate={"pages": "max(page_count)", "strands": "count(AO)"},
        )
        html = _render_form(jinja_env, _make_form([c]))
        assert "dz-form-companion-summary-row" in html
        assert "dz-form-companion-metric" in html
        # The metric label is rendered humanised (underscores → spaces).
        assert "pages" in html
        assert "strands" in html
        # The expression is captured but not user-visible (debug-only span).
        assert "max(page_count)" in html

    def test_status_list_renders_entries(self, jinja_env) -> None:
        c = CompanionContext(
            name="plan",
            title="Plan",
            position="bottom",
            display="status_list",
            entries=[
                CompanionEntryContext(title="Classify the batch", caption="Sort by paper"),
                CompanionEntryContext(title="Separate the PDF"),
            ],
        )
        html = _render_form(jinja_env, _make_form([c]))
        assert "Classify the batch" in html
        assert "Sort by paper" in html
        assert "Separate the PDF" in html
        assert html.count("dz-form-companion-entry") >= 2

    def test_status_list_state_emits_modifier_class(self, jinja_env) -> None:
        c = CompanionContext(
            name="plan",
            title="Plan",
            position="bottom",
            display="status_list",
            entries=[
                CompanionEntryContext(title="A", state="ok"),
                CompanionEntryContext(title="B", state="warn"),
            ],
        )
        html = _render_form(jinja_env, _make_form([c]))
        assert "dz-form-companion-entry--ok" in html
        assert "dz-form-companion-entry--warn" in html

    def test_pipeline_steps_renders_stage_cards(self, jinja_env) -> None:
        c = CompanionContext(
            name="pipe",
            title="Pipeline",
            position="bottom",
            display="pipeline_steps",
            stages=[
                CompanionStageContext(label="Step 1", caption="First"),
                CompanionStageContext(label="Step 2"),
            ],
        )
        html = _render_form(jinja_env, _make_form([c]))
        assert "dz-form-companion-pipeline" in html
        assert "Step 1" in html
        assert "First" in html
        assert "Step 2" in html
        assert html.count("dz-form-companion-stage") >= 2

    def test_source_bound_renders_placeholder(self, jinja_env) -> None:
        """v1 ships declarative companions only; source-bound companions
        parse but render a placeholder pending workspace-region pipeline
        integration."""
        c = CompanionContext(
            name="roster",
            title="Roster",
            position="top",
            display="list",
            source="StudentProfile",
            limit=5,
        )
        html = _render_form(jinja_env, _make_form([c]))
        # Source name surfaces in the placeholder so authors can debug.
        assert "StudentProfile" in html
        assert "dz-form-companion-placeholder" in html

    def test_unknown_display_falls_back_to_placeholder(self, jinja_env) -> None:
        c = CompanionContext(
            name="x",
            title="Unknown",
            position="top",
            display=None,
        )
        html = _render_form(jinja_env, _make_form([c]))
        assert "Unknown" in html
        assert "dz-form-companion-placeholder" in html


class TestCompilerConversion:
    """Compiling an IR `CompanionSpec` into a `CompanionContext`."""

    def test_compiler_propagates_position_and_anchor(self) -> None:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle_ui.converters.template_compiler import _build_companion_contexts

        dsl = """
module test
app A "A"
entity Doc:
  id: uuid pk

surface doc_create:
  uses entity Doc
  mode: create

  companion top "Top" position=top:
    display: status_list

  companion sec "After main" position=below_section[main]:
    display: status_list

  section main:
    field id "id"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        contexts = _build_companion_contexts(fragment.surfaces[0])
        assert len(contexts) == 2
        assert contexts[0].name == "top"
        assert contexts[0].position == "top"
        assert contexts[1].name == "sec"
        assert contexts[1].position == "below_section"
        assert contexts[1].section_anchor == "main"

    def test_no_companions_yields_empty_list(self) -> None:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle_ui.converters.template_compiler import _build_companion_contexts

        dsl = """
module test
app A "A"
entity Doc:
  id: uuid pk

surface doc_create:
  uses entity Doc
  mode: create
  section main:
    field id "id"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        assert _build_companion_contexts(fragment.surfaces[0]) == []
