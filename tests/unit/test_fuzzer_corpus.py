"""Tests for fuzzer corpus loading."""

from pathlib import Path

from dazzle.testing.fuzzer.corpus import load_corpus


class TestCorpusLoader:
    def test_load_corpus_returns_nonempty(self) -> None:
        """Corpus loader finds DSL files in examples/."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        corpus = load_corpus(examples_dir)
        assert len(corpus) > 0

    def test_corpus_entries_are_strings(self) -> None:
        """Each corpus entry is a non-empty string of DSL text."""
        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        corpus = load_corpus(examples_dir)
        for entry in corpus:
            assert isinstance(entry, str)
            assert len(entry.strip()) > 0

    def test_corpus_entries_parse_successfully(self) -> None:
        """All corpus entries must parse without error (they're valid DSL)."""
        from dazzle.core.dsl_parser_impl import parse_dsl

        examples_dir = Path(__file__).resolve().parents[2] / "examples"
        corpus = load_corpus(examples_dir)
        for entry in corpus:
            # Should not raise
            parse_dsl(entry, Path("corpus.dsl"))
