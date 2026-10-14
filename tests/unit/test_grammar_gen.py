"""Tests for grammar_gen.py — grammar documentation generator."""

import re
from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.dsl_parser_impl.process import _STEP_FIELD_IDENT_KEYWORDS, _STEP_FIELD_KEYWORDS
from dazzle.core.grammar_gen import (
    _CATEGORY_EXAMPLES,
    _MIXIN_SECTIONS,
    build_type_spec_rule,
    generate_grammar,
    get_keyword_groups,
    get_mixin_class_names,
    get_version,
)
from dazzle.core.ir.fields import FieldTypeKind


class TestGenerateGrammar:
    """Tests for the main generate_grammar() function."""

    def test_produces_nonempty_output(self) -> None:
        output = generate_grammar()
        assert len(output) > 1000, "Grammar output should be substantial"

    def test_includes_version_header(self) -> None:
        version = get_version()
        output = generate_grammar()
        assert f"v{version}" in output

    def test_includes_anti_turing_note(self) -> None:
        output = generate_grammar()
        assert "Anti-Turing" in output

    def test_includes_keyword_inventory(self) -> None:
        output = generate_grammar()
        assert "## Keyword Inventory" in output
        # Check some representative keywords are listed
        assert "`entity`" in output
        assert "`surface`" in output

    def test_includes_field_types_section(self) -> None:
        output = generate_grammar()
        assert "## Field Types" in output

    @pytest.mark.parametrize(
        "tokens",
        [
            ["```ebnf", "dazzle_spec"],
            ["## DSL Examples", "```dsl"],
            ["## Parser Mixin Coverage", "| Module | Class | Category |"],
            ["Auto-generated", "grammar_gen.py"],
        ],
        ids=[
            "test_includes_ebnf_block",
            "test_includes_dsl_examples",
            "test_includes_parser_mixin_table",
            "test_auto_generated_notice",
        ],
    )
    def test_grammar_contains_tokens(self, tokens: list[str]) -> None:
        output = generate_grammar()
        for token in tokens:
            assert token in output


class TestMixinCoverage:
    """Every parser mixin must be represented in the grammar."""

    def test_all_mixins_have_entries(self) -> None:
        """Every module in _MIXIN_SECTIONS must map to a real class."""
        class_names = get_mixin_class_names()
        for mod_name, _title, _category in _MIXIN_SECTIONS:
            assert mod_name in class_names, f"Mixin module '{mod_name}' not found"

    def test_all_mixins_in_grammar_output(self) -> None:
        """Every mixin module should appear in the mixin coverage table."""
        output = generate_grammar()
        for mod_name, _title, _category in _MIXIN_SECTIONS:
            assert f"`{mod_name}.py`" in output, f"Mixin '{mod_name}' not in grammar output"


class TestFieldTypeCoverage:
    """Every FieldTypeKind must appear in the type_spec rule."""

    def test_all_field_types_in_type_spec(self) -> None:
        rule = build_type_spec_rule()
        for kind in FieldTypeKind:
            # ENUM and REF are handled specially (enum_type, reference_type)
            if kind == FieldTypeKind.ENUM:
                assert "enum" in rule
            elif kind == FieldTypeKind.REF:
                assert '"ref"' in rule
            else:
                assert f'"{kind.value}"' in rule, (
                    f"FieldTypeKind.{kind.name} ({kind.value}) missing from type_spec"
                )

    def test_all_field_types_in_grammar_output(self) -> None:
        output = generate_grammar()
        for kind in FieldTypeKind:
            assert f"`{kind.value}`" in output, f"FieldTypeKind.{kind.name} not in grammar output"


class TestKeywordGroups:
    """Keyword extraction from lexer."""

    def test_returns_nonempty_groups(self) -> None:
        groups = get_keyword_groups()
        assert len(groups) > 5, "Expected multiple keyword groups"

    def test_core_keywords_present(self) -> None:
        groups = get_keyword_groups()
        all_keywords = [kw for kwlist in groups.values() for kw in kwlist]
        for expected in ["entity", "surface", "workspace", "service"]:
            assert expected in all_keywords, f"Keyword '{expected}' not found"


class TestVersion:
    """Version extraction."""

    def test_version_is_semantic(self) -> None:
        import re

        version = get_version()
        parts = version.split(".")
        assert len(parts) >= 2, f"Version '{version}' should be semantic"
        # Allow PEP 440 prerelease suffixes on the patch component:
        # 0.61.0, 0.61.0rc1, 0.61.0a2, 0.61.0b1, 0.61.0.dev1 all valid.
        pep440_part = re.compile(r"^\d+([a-z]+\d+)?$")
        for p in parts:
            assert pep440_part.match(p), f"Version part {p!r} is not numeric or PEP-440"


def _production_keywords(name: str) -> set[str]:
    """Quoted keywords of one EBNF production in the generated grammar."""
    match = re.search(rf"^{name}\s*::=(.*?);[^\n]*$", generate_grammar(), re.M | re.S)
    assert match, f"production {name!r} not found"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


class TestProcessGrammarMatchesParser:
    """Flense ship Z: the process productions list what the parser reads."""

    def test_step_body_keywords_match_the_step_dispatch_table(self) -> None:
        parsed = {tt.value for tt in _STEP_FIELD_KEYWORDS} | set(_STEP_FIELD_IDENT_KEYWORDS)
        assert _production_keywords("step_body") == parsed

    @pytest.mark.parametrize(
        ("production", "keywords"),
        [
            (
                "human_task_body",
                {"surface", "entity", "assignee_role", "assignee", "timeout", "outcomes"},
            ),
            ("task_outcome", {"label", "goto", "confirm", "style"}),
            ("compensation", {"service", "timeout", "inputs"}),
            (
                "step_retry_config",
                {"max_attempts", "backoff", "interval", "fixed", "exponential", "linear"},
            ),
        ],
    )
    def test_process_sub_block_keywords(self, production: str, keywords: set[str]) -> None:
        assert _production_keywords(production) == keywords

    def test_workflow_example_parses_without_warnings(self) -> None:
        body = _CATEGORY_EXAMPLES["Workflow"].split("```dsl\n", 1)[1].split("```", 1)[0]
        *_, fragment = parse_dsl('module t\napp t "T"\n\n' + body, Path("x.dsl"))
        assert fragment.parse_warnings == []
        process = fragment.processes[0]
        assert [s.name for s in process.steps] == ["validate", "pick", "cancel"]
        task = process.steps[1].human_task
        assert task is not None and task.entity_path == "Order"
        assert [o.name for o in task.outcomes] == ["picked", "short"]
        assert process.steps[0].retry is not None
        assert [s.name for s in fragment.schedules[0].steps] == ["generate"]
