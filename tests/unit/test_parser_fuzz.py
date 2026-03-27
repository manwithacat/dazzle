# tests/unit/test_parser_fuzz.py
"""Hypothesis-powered parser fuzz tests.

These tests verify parser robustness invariants:
1. No input causes a hang (>5s timeout)
2. No input causes an unhandled exception (only ParseError is acceptable)
3. Mutations of valid DSL produce either valid output or clean ParseErrors
"""

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.testing.fuzzer.corpus import load_corpus
from dazzle.testing.fuzzer.mutator import (
    delete_token,
    duplicate_line,
    inject_near_miss,
    insert_keyword,
    swap_adjacent_tokens,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
_corpus: list[str] | None = None


def _get_corpus() -> list[str]:
    global _corpus
    if _corpus is None:
        _corpus = load_corpus(EXAMPLES_DIR)
    return _corpus


class TestParserNeverCrashesOnArbitraryInput:
    """The parser should only raise ParseError, never crash."""

    @given(st.text(min_size=0, max_size=2000))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_arbitrary_text(self, text: str) -> None:
        try:
            parse_dsl(text, Path("fuzz.dsl"))
        except ParseError:
            pass  # Expected

    @given(st.text(min_size=0, max_size=500, alphabet='abcdefghijklmnopqrstuvwxyz :_\n  "'))
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_dsl_like_text(self, text: str) -> None:
        """Text using DSL-like characters is more likely to reach deeper parser paths."""
        try:
            parse_dsl(text, Path("fuzz.dsl"))
        except ParseError:
            pass


class TestMutatedCorpusNeverCrashes:
    """Mutations of valid DSL should produce ParseError at worst, never crash."""

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_insert_keyword_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = insert_keyword(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_delete_token_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = delete_token(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_swap_adjacent_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = swap_adjacent_tokens(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_duplicate_line_mutation(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = duplicate_line(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass

    @given(st.integers(min_value=0, max_value=5000))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_near_miss_injection(self, seed: int) -> None:
        corpus = _get_corpus()
        if not corpus:
            pytest.skip("No corpus available")
        source = corpus[seed % len(corpus)]
        mutated = inject_near_miss(source, seed=seed)
        try:
            parse_dsl(mutated, Path("fuzz.dsl"))
        except ParseError:
            pass
