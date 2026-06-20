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

import pytest

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
    @pytest.mark.parametrize(
        "template, item, expected",
        [
            # test_simple_field
            ("Hello, {{ name }}!", {"name": "Priya"}, "Hello, Priya!"),
            # test_dotted_path
            (
                "Tutor: {{ tutor.full_name }}",
                {"tutor": {"full_name": "Mr Khan"}},
                "Tutor: Mr Khan",
            ),
            # test_multiple_fields
            ("{{ year }} · UPN {{ upn }}", {"year": "Y10", "upn": "ABC123"}, "Y10 · UPN ABC123"),
            # test_missing_field_renders_empty
            ("Status: {{ missing }}", {"name": "X"}, "Status: "),
            # test_missing_dotted_path_renders_empty
            ("Tutor: {{ tutor.full_name }}", {"tutor": None}, "Tutor: "),
            # test_fk_dict_resolves_via_display — single-segment FK dict falls back to __display__
            (
                "Tutor: {{ tutor }}",
                {"tutor": {"id": "u-1", "__display__": "Mr Khan"}},
                "Tutor: Mr Khan",
            ),
            # test_empty_template_returns_empty
            ("", {"a": 1}, ""),
            # test_no_placeholders_passes_through
            ("Static text", {"a": 1}, "Static text"),
        ],
        ids=[
            "test_simple_field",
            "test_dotted_path",
            "test_multiple_fields",
            "test_missing_field_renders_empty",
            "test_missing_dotted_path_renders_empty",
            "test_fk_dict_resolves_via_display",
            "test_empty_template_returns_empty",
            "test_no_placeholders_passes_through",
        ],
    )
    def test_interpolate(self, template: str, item: dict, expected: str) -> None:
        from dazzle.http.runtime.workspace_card_data import _interpolate_card_template

        assert _interpolate_card_template(template, item) == expected

    def test_unsafe_expression_left_as_literal(self) -> None:
        """Expressions / function calls aren't supported — they
        don't match the strict IDENT.IDENT* shape so they're left
        as literal `{{ ... }}` placeholders for the author to
        notice. Critically: never eval'd.

        Note: as of #1145 part 1 the grammar accepts an optional
        `| transform_name` suffix and applies it via the
        ``_TIME_TRANSFORMS`` registry. Unknown transform names fall
        back to the raw value (still never eval'd) — see
        ``test_card_template_transforms_1145.py`` for the
        registered-transform contract.
        """
        from dazzle.http.runtime.workspace_card_data import _interpolate_card_template

        item = {"a": 1}
        # Unknown transform — value rendered raw, transform not applied.
        assert _interpolate_card_template("{{ a | upper }}", item) == "1"
        # Arithmetic — not matched, stays literal
        assert _interpolate_card_template("{{ a + 1 }}", item) == "{{ a + 1 }}"


# ───────────────────────── avatar fallback ──────────────────────────


class TestInitialsFrom:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Priya Sharma", "PS"),
            ("Mary Anne Smith", "MA"),
            ("Madonna", "M"),
            ("", ""),
            ("james barlow", "JB"),
        ],
        ids=[
            "test_two_word_name",
            "test_three_word_name_caps_at_two",
            "test_single_word",
            "test_empty_string",
            "test_lowercase_input_uppercased",
        ],
    )
    def test_initials_from(self, name: str, expected: str) -> None:
        from dazzle.http.runtime.workspace_card_data import _initials_from

        assert _initials_from(name) == expected


# ───────────────────────── _resolve_path ──────────────────────────


class TestResolvePath:
    def test_single_segment(self) -> None:
        from dazzle.http.runtime.workspace_card_data import _resolve_path

        assert _resolve_path({"name": "X"}, "name") == "X"

    def test_dotted_path(self) -> None:
        from dazzle.http.runtime.workspace_card_data import _resolve_path

        item = {"tutor": {"name": "Mr Khan"}}
        assert _resolve_path(item, "tutor.name") == "Mr Khan"

    def test_missing_segment(self) -> None:
        from dazzle.http.runtime.workspace_card_data import _resolve_path

        assert _resolve_path({"a": 1}, "missing") is None

    def test_descend_into_non_dict(self) -> None:
        from dazzle.http.runtime.workspace_card_data import _resolve_path

        assert _resolve_path({"a": "string"}, "a.b") is None

    def test_empty_path(self) -> None:
        from dazzle.http.runtime.workspace_card_data import _resolve_path

        assert _resolve_path({"a": 1}, "") is None


# ───────────────────────── template wiring ──────────────────────────


@pytest.mark.skip(
    reason="Phase 4 deletion sweep (v0.67.52) — pinned legacy Jinja template content or file existence; the typed substrate produces equivalent output via different markup"
)
class TestProfileCardTemplateWiring:
    def test_template_map_includes_profile_card(self) -> None:
        from dazzle.page.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "PROFILE_CARD" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["PROFILE_CARD"] == "workspace/regions/_typed_primitive.html"

    def test_template_file_exists(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle/page/templates/workspace/regions/profile_card.html"
        )
        assert path.is_file()

    def test_template_uses_region_card_macro(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle/page/templates/workspace/regions/profile_card.html"
        )
        contents = path.read_text()
        assert "{% call region_card" in contents

    def test_region_context_carries_profile_card_fields(self) -> None:
        from dazzle.page.runtime.workspace_renderer import RegionContext

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
        # v0.67.102 (#1057 cut 3): the interpolator moved to
        # workspace_card_data.py — same invariant, different file.
        src = (
            Path(__file__).resolve().parents[2] / "src/dazzle/http/runtime/workspace_card_data.py"
        ).read_text()
        # The interpolator function should appear in the source
        assert "def _interpolate_card_template" in src
        # And use re.sub, not Jinja
        assert "_CARD_TEMPLATE_RE.sub" in src


# ───────────────────────── #910 follow-up: stats dict access ──────────────


class TestProfileCardStatsBuildFromDicts:
    """v0.61.80 (#910 follow-up): pre-fix the runtime accessed
    `_stat.label` (attribute) on items from `ctx.ctx_region.profile_stats`,
    which is a `list[dict[str, str]]` per the IR→template-context
    boundary in `workspace_renderer.py` (line 569). The attribute
    access raised `AttributeError: 'dict' object has no attribute
    'label'` — but only when `items` was non-empty so the
    `if _item is not None` branch ran.

    Pre-#909 every prod call had wrong-bound scope filters that
    returned 0 items, so the branch never ran and the bug never
    surfaced. The #910 predicate-compiler fix restored items, the
    branch ran, and AegisMark hit the AttributeError as a 500.

    These tests pin the dict-access contract — would have caught the
    AttributeError if they'd existed before #909."""

    def test_build_profile_stats_from_dict_specs_no_attribute_error(self) -> None:
        """Repro of the 500: stats specs are dicts, not pydantic
        models — accessing `stat.label` raised AttributeError. Now
        uses ``stat["label"]``.

        v0.67.107 (#1057 cut 8): the PROFILE_CARD compute moved to
        ``workspace_region_computes.compute_profile_card``. Same
        invariant, new home.
        """
        src = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle/http/runtime/workspace_region_computes.py"
        ).read_text()
        # The runtime must use dict access (the boundary always converts to dicts)
        assert 'stat["label"]' in src, (
            "PROFILE_CARD render path must use dict-access on stats specs — "
            "attribute access (`stat.label`) raised 500 in production (#910 "
            "follow-up: AegisMark pupil_identity profile_card)."
        )
        assert 'stat["value"]' in src
        # And NOT the attribute form in the comprehension itself.
        # Substring check on the full file would match the docstring,
        # so scope to a window around the dict literal we care about.
        marker = '"label": stat["label"]'
        idx = src.find(marker)
        assert idx >= 0
        # Window the assertion to ±200 chars of the dict literal so the
        # docstring history doesn't trip us up.
        window = src[max(0, idx - 200) : idx + 400]
        assert "stat.label" not in window
        assert "stat.value" not in window

    def test_runtime_boundary_emits_dicts_not_models(self) -> None:
        """Pin the IR→template-context boundary shape: profile_stats
        is `list[dict[str, str]]`, not `list[ProfileCardStatSpec]`.
        If this boundary ever changes to pass models through directly,
        the dict-access fix above must change with it."""
        src = (
            Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/workspace_renderer.py"
        ).read_text()
        # The boundary line that constructs the dict-of-dicts shape
        assert '{"label": s.label, "value": s.value}' in src
        # The RegionContext field signature
        assert "profile_stats: list[dict[str, str]]" in src

    def test_stat_value_resolves_against_item_via_dict_key(self) -> None:
        """End-to-end-ish: simulate the inner comprehension. Build the
        same shape the runtime would produce given a non-empty item
        and dict-shaped stats — exercising the exact lines that 500'd."""
        # Mirror of the comprehension in workspace_rendering.py PROFILE_CARD
        from dazzle.http.runtime.workspace_card_data import _resolve_path

        item = {
            "id": "abc",
            "target_grade": "A*",
            "latest_grade": "B",
            "year_group": "11",
        }
        stats_specs = [
            {"label": "Target", "value": "target_grade"},
            {"label": "Latest", "value": "latest_grade"},
        ]
        # The exact shape from line 1389
        result = [
            {
                "label": _stat["label"],
                "value": str(_resolve_path(item, _stat["value"]) or ""),
            }
            for _stat in stats_specs
        ]
        assert result == [
            {"label": "Target", "value": "A*"},
            {"label": "Latest", "value": "B"},
        ]
