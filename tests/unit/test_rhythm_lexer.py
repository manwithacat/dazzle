"""Tests for rhythm lexer tokens."""

from pathlib import Path

from dazzle.core.lexer import TokenType, tokenize


def test_rhythm_keyword_tokenized():
    tokens = tokenize("rhythm onboarding", Path("test.dsl"))
    assert tokens[0].type == TokenType.RHYTHM
    assert tokens[0].value == "rhythm"


def test_phase_keyword_tokenized():
    tokens = tokenize("phase discovery", Path("test.dsl"))
    assert tokens[0].type == TokenType.PHASE
    assert tokens[0].value == "phase"


def test_scene_keyword_tokenized():
    tokens = tokenize("scene browse", Path("test.dsl"))
    assert tokens[0].type == TokenType.SCENE
    assert tokens[0].value == "scene"
