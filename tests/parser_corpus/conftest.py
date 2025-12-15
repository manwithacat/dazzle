"""Pytest configuration for parser corpus tests."""

from pathlib import Path

import pytest

# Corpus directories
CORPORA_DIR = Path(__file__).parent.parent / "corpora"
APPSPEC_CORPUS_DIR = CORPORA_DIR / "appspec"
STREAMSPEC_CORPUS_DIR = CORPORA_DIR / "streamspec"


@pytest.fixture
def appspec_corpus_dir() -> Path:
    """Return path to AppSpec corpus directory."""
    return APPSPEC_CORPUS_DIR


@pytest.fixture
def streamspec_corpus_dir() -> Path:
    """Return path to StreamSpec corpus directory."""
    return STREAMSPEC_CORPUS_DIR
