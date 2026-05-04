"""Tests for grammar_gen.py — grammar documentation generator."""

import pytest

from dazzle.core.grammar_gen import (
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

    def test_ledger_keywords_present(self) -> None:
        groups = get_keyword_groups()
        all_keywords = [kw for kwlist in groups.values() for kw in kwlist]
        for expected in ["ledger", "transaction", "transfer", "debit", "credit"]:
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
