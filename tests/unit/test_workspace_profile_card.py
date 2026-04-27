"""Tests for the v0.61.55 profile_card display mode (#892).

Four layers:
  1. Parser: ``display: profile_card`` + ``avatar_field:`` /
     ``primary:`` / ``secondary:`` / ``stats:`` / ``facts:`` parse
     into the IR.
  2. Template-string interpolation: ``_interpolate_card_template``
     resolves ``{{ field }}`` and ``{{ field.path }}`` against an
     item dict, with safe fallbacks for missing/None paths.
  3. Avatar fallback: ``_initials_from`` computes initials from a
     name when no avatar URL is available.
  4. Renderer: ``RegionContext`` carries the profile_card fields
     through to the template; template wiring registered.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import DisplayMode, ProfileCardStatSpec
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity Student:
  id: uuid pk
  full_name: str(100)
  upn: str(20)
  photo_url: str(200)
workspace dash "Dash":
  pupil_identity:
    source: Student
    display: profile_card
    avatar_field: photo_url
    primary: full_name
"""


# ───────────────────────── parser ──────────────────────────


class TestProfileCardParser:
    def test_minimal_profile_card(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.PROFILE_CARD
        assert region.source == "Student"
        assert region.avatar_field == "photo_url"
        assert region.primary == "full_name"
        assert region.secondary is None
        assert region.profile_stats == []
        assert region.facts == []

    def test_secondary_quoted_string_with_template(self) -> None:
        src = _BASE_DSL + '    secondary: "{{ year_group }} · UPN {{ upn }}"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.secondary == "{{ year_group }} · UPN {{ upn }}"

    def test_stats_block(self) -> None:
        src = (
            _BASE_DSL
            + "    stats:\n"
            + '      - label: "Target"\n'
            + "        value: target_grade\n"
            + '      - label: "Projected"\n'
            + "        value: projected_grade\n"
        )
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.profile_stats) == 2
        assert region.profile_stats[0].label == "Target"
        assert region.profile_stats[0].value == "target_grade"
        assert region.profile_stats[1].label == "Projected"
        assert region.profile_stats[1].value == "projected_grade"

    def test_stats_value_supports_dotted_path(self) -> None:
        src = (
            _BASE_DSL
            + "    stats:\n"
            + '      - label: "Tutor"\n'
            + "        value: tutor.full_name\n"
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.profile_stats[0].value == "tutor.full_name"

    def test_facts_block(self) -> None:
        src = (
            _BASE_DSL
            + "    facts:\n"
            + '      - "Tutor: {{ tutor.full_name }}"\n'
            + '      - "EAL: {{ eal_status }}"\n'
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.facts == [
            "Tutor: {{ tutor.full_name }}",
            "EAL: {{ eal_status }}",
        ]

    def test_full_repro_dsl_from_issue(self) -> None:
        """The issue's complete DSL example — parses without errors."""
        src = """module t
app t "Test"
entity StudentProfile:
  id: uuid pk
  full_name: str(100)
  photo_url: str(200)
  target_grade: str(10)
  projected_grade: str(10)
  latest_sub_band: str(10)
workspace dash "Dash":
  pupil_identity:
    source: StudentProfile
    display: profile_card
    avatar_field: photo_url
    primary: full_name
    secondary: "{{ year_group }} · UPN {{ upn }}"
    stats:
      - label: "Target"
        value: target_grade
      - label: "Projected"
        value: projected_grade
      - label: "Current band"
        value: latest_sub_band
    facts:
      - "Tutor: {{ tutor.full_name }}"
      - "EAL: {{ eal_status }}"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.display == DisplayMode.PROFILE_CARD
        assert region.avatar_field == "photo_url"
        assert region.primary == "full_name"
        assert region.secondary == "{{ year_group }} · UPN {{ upn }}"
        assert len(region.profile_stats) == 3
        assert len(region.facts) == 2


# ───────────────────────── interpolation ──────────────────────────


class TestInterpolateCardTemplate:
    def test_simple_field(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        item = {"name": "Priya"}
        assert _interpolate_card_template("Hello, {{ name }}!", item) == "Hello, Priya!"

    def test_dotted_path(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        item = {"tutor": {"full_name": "Mr Khan"}}
        assert _interpolate_card_template("Tutor: {{ tutor.full_name }}", item) == "Tutor: Mr Khan"

    def test_multiple_fields(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        item = {"year": "Y10", "upn": "ABC123"}
        assert _interpolate_card_template("{{ year }} · UPN {{ upn }}", item) == "Y10 · UPN ABC123"

    def test_missing_field_renders_empty(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        item = {"name": "X"}
        assert _interpolate_card_template("Status: {{ missing }}", item) == "Status: "

    def test_missing_dotted_path_renders_empty(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        item = {"tutor": None}
        assert _interpolate_card_template("Tutor: {{ tutor.full_name }}", item) == "Tutor: "

    def test_fk_dict_resolves_via_display(self) -> None:
        """When a single-segment path lands on an FK dict, fall back
        to the heatmap/box_plot resolution chain (`__display__` →
        `name` → `title` → ...)."""
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        item = {"tutor": {"id": "u-1", "__display__": "Mr Khan"}}
        assert _interpolate_card_template("Tutor: {{ tutor }}", item) == "Tutor: Mr Khan"

    def test_empty_template_returns_empty(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        assert _interpolate_card_template("", {"a": 1}) == ""

    def test_no_placeholders_passes_through(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        assert _interpolate_card_template("Static text", {"a": 1}) == "Static text"

    def test_unsafe_expression_left_as_literal(self) -> None:
        """Expressions / filters / function calls aren't supported —
        they don't match the strict IDENT.IDENT* shape so they're
        left as literal `{{ ... }}` placeholders for the author to
        notice. Critically: never eval'd."""
        from dazzle_back.runtime.workspace_rendering import _interpolate_card_template

        item = {"a": 1}
        # Pipe filter — not matched, stays literal
        assert _interpolate_card_template("{{ a | upper }}", item) == "{{ a | upper }}"
        # Arithmetic — not matched
        assert _interpolate_card_template("{{ a + 1 }}", item) == "{{ a + 1 }}"


# ───────────────────────── avatar fallback ──────────────────────────


class TestInitialsFrom:
    def test_two_word_name(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _initials_from

        assert _initials_from("Priya Sharma") == "PS"

    def test_three_word_name_caps_at_two(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _initials_from

        assert _initials_from("Mary Anne Smith") == "MA"

    def test_single_word(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _initials_from

        assert _initials_from("Madonna") == "M"

    def test_empty_string(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _initials_from

        assert _initials_from("") == ""

    def test_lowercase_input_uppercased(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _initials_from

        assert _initials_from("james barlow") == "JB"


# ───────────────────────── _resolve_path ──────────────────────────


class TestResolvePath:
    def test_single_segment(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _resolve_path

        assert _resolve_path({"name": "X"}, "name") == "X"

    def test_dotted_path(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _resolve_path

        item = {"tutor": {"name": "Mr Khan"}}
        assert _resolve_path(item, "tutor.name") == "Mr Khan"

    def test_missing_segment(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _resolve_path

        assert _resolve_path({"a": 1}, "missing") is None

    def test_descend_into_non_dict(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _resolve_path

        assert _resolve_path({"a": "string"}, "a.b") is None

    def test_empty_path(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _resolve_path

        assert _resolve_path({"a": 1}, "") is None


# ───────────────────────── template wiring ──────────────────────────


class TestProfileCardTemplateWiring:
    def test_template_map_includes_profile_card(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "PROFILE_CARD" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["PROFILE_CARD"] == "workspace/regions/profile_card.html"

    def test_template_file_exists(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/profile_card.html"
        )
        assert path.is_file()

    def test_template_uses_region_card_macro(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/profile_card.html"
        )
        contents = path.read_text()
        assert "{% call region_card" in contents

    def test_region_context_carries_profile_card_fields(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(
            name="r",
            avatar_field="photo_url",
            primary="full_name",
            secondary="hello",
            profile_stats=[{"label": "L", "value": "v"}],
            facts=["f1"],
        )
        assert ctx.avatar_field == "photo_url"
        assert ctx.primary == "full_name"
        assert ctx.secondary == "hello"
        assert len(ctx.profile_stats) == 1
        assert ctx.facts == ["f1"]

    def test_profile_card_stat_spec_construct(self) -> None:
        spec = ProfileCardStatSpec(label="X", value="y")
        assert spec.label == "X"
        assert spec.value == "y"


# ───────────────────────── safety invariants ──────────────────────────


class TestProfileCardSafety:
    def test_template_no_jinja_eval_in_runtime_helper(self) -> None:
        """Pin the contract that `_interpolate_card_template` never
        invokes Jinja's eval/expression parser. The interpolator is
        a plain regex substitution — checked by the
        `test_unsafe_expression_left_as_literal` case above. This test
        is the static-source guard: the implementation must NOT import
        jinja2 inside `_interpolate_card_template`'s module path."""
        src = (
            Path(__file__).resolve().parents[2] / "src/dazzle_back/runtime/workspace_rendering.py"
        ).read_text()
        # The interpolator function should appear in the source
        assert "def _interpolate_card_template" in src
        # And use re.sub, not Jinja
        assert "_CARD_TEMPLATE_RE.sub" in src
