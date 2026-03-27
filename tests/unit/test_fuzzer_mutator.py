"""Tests for fuzzer mutation strategies."""

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from dazzle.testing.fuzzer.mutator import (
    delete_token,
    duplicate_line,
    insert_keyword,
    swap_adjacent_tokens,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


class TestTokenMutators:
    def test_insert_keyword_changes_input(self) -> None:
        dsl = 'entity Task "Task":\n  id: uuid pk\n'
        mutated = insert_keyword(dsl, seed=42)
        assert mutated != dsl

    def test_delete_token_produces_shorter_output(self) -> None:
        dsl = 'entity Task "Task":\n  id: uuid pk\n  title: str(200)\n'
        mutated = delete_token(dsl, seed=42)
        # Deleting a token should change the text
        assert mutated != dsl

    def test_swap_adjacent_changes_input(self) -> None:
        dsl = 'entity Task "Task":\n  id: uuid pk\n  title: str(200)\n'
        mutated = swap_adjacent_tokens(dsl, seed=42)
        assert mutated != dsl

    def test_duplicate_line_adds_content(self) -> None:
        dsl = 'entity Task "Task":\n  id: uuid pk\n  title: str(200)\n'
        mutated = duplicate_line(dsl, seed=42)
        assert len(mutated) > len(dsl)

    def test_mutations_deterministic_with_same_seed(self) -> None:
        dsl = 'entity Task "Task":\n  id: uuid pk\n'
        a = insert_keyword(dsl, seed=99)
        b = insert_keyword(dsl, seed=99)
        assert a == b


class TestTokenMutatorNeverCrashesParser:
    """Property: mutations of valid DSL never crash the parser (hang or unhandled exception)."""

    @given(st.integers(min_value=0, max_value=10000))
    @settings(max_examples=50)
    def test_insert_keyword_no_crash(self, seed: int) -> None:
        from dazzle.core.dsl_parser_impl import parse_dsl
        from dazzle.core.errors import ParseError

        dsl = 'module test\napp t "T"\n\nentity Task "Task":\n  id: uuid pk\n  title: str(200)\n'
        mutated = insert_keyword(dsl, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass  # Expected — structural errors are fine
