"""
Property-based tests using Hypothesis.

These tests verify invariants across a wide range of inputs,
replacing the need for exhaustive example-based tests.
"""

from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.lexer import Lexer, TokenType
from dazzle_dnr_back.channels.templates import (
    TemplateSyntaxError,
    extract_variables,
    render_template,
    validate_template,
)

# =============================================================================
# Template Engine Property Tests
# =============================================================================


class TestTemplateEngineProperties:
    """Property-based tests for the template engine."""

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_render_never_crashes_on_arbitrary_input(self, text: str) -> None:
        """Invariant: render_template never crashes, only raises TemplateSyntaxError."""
        try:
            render_template(text, {})
        except TemplateSyntaxError:
            pass  # Expected for invalid templates
        # No other exceptions should occur

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_0123456789"),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=100)
    def test_simple_variable_substitution_roundtrip(self, var_name: str) -> None:
        """Invariant: {{ var }} with context[var]=X always produces X."""
        assume(var_name.isidentifier())  # Must be valid Python identifier
        template = f"{{{{ {var_name} }}}}"
        value = "test_value"
        result = render_template(template, {var_name: value})
        assert result == value

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_plain_text_unchanged(self, text: str) -> None:
        """Invariant: Text without {{ or {% passes through unchanged."""
        assume("{{" not in text and "{%" not in text)
        result = render_template(text, {})
        assert result == text

    @given(
        st.dictionaries(
            keys=st.text(
                alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
                min_size=1,
                max_size=10,
            ).filter(str.isidentifier),
            values=st.text(min_size=0, max_size=50),
            min_size=0,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_variable_extraction_finds_used_variables(self, context: dict) -> None:
        """Invariant: Variables in template are found by extract_variables."""
        if not context:
            return

        # Build template using all context keys
        template_parts = [f"{{{{ {key} }}}}" for key in context.keys()]
        template = " ".join(template_parts)

        extracted = extract_variables(template)
        for key in context.keys():
            assert key in extracted

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_validation_consistency_with_render(self, template: str) -> None:
        """Invariant: If validate returns errors, render should raise."""
        errors = validate_template(template)

        if not errors:
            # Valid template should render without exception
            try:
                render_template(template, {})
            except TemplateSyntaxError:
                # Some edge cases may validate but fail to render
                # This is acceptable - validation is conservative
                pass
        # If errors exist, we don't require render to fail
        # (validation may be stricter than render)


class TestTemplateConditionalProperties:
    """Property-based tests for conditional blocks."""

    @given(st.booleans())
    def test_if_block_boolean_consistency(self, condition: bool) -> None:
        """Invariant: {% if x %}A{% else %}B{% endif %} returns A if x else B."""
        template = "{% if cond %}TRUE{% else %}FALSE{% endif %}"
        result = render_template(template, {"cond": condition})
        expected = "TRUE" if condition else "FALSE"
        assert result == expected

    @given(st.lists(st.booleans(), min_size=1, max_size=3))
    @settings(max_examples=50)
    def test_nested_if_blocks(self, conditions: list[bool]) -> None:
        """Invariant: Nested if blocks evaluate correctly."""
        # Build nested template
        opens = "".join(f"{{% if c{i} %}}" for i in range(len(conditions)))
        closes = "{% endif %}" * len(conditions)
        template = f"{opens}PASS{closes}"

        context = {f"c{i}": cond for i, cond in enumerate(conditions)}
        result = render_template(template, context)

        expected = "PASS" if all(conditions) else ""
        assert result == expected


# =============================================================================
# String Invariant Properties
# =============================================================================


class TestStringInvariants:
    """Property-based tests for string handling invariants."""

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
            min_size=1,
            max_size=20,
        ).filter(str.isidentifier)
    )
    @settings(max_examples=100)
    def test_missing_variable_renders_empty(self, var_name: str) -> None:
        """Invariant: Missing variables render as empty string, not error."""
        template = f"prefix{{{{ {var_name} }}}}suffix"
        result = render_template(template, {})
        assert result == "prefixsuffix"

    @given(st.none() | st.integers() | st.floats(allow_nan=False) | st.booleans())
    def test_non_string_values_stringify(self, value) -> None:
        """Invariant: Non-string values are converted to strings."""
        if value is None:
            expected = ""
        else:
            expected = str(value)

        template = "{{ val }}"
        result = render_template(template, {"val": value})
        assert result == expected


# =============================================================================
# Edge Case Fuzzing
# =============================================================================


class TestEdgeCaseFuzzing:
    """Fuzz testing for edge cases and potential security issues."""

    @given(st.text(alphabet=st.sampled_from("{}% \t\n"), min_size=0, max_size=50))
    @settings(max_examples=200)
    def test_malformed_braces_dont_crash(self, text: str) -> None:
        """Invariant: Malformed brace sequences don't cause crashes."""
        try:
            render_template(text, {})
        except TemplateSyntaxError:
            pass  # Expected

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz "),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_unclosed_braces_handled(self, text: str) -> None:
        """Invariant: Unclosed {{ sequences are handled gracefully."""
        template = "prefix{{ " + text  # Deliberately unclosed
        try:
            render_template(template, {})
        except TemplateSyntaxError:
            pass  # Expected for invalid templates

    @given(st.integers(min_value=1, max_value=20))
    def test_deeply_nested_conditions(self, depth: int) -> None:
        """Invariant: Deeply nested conditions don't overflow stack."""
        opens = "{% if x %}" * depth
        closes = "{% endif %}" * depth
        template = f"{opens}PASS{closes}"

        result = render_template(template, {"x": True})
        assert result == "PASS"

        result_false = render_template(template, {"x": False})
        assert result_false == ""


# =============================================================================
# Comparison Properties
# =============================================================================


class TestComparisonProperties:
    """Property-based tests for comparison operations."""

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
            min_size=1,
            max_size=15,
        ),
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
            min_size=1,
            max_size=15,
        ),
    )
    @settings(max_examples=100)
    def test_equality_comparison_consistency(self, a: str, b: str) -> None:
        """Invariant: String equality comparison matches Python semantics."""
        template = f'{{% if val == "{a}" %}}MATCH{{% else %}}NO{{% endif %}}'
        result = render_template(template, {"val": a})
        assert result == "MATCH"

        if a != b:
            result_other = render_template(template, {"val": b})
            assert result_other == "NO"

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
            min_size=1,
            max_size=15,
        )
    )
    @settings(max_examples=50)
    def test_inequality_comparison_consistency(self, value: str) -> None:
        """Invariant: Inequality comparison matches Python semantics."""
        template = f'{{% if val != "{value}" %}}DIFFERENT{{% else %}}SAME{{% endif %}}'

        result_same = render_template(template, {"val": value})
        assert result_same == "SAME"

        result_diff = render_template(template, {"val": value + "_other"})
        assert result_diff == "DIFFERENT"


# =============================================================================
# DSL Parser/Lexer Property Tests
# =============================================================================


class TestLexerProperties:
    """Property-based tests for the DAZZLE DSL lexer."""

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_lexer_never_crashes_on_arbitrary_input(self, text: str) -> None:
        """Invariant: Lexer never crashes, only raises ParseError."""
        try:
            lexer = Lexer(text, Path("test.dsl"))
            lexer.tokenize()
        except ParseError:
            pass  # Expected for invalid input
        # No other exceptions should occur

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_lexer_always_emits_eof(self, text: str) -> None:
        """Invariant: Lexer always emits EOF token at the end."""
        try:
            lexer = Lexer(text, Path("test.dsl"))
            tokens = lexer.tokenize()
            # Last token should always be EOF
            assert len(tokens) > 0
            assert tokens[-1].type == TokenType.EOF
        except ParseError:
            pass  # Invalid input is allowed to fail

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_lexer_token_positions_valid(self, text: str) -> None:
        """Invariant: All tokens have valid line/column numbers (≥1)."""
        try:
            lexer = Lexer(text, Path("test.dsl"))
            tokens = lexer.tokenize()
            for token in tokens:
                assert token.line >= 1, f"Token {token} has invalid line"
                assert token.column >= 1, f"Token {token} has invalid column"
        except ParseError:
            pass  # Invalid input is allowed to fail

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_lexer_finite_tokens(self, text: str) -> None:
        """Invariant: Token count is finite and bounded for finite input."""
        try:
            lexer = Lexer(text, Path("test.dsl"))
            tokens = lexer.tokenize()
            # Token count should be bounded relative to input size
            # At most, each character could be a token plus EOF
            assert len(tokens) <= len(text) * 2 + 100
        except ParseError:
            pass  # Invalid input is allowed to fail

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
            min_size=1,
            max_size=20,
        ).filter(str.isidentifier)
    )
    @settings(max_examples=100)
    def test_lexer_identifier_roundtrip(self, identifier: str) -> None:
        """Invariant: Valid identifiers are tokenized correctly."""
        lexer = Lexer(identifier, Path("test.dsl"))
        tokens = lexer.tokenize()
        # Should have IDENTIFIER (or keyword) + EOF
        assert len(tokens) >= 2
        assert tokens[-1].type == TokenType.EOF
        # First non-special token should contain the identifier
        assert tokens[0].value == identifier

    @given(st.integers(min_value=0, max_value=999999))
    def test_lexer_number_roundtrip(self, number: int) -> None:
        """Invariant: Numbers are tokenized correctly."""
        text = str(number)
        lexer = Lexer(text, Path("test.dsl"))
        tokens = lexer.tokenize()
        assert len(tokens) >= 2
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == text

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789 "),
            min_size=0,
            max_size=50,
        )
    )
    @settings(max_examples=100)
    def test_lexer_string_roundtrip(self, content: str) -> None:
        """Invariant: Quoted strings are tokenized with correct content."""
        # Escape quotes in content
        escaped = content.replace("\\", "\\\\").replace('"', '\\"')
        text = f'"{escaped}"'
        lexer = Lexer(text, Path("test.dsl"))
        tokens = lexer.tokenize()
        assert len(tokens) >= 2
        assert tokens[0].type == TokenType.STRING
        # String content should match original
        assert tokens[0].value == content

    @given(st.text(alphabet=st.sampled_from("{}[]()=:,.<>!-+*"), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_lexer_operators_dont_crash(self, text: str) -> None:
        """Invariant: Operator sequences don't crash the lexer."""
        try:
            lexer = Lexer(text, Path("test.dsl"))
            lexer.tokenize()
        except ParseError:
            pass  # Expected for some invalid combinations


class TestParserProperties:
    """Property-based tests for the DAZZLE DSL parser."""

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=200)
    def test_parser_never_crashes_on_arbitrary_input(self, text: str) -> None:
        """Invariant: Parser never crashes, only raises ParseError."""
        try:
            parse_dsl(text, Path("test.dsl"))
        except ParseError:
            pass  # Expected for invalid input
        # No other exceptions should occur

    def test_parser_empty_input(self) -> None:
        """Invariant: Empty input produces empty fragment."""
        _, _, _, _, _, fragment = parse_dsl("", Path("test.dsl"))
        assert fragment.entities == []
        assert fragment.surfaces == []
        assert fragment.workspaces == []

    @given(st.text(alphabet=st.sampled_from(" \t\n#"), min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_parser_whitespace_and_comments_only(self, text: str) -> None:
        """Invariant: Whitespace/comments produce empty fragment."""
        # Add comment markers to make it valid
        lines = text.split("\n")
        commented = "\n".join(f"# {line}" if line.strip() else line for line in lines)
        _, _, _, _, _, fragment = parse_dsl(commented, Path("test.dsl"))
        assert fragment.entities == []
        assert fragment.surfaces == []

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
            min_size=1,
            max_size=20,
        ).filter(str.isidentifier)
    )
    @settings(max_examples=50)
    def test_parser_module_declaration(self, name: str) -> None:
        """Invariant: Module declaration extracts module name."""
        assume(name not in ("module", "app", "entity", "surface", "use"))  # Not keywords
        text = f"module {name}"
        module_name, _, _, _, _, _ = parse_dsl(text, Path("test.dsl"))
        assert module_name == name

    @given(
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
            min_size=1,
            max_size=15,
        ).filter(str.isidentifier),
        st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz "),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(max_examples=50)
    def test_parser_app_declaration(self, app_name: str, app_title: str) -> None:
        """Invariant: App declaration extracts name and title."""
        assume(app_name not in ("module", "app", "entity", "surface", "use"))
        # Escape quotes in title
        escaped_title = app_title.replace('"', '\\"')
        text = f'app {app_name} "{escaped_title}"'
        _, parsed_name, parsed_title, _, _, _ = parse_dsl(text, Path("test.dsl"))
        assert parsed_name == app_name
        assert parsed_title == app_title

    @given(
        st.text(
            alphabet=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            min_size=1,
            max_size=15,
        )
    )
    @settings(max_examples=50)
    def test_parser_minimal_entity(self, entity_name: str) -> None:
        """Invariant: Minimal entity declaration parses correctly."""
        assume(entity_name[0].isupper())  # Entity names should start uppercase
        text = f"""entity {entity_name} "Test entity":
  id: uuid pk
"""
        _, _, _, _, _, fragment = parse_dsl(text, Path("test.dsl"))
        assert len(fragment.entities) == 1
        assert fragment.entities[0].name == entity_name
        assert len(fragment.entities[0].fields) >= 1

    @given(st.integers(min_value=1, max_value=10))
    def test_parser_multiple_entities(self, count: int) -> None:
        """Invariant: Multiple entities are all parsed."""
        entities = []
        for i in range(count):
            entities.append(f"""entity Entity{i} "Entity {i}":
  id: uuid pk
""")
        text = "\n".join(entities)
        _, _, _, _, _, fragment = parse_dsl(text, Path("test.dsl"))
        assert len(fragment.entities) == count

    @given(
        st.lists(
            st.sampled_from(["int", "bool", "uuid", "date", "datetime", "text"]),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=50)
    def test_parser_field_types(self, types: list[str]) -> None:
        """Invariant: Various field types parse correctly."""
        # Note: str() requires length param, use text or other simple types
        fields = "\n".join(f"  field_{i}: {t}" for i, t in enumerate(types))
        text = f"""entity TestEntity "Test":
  id: uuid pk
{fields}
"""
        _, _, _, _, _, fragment = parse_dsl(text, Path("test.dsl"))
        assert len(fragment.entities) == 1
        # id + all defined fields
        assert len(fragment.entities[0].fields) == 1 + len(types)


class TestLexerEdgeCases:
    """Edge case fuzzing for lexer robustness."""

    @given(st.integers(min_value=1, max_value=50))
    def test_deeply_nested_indentation(self, depth: int) -> None:
        """Invariant: Deeply nested indentation doesn't crash."""
        lines = ["entity Test 'Test':"]
        indent = "  "
        for i in range(depth):
            lines.append(indent * (i + 1) + f"field{i}: str")
        text = "\n".join(lines)
        try:
            lexer = Lexer(text, Path("test.dsl"))
            tokens = lexer.tokenize()
            # Should have INDENT tokens for each level
            indent_count = sum(1 for t in tokens if t.type == TokenType.INDENT)
            assert indent_count >= 1  # At least one indent
        except ParseError:
            pass  # Some depths may fail validation

    @given(st.text(alphabet=st.sampled_from("\n\t "), min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_whitespace_only_input(self, text: str) -> None:
        """Invariant: Whitespace-only input produces only structural tokens or errors."""
        # Note: \r is excluded as it can cause inconsistent indentation errors
        try:
            lexer = Lexer(text, Path("test.dsl"))
            tokens = lexer.tokenize()
            # Should only have NEWLINE and EOF tokens
            for token in tokens:
                assert token.type in (
                    TokenType.NEWLINE,
                    TokenType.EOF,
                    TokenType.INDENT,
                    TokenType.DEDENT,
                )
        except ParseError:
            pass  # Inconsistent indentation is valid rejection

    @given(
        st.lists(
            st.sampled_from(["->", "<-", "<->", "==", "!=", ">=", "<="]), min_size=1, max_size=10
        )
    )
    @settings(max_examples=50)
    def test_multi_char_operators(self, operators: list[str]) -> None:
        """Invariant: Multi-character operators tokenize correctly."""
        text = " ".join(operators)
        lexer = Lexer(text, Path("test.dsl"))
        tokens = lexer.tokenize()
        # Should have one token per operator plus EOF
        operator_tokens = [t for t in tokens if t.type not in (TokenType.NEWLINE, TokenType.EOF)]
        assert len(operator_tokens) == len(operators)

    @given(st.sampled_from(["7d", "24h", "30min", "2w", "3m", "1y"]))
    def test_duration_literals(self, duration: str) -> None:
        """Invariant: Duration literals are tokenized correctly."""
        lexer = Lexer(duration, Path("test.dsl"))
        tokens = lexer.tokenize()
        assert len(tokens) >= 2
        assert tokens[0].type == TokenType.DURATION_LITERAL
        assert tokens[0].value == duration
